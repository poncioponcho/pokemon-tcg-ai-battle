# Project Plan — 蒸馏数据管道加速与 T4 满载（修正版 v2）

## Domain
- **Type**: AI/ML（PyTorch 训练数据管道优化）
- **Pattern**: Pipeline 优化（数据生产者 → 计算消费者 解耦）
- **Language**: Python 3.x + PyTorch ≥2.5

## Overview
`train_v2.py` 的 BC→AWR→Distill 全流程在 Kaggle 免费 T4（周配额 30h 重置）上每 epoch 耗时 120–180s，
但纯 GPU 计算每 epoch 仅 ~1s（T4 fp16 ≈65 TFLOPS，teacher 前向 ~3.6e13 MACs + student fwd/bwd ~2.5e13 FLOPs），
即瓶颈 100% 在 CPU 侧数据管道。

本计划分两个**互相独立**的目标（AC 互不绑定）：
- **M1（更快，P0，主目标）**：修复数据管道，让相同 epoch 数在 T4 上大幅提速 → 周配额内塞进更多实验。
- **M2（更满，P1，条件触发）**：M1 验证通过后，再评估是否放大计算规模（teacher hidden/blocks/bs），
  让 tensor core 成为真实瓶颈。**M2 不承诺 epoch 变短，只承诺吞吐/利用率提升。**

## User Persona
- **Primary user**: 项目作者（单人科研/竞赛）
- **User goal**: 不超 30h/周免费 T4 配额，distill 阶段跑得更快；若可满载则满载

## User Journey (Primary Flow)
1. 本地 Mac（M4/24GB/MPS）用真实 14GB 数据跑 train_v2.py --stage distill --limit 小样本 + --profile
2. **按 profiler 结果判定瓶颈归属**（prepare/transfer/compute 三段），再选修复方案（分支决策，非既定方案）
3. 实施管道修复（方案取决于第 2 步结论；候选：多 worker / 物理连续块读 / 去 pin_memory 冗余 / 减少 H2D）
4. 本地验证 loss/top1 与基线一致（等价对比）
5. 部署链路：train_v2.py → .kaggle_stage_code/ptcg_code.tar.gz → ptcg-code dataset → run_experiment.py → push_t4.py
6. T4 实测 M1 成功标准（data-wait≈0 + epoch 大幅降）
7. （可选 M2）放大 teacher 满载，实测 TFLOP/s

## Scope

### P0 — MVP (Must Have) → M1「更快」
| ID   | Feature | Description | AC |
|------|---------|-------------|----|
| F-001 | 数据管道 profiler（前置门槛） | 本地可跑，输出 per-batch prepare/transfer/compute 三段耗时 | AC-001 |
| F-002 | 按 profiler 结果的管道修复 | 分支决策后实施；候选方案见 design.md | AC-002 |
| F-003 | 正确性保持 | 修复前后 loss/top1 一致 | AC-003 |
| F-004 | 部署链路同步 | 改 train_v2.py → 重建 ptcg_code.tar.gz → version dataset → run_experiment.py 参数同步 | AC-004 |
| F-005 | T4 实测 M1 | data-wait≈0 + epoch 大幅降 | AC-005 |

### P1 — Important → M2「更满」（条件触发）
| ID   | Feature | Description | AC |
|------|---------|-------------|----|
| F-006 | 放大计算规模 | teacher hidden/blocks/bs 放大，tensor core 成为瓶颈 | AC-006 |
| F-007 | 吞吐实测 | 每步 compute ms + 实测 TFLOP/s 报告 | AC-007 |

### P2 — Deferred
| ID   | Feature | Description | AC |
|------|---------|-------------|----|
| F-008 | CPU 基线对照 | ≥32GB RAM 多核 CPU 实例跑同 pipeline 对比 | AC-008 |
| F-009 | 周配额内多配置编排 | 单 kernel 顺序跑多组超参 | AC-009 |
| F-010 | 蒸馏超参自动搜索 | 复用富余算力 | - |

### Explicitly Out of Scope
- 改模型架构（student 必须保持 numpy 可复现的固定层序）
- Kaggle→本地数据迁移、租赁 GPU
- 训练算法本身（AWR/蒸馏公式）不变
- M2 之前不承诺任何「GPU 利用率」类指标

## Acceptance Criteria

### M1（更快）— Functional
- [ ] AC-001: `--profile` 模式下每 batch 打印 prepare_ms / transfer_ms / compute_ms 三段耗时（verified by: 本地 --limit 50000）
- [ ] AC-002: 修复后 prepare（等数据）占比显著下降，队列不再周期性空转；修复方案与 profiler 结论一致（verified by: profile 输出 + 决策记录）
- [ ] AC-003: 相同 seed/epochs/limit 下修复前后 canary top1 差距 ≤1e-3 或 loss 曲线形态一致（verified by: 两次运行对比）
- [ ] AC-004: 部署链路上 train_v2.py、ptcg_code.tar.gz、run_experiment.py 的 TRAIN_ARGS 三者版本一致（verified by: tar 内容 diff + kernel 日志）
- [ ] AC-005: T4 上 distill 单 epoch 中 prepare 等待占比 <10%（data-wait≈0），且 epoch 时间相对基线（120–180s）**大幅下降**（目标 ≥3x，verified by: kaggle kernel 日志 --profile）

### M2（更满）— Functional（M1 通过后触发）
- [ ] AC-006: 放大后 T4 distill 每步 compute 时间显著上升且与放大倍数一致（计算成为主导，verified by: profile）
- [ ] AC-007: 实测 TFLOP/s 报告（teacher 参数×2×3 步数 / compute 秒数），相对放大前提升 ≥2x（verified by: 计算脚本）

### Non-Functional
- [ ] NF-001: profile 改动零侵入（默认不开 profiling 不减速）(verified by: --profile 默认关闭)
- [ ] NF-002: 修复不改变 shuffle 语义/抽样均匀性（每样本每 epoch 恰好一次）(verified by: 代码审查 + 计数断言)
- [ ] NF-003: 可回滚 — 所有改动经 git 可 diff，失败可 revert（verified by: git status）
- [ ] NF-004: 内存 — 14GB 数据 + prefetch 在 Kaggle T4 环境不 OOM（verified by: kernel 跑完）
- [ ] NF-005: **指标口径** — 不使用 nvidia-smi util% 作为 M1 成功判据（只作参考）；M1 判据是 data-wait 占比 + epoch 时间，M2 判据是 TFLOP/s（verified by: 记录方式）

## Technology Choices

| Dependency | Version | Purpose | Why chosen |
|------------|---------|---------|------------|
| PyTorch | ≥2.5（现有） | 训练 + profile | 已用，零新增 |
| numpy | ≥2.0（现有） | mmap 数据访问 | 已用，零新增 |

不新增任何依赖；并发 prefetch 用标准库 threading/queue（已存在）。

## Risk Matrix

| ID | Description | Likelihood | Impact | Mitigation |
|----|-------------|-----------|--------|------------|
| R-001 | profiler 显示瓶颈是 transfer/autocast 而非 prepare，多 worker 方案白做 | Med | High | F-002 明确「按 profiler 结论分支」，设计不预设方案 |
| R-002 | 多线程 gather GIL 争用更慢 | Med | Med | numpy fancy-index 释放 GIL；workers 1/2/3/4 实测取最优 |
| R-003 | 本地 Mac (MPS/24GB) 与 T4 行为不同 | Med | Med | 本地只验正确性与趋势；绝对指标以 T4 为准 |
| R-004 | Kaggle 周配额有限，多轮 push 消耗快 | High | Med | 本地充分验证再 push；单次 kernel 多配置（F-009） |
| R-005 | 物理连续块切分改变 shuffle 语义 | Med | Low | 块内随机 + 跨块顺序，每样本每 epoch 恰好一次（NF-002 断言） |
| R-006 | 数据 14GB > T4 机 RAM ~13GB，mmap 冷读磁盘抖动 | High | Med | 块级连续读缓解；F-008 CPU 基线对照承认此风险；必要时分片/预处理 |
| R-007 | 部署链路版本不同步（改了 train_v2.py 但 tar/dataset 没更新） | Med | High | AC-004 强制三者 diff 校验 + push_t4.py 流程复核 |
| R-008 | 放大 teacher 后 epoch 变长、不满足「更快」预期 | Low | Med | M1/M2 AC 拆开，M2 不承诺 epoch 变短 |

## Constraints
- 30h/周免费 Kaggle GPU 配额（T4 x2，sm_75）；T4 机 RAM ~13GB < 数据 14GB
- 本地仅 Mac M4 24GB / MPS，不能当最终性能基准
- student 架构必须保持 numpy 可复现（export_student.py 按固定层序映射权重）
- 工作区已有未提交的 BatchPrefetcher 改动，修复需在其基础上做

## External Dependencies
| Name | Type | Endpoint/Version | Failure mode |
|------|------|------------------|--------------|
| Kaggle kernels | Service | GPU T4 x2 / 30h 每周 | 配额耗尽 → CPU 兜底 |
| ptcg-tensors dataset | Data | 私有 dataset（14GB npy） | 挂载失败 → dump_input_tree 诊断 |
| ptcg-code dataset | Data | 私有 dataset（train_v2.py 等打包 tar.gz） | 未更新 → AC-004 校验拦截 |

## Assumptions
- Kaggle 免费 T4 配额按周重置
- 数据管道是当前唯一显著瓶颈（纯计算 ~1s/epoch 的估算基于 teacher hidden=1024 blocks=2）
- M1 只针对 `train_v2.py`（Kaggle 一体化脚本）；ptcg-bcrl Phase2 的 train.py 不在本次范围
- nvidia-smi util% 只作参考，不作 M1 判据（NF-005）
