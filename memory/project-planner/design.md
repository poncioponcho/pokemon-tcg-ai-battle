# Technical Design — 蒸馏数据管道加速与 T4 满载（修正版 v2）

## Architecture
### Style: 单机流水线（数据生产者 ↔ GPU 计算消费者 解耦），零新增依赖

### Layer Diagram
```
┌─────────────────────── train_v2.py ──────────────────────────┐
│                                                                │
│  ┌──────────────┐      ┌─────────────────────────────┐        │
│  │  数据层       │      │  BatchPrefetcher (修复)      │        │
│  │ 14GB mmap    │──▶───│  · N producer 线程池          │        │
│  │ states_u8     │      │  · 物理连续块读 + 块内 shuffle │        │
│  │ opts_u8       │      │  · uint8 直接入队(省4x拷贝)   │        │
│  │ scalars/labels│      └────────────┬────────────────┘        │
│  └──────────────┘                     │ queue.Queue             │
│                        ┌──────────────▼────────────────┐        │
│                        │  训练循环 (run_phase)          │        │
│                        │  · get() 等数据(计时=prepare)  │        │
│                        │  · to(device) uint8→fp16/32    │        │
│                        │  · autocast forward/backward   │        │
│                        └──────────────┬────────────────┘        │
│                                       │                          │
│                ┌──────────────────────▼───────────┐             │
│                │  --profile 仪表盘                 │             │
│                │  prepare/transfer/compute 分段计时 │             │
│                └──────────────────────────────────┘             │
└────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities
| Component | Responsibility | Depends On |
|-----------|---------------|------------|
| 数据层 | mmap 只读 14GB numpy | numpy |
| BatchPrefetcher | 并行 gather + pin_memory + 入队 | threading/queue |
| run_phase 训练循环 | 消费 batch、autocast 前向/反向 | BatchPrefetcher |
| --profile 仪表盘 | 每 batch/epoch 输出三段耗时 | time.perf_counter |

## Data Flow（物理连续块读，修正 v1 的写反 bug）
v1 的错误：把全局随机 `perm` 切成连续块 → `perm[a:a+k]` 是分散在 8GB 文件里的随机下标，
gather 仍是随机访问，页缓存命中率不提升。

**修正后的正确做法**：
1. 将文件物理地址空间 `[0, n)` 按块大小 `C`（如 8×bs）切成**物理连续区间** `[b, b+C)`
2. 每个块内的样本下标做一次 `np.random.permutation`（块内乱序）
3. worker 依次 grab 下一个物理块（块间顺序），块内 gather 的是 `[b, b+C)` 连续段
   → 每次 `arrays['states_u8'][b:b+C]` 读取 mmap 连续页 → 顺序读，页缓存命中率高
4. 抽样均匀性：每样本每 epoch 恰好出现一次（NF-002）；随机性来自块内 permutation

块大小 C 是超参：C=1×bs 时近似全局乱序但几乎无连续收益；C=32×bs 时连续读最优但块内
随机性局限在同一块内。默认 C=8×bs（bs=16384 → 每块 131072 样本 ≈ 576MB 连续读）。

## 分支决策（F-002 不预设方案）
修复方案**由 --profile 结果决定**，候选：

| profiler 发现 | 修复 | 涉及 |
|---------------|------|------|
| prepare 占比高（等数据） | 多 worker + 物理连续块读 + 增大 depth | BatchPrefetcher |
| transfer 占比高 | 减 H2D 流量（uint8 已省 4x）；缩 batch 或分块 transfer | 训练循环 |
| compute 占比高（GPU 慢） | 放大模型/bs（转入 M2） | run_phase + 超参 |
| 三者都低但 epoch 仍长 | Python 串行开销 / eval / ckpt 保存 | 循环外瓶颈审计 |

## Data Model
无持久化数据模型变更；仅运行时数据结构：
| 对象 | 形状 | dtype | 说明 |
|------|------|-------|------|
| states_u8 | (1.8M, 4400) | uint8 | 8GB mmap |
| opts_u8 | (1.8M, 64, 52) | uint8 | 6GB mmap |
| scalars | (1.8M, 90) | float32 | mmap |
| labels/masks | (1.8M, 64) | int64 | mmap |
| 队列元素 | batch 元组 | 混合 | 上限 depth 防 OOM |

## API Contracts
无对外 API；CLI 变更：
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| --profile | flag | 关 | 输出每 batch prepare/transfer/compute 分段耗时 |
| --prefetch-workers | int | 1 | 生产者线程数（1=单线程基线对照） |
| --prefetch-depth | int | 2 | 队列深度 |
| --prefetch-block | int | 8×bs | 物理块大小（×bs 的倍数），0=完全随机对照 |

## 部署链路（钉死，AC-004）
优化必须落在真实被 push 的文件上：
```
inference/dataset/train_v2.py   ← 源码改动点（profiler/管道/CLI）
        │ 打包
        ▼
.kaggle_stage_code/ptcg_code.tar.gz   ← 由源码重建（.kaggle_stage_code/dataset-metadata.json: daniel1547/ptcg-code）
        │ version 上传（kaggle datasets version -p .kaggle_stage_code）
        ▼
Kaggle ptcg-code dataset
        │
.kaggle_kernel/run_experiment.py   ← kernel 主体，含 TRAIN_ARGS（--prefetch-workers 等需同步）
        │ push_t4.py 推送（machine_shape=NvidiaTeslaT4）
        ▼
Kaggle kernel 解压 ptcg_code.tar.gz → python3 train_v2.py
```
校验：push 前 `tar -tzf ptcg_code.tar.gz | grep train_v2.py` + 对比 tar 内与本地源码 hash。

## Error Handling
| Layer | Error Type | Handling |
|-------|-----------|----------|
| Producer 线程 | 异常 | 记录 _err，主循环迭代时抛 RuntimeError（沿用现模式） |
| 线程终止 | 训练中断 | _stop.set() + daemon 线程 |
| GIL 争用 | 实测 | workers=1/2/3/4 各跑一次取最优 |

## File Structure
```
inference/dataset/
├── train_v2.py      # 修改：SegProfiler + BatchPrefetcher 修复 + 块读参数
├── train_bc.py      # 不改（batch_from_idx 保持，供对照）
└── model_v2.py      # 不改
.kaggle_stage_code/
├── ptcg_code.tar.gz # 重建（含 train_v2.py 新版本）
└── dataset-metadata.json
.kaggle_kernel/
└── run_experiment.py # TRAIN_ARGS 同步新参数
memory/project-planner/
├── plan.md          # v2 修正
├── design.md        # 本文件 v2
└── tasks.md         # v2
```

## Test Strategy
| Layer | Test Type | 方法 | 覆盖 |
|-------|-----------|------|------|
| 管道正确性 | 等价对比 | --limit 小样本跑 bc+distill 各 1 epoch，新旧对比 loss | 修复不改变数学结果 |
| 抽样均匀性 | 计数断言 | --limit 内每样本出现次数恰为 1 | NF-002 |
| 数据等待 | profile | 对比 prepare 占比 | data-wait→0 |
| T4 实测 M1 | Kaggle kernel | --profile 日志：prepare 占比<10% + epoch 大幅降 | AC-005 |
| T4 实测 M2 | Kaggle kernel | 放大前后 compute ms 与 TFLOP/s 对比 | AC-006/007 |

## Key Design Decisions
| Decision | Options Considered | Chosen | Rationale |
|----------|-------------------|--------|-----------|
| 块切分 | 全局随机 perm 切块（错）/ 物理连续块+块内 shuffle（对） | 物理连续块+块内 shuffle | mmap 连续读；v1 写反已修正 |
| 修复方案 | 预设多 worker / 按 profiler 分支 | 按 profiler 分支 | R-001：不预设方案 |
| 多线程 vs 多进程 | ProcessPool / DataLoader(num_workers) / 手写线程池 | 手写线程池 | numpy 释放 GIL 可并行；零新依赖；避免 fork 复制页表 |
| M1/M2 关系 | 混在一条 AC / 拆开 | 拆开（M2 条件触发） | AC 不互相矛盾 |
| 成功指标 | nvidia-smi util% / data-wait+TFLOP/s | data-wait+TFLOP/s | util% 只量"有无 kernel"，不量吞吐 |
