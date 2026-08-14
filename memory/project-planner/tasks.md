# Task List — 蒸馏数据管道加速与 T4 满载（修正版 v2）

> 2026-08-14 截止赛覆盖：下面原 T4 项目保留为历史任务；8/17 07:59 前以本节为当前任务板。

## 截止赛残局任务板（2026-08-14 14:13 CST）

| ID | Task | Priority | Status | Exit rule |
|----|------|----------|--------|-----------|
| C-001 | 锁定 incumbent = retreat 精确恢复件 | P0 | completed | `main=411d9dff`、`deck=2a541d7b`；禁止改 `submission_baseline/` |
| C-002 | Control/Search/router v13 跨牌组漏斗 | P0 | completed-negative | Control 死 Grim；Search 死 Alakazam；router 仅保住 Alakazam baseline、未形成综合提升 |
| C-003 | 盘点 Grim 固定牌组的现有规则 pilots | P0 | completed | v22/v24/v28 等消融完成；未硬套 Lucario 专用规则 |
| C-004 | Grim pilot 四腿闸：retreat / Grim / Router / Alakazam | P0 | completed | v22 修复后 n=64 三腿 + exact Alakazam 51-13；v29 重审加权仅 +0.27pp、直接 H2H 区间跨 50%，不翻案 |
| C-005 | 最佳 Grim 候选净包验证与确定性归档 | P0 | completed | v22 包含卡表/cg；双入口、60 卡、零 fault、双打包 SHA 一致、exact-archive 四腿通过 |
| C-006 | 8/15 发射裁决 | P0 | ready | 配额重置后尽早提交 `grim_v22_final`；20:00 改为首轮 live 盘点 |
| C-007 | 8/16 每日一发 + 条件恢复 | P0 | pending | 只在 v22/retreat 中重交后验最强件；禁止全新变体，满足每日真实反馈硬约束 |
| C-008 | 8/17 07:59 冻结 | P0 | pending | 最后一发必须是测量最充分件；按收官 checklist 执行 |

当前禁止项：按瞬时峰值追单、用 config A 当主 baseline、重开 NN/search 训练、修改七件既有 Automation。

当前唯一 challenger：`artifacts/grim_v22_final/submission.tar.gz`，archive SHA256
`599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`。
完整证据见 `reports/20260814_grim_v22_delivery.md`。

## Dependency Graph
```
T-001 (profiler 基线，前置门槛)
  └──→ T-002 (按 profiler 结论分支：管道修复)
         └──→ T-003 (正确性 + 抽样均匀性等价)
                └──→ T-004 (部署链路同步 + 校验)
                       └──→ T-005 (T4 实测 M1：data-wait≈0 + epoch 大幅降)
                              ├──→ T-006 (M2 放大计算规模，条件触发)
                              │        └──→ T-007 (TFLOP/s 吞吐实测)
                              └──→ T-008 (CPU 基线对照，P2)
```

## Critical Path
T-001 → T-002 → T-003 → T-004 → T-005（M1）；T-006 → T-007（M2，条件触发）

## Phase: 分析与基线
| ID | Task | Priority | Depends On | Complexity | Est. Effort | Status |
|----|------|----------|------------|------------|-------------|--------|
| T-001 | 本地 --limit --profile 基线 + 分支决策 | P0 | - | Medium | 30m | completed |

## Phase: 核心实现（M1）
| ID | Task | Priority | Depends On | Complexity | Est. Effort | Status |
|----|------|----------|------------|------------|-------------|--------|
| T-002 | 按 profiler 结论实施管道修复 | P0 | T-001 | High | 60m | completed |
| T-003 | 正确性 + 抽样均匀性等价对比 | P0 | T-002 | Low | 30m | completed |
| T-004 | 部署链路同步 + 版本校验 | P0 | T-003 | Low | 30m | completed |
| T-005 | T4 实测 M1（data-wait<10% + epoch ≥3x 降） | P0 | T-004 | Medium | 60m | completed（稳态 prepare 0.1%/compute 99.8%，见 progress 17:55） |

## Phase: M2（条件触发）
| ID | Task | Priority | Depends On | Complexity | Est. Effort | Status |
|----|------|----------|------------|------------|-------------|--------|
| T-006 | 放大 teacher hidden/blocks/bs | P1 | T-005 | Medium | 60m | pending |
| T-007 | TFLOP/s 吞吐实测报告 | P1 | T-006 | Low | 30m | pending |
| T-008 | CPU 基线对照（≥32GB 多核） | P2 | T-005 | Low | 45m | pending |

---

## Task Details

### T-001: 本地 --limit --profile 基线 + 分支决策
- **Phase**: 分析与基线
- **Status**: in_progress
- **Priority**: P0
- **Depends on**: none
- **Complexity**: medium
- **Estimated effort**: 30m
- **Files to create**: 无
- **Files to modify**: `inference/dataset/train_v2.py`（已加 SegProfiler + workers/depth/block 参数位）
- **Details**:
  1. run_phase 已按 batch 计时 prepare/transfer/compute 三段
  2. 本地 `--limit 50000 --stage distill --epochs-distill 1 --prefetch-workers 1 --profile` 跑基线
  3. 按 design.md 分支决策表判断瓶颈归属 → 决定 T-002 方案
- **Acceptance**: 输出每 batch 三段 ms 与占比，明确瓶颈归属并记录决策
- **AC Mapping**: AC-001

### T-002: 按 profiler 结论实施管道修复
- **Phase**: 核心实现（M1）
- **Status**: pending
- **Priority**: P0
- **Depends on**: T-001
- **Complexity**: high
- **Estimated effort**: 60m
- **Files to create**: 无
- **Files to modify**: `inference/dataset/train_v2.py`
- **Details**:
  1. 若 prepare 占比高：BatchPrefetcher 改为「物理连续块 `[b,b+C)` + 块内 shuffle + N worker 依次 grab 块」；workers/depth/block 参数接入
  2. 若 transfer 占比高：缩 H2D 流量/分块 transfer
  3. 若 compute 占比高：不在此修复，转 T-006（M2）
  4. 保持 uint8→GPU 转换路径与 pin_memory；workers=0 纯串行对照
  5. 抽样均匀性断言：--limit 内每样本恰好出现一次
- **Acceptance**: profile 显示目标段占比显著下降
- **AC Mapping**: AC-002, NF-002

### T-003: 正确性 + 抽样均匀性等价对比
- **Phase**: 核心实现（M1）
- **Status**: pending
- **Priority**: P0
- **Depends on**: T-002
- **Complexity**: low
- **Estimated effort**: 30m
- **Files to create**: 无
- **Files to modify**: 无
- **Details**:
  1. 相同 seed/--limit/epochs 跑基线（workers=0 串行）与修复后（workers=2）
  2. 对比 bc/distill loss 与 canary top1，差值 ≤1e-3
  3. 每样本出现次数断言 = 1
- **Acceptance**: top1 差距 ≤1e-3 且抽样计数=1
- **AC Mapping**: AC-003, NF-002

### T-004: 部署链路同步 + 版本校验
- **Phase**: 核心实现（M1）
- **Status**: pending
- **Priority**: P0
- **Depends on**: T-003
- **Complexity**: low
- **Estimated effort**: 30m
- **Files to create**: 无
- **Files to modify**: `.kaggle_stage_code/ptcg_code.tar.gz`（重建）、`.kaggle_kernel/run_experiment.py`（TRAIN_ARGS 同步）
- **Details**:
  1. 由 inference/dataset 重建 ptcg_code.tar.gz（含 train_v2.py 新版）
  2. version 上传 ptcg-code dataset
  3. run_experiment.py TRAIN_ARGS 加 --prefetch-workers/--profile
  4. push 前校验：tar 内 train_v2.py 与本地 hash 一致
- **Acceptance**: 三者版本一致（AC-004）
- **AC Mapping**: AC-004

### T-005: T4 实测 M1
- **Phase**: 核心实现（M1）
- **Status**: pending
- **Priority**: P0
- **Depends on**: T-004
- **Complexity**: medium
- **Estimated effort**: 60m
- **Files to create**: 无
- **Files to modify**: 无
- **Details**:
  1. push_t4.py 推送，kernel 内 --profile 跑 distill
  2. 对比基线 epoch 秒数与 prepare 占比
- **Acceptance**: prepare 占比 <10% 且 epoch 时间 ≥3x 下降
- **AC Mapping**: AC-005, NF-005

### T-006: M2 放大计算规模
- **Phase**: M2
- **Status**: pending
- **Priority**: P1
- **Depends on**: T-005
- **Complexity**: medium
- **Estimated effort**: 60m
- **Files to create**: 无
- **Files to modify**: `.kaggle_kernel/run_experiment.py`（TRAIN_ARGS）
- **Details**:
  1. M1 通过后，逐步放大：teacher hidden 1024→2048→4096、blocks 2→4、bs 16384→32768
  2. 每档 profile，找 compute 成为主导的档位
- **Acceptance**: compute 占比显著上升且与放大倍数一致
- **AC Mapping**: AC-006

### T-007: TFLOP/s 吞吐实测
- **Phase**: M2
- **Status**: pending
- **Priority**: P1
- **Depends on**: T-006
- **Complexity**: low
- **Estimated effort**: 30m
- **Files to create**: `scripts/measure_tflops.py`
- **Files to modify**: 无
- **Details**:
  1. 用 teacher 参数量×2×每 epoch 前向/反向步数 ÷ compute 秒数 估实测 TFLOP/s
  2. 对比放大前后提升
- **Acceptance**: 相对放大前 ≥2x
- **AC Mapping**: AC-007

### T-008: CPU 基线对照
- **Phase**: M2
- **Status**: pending
- **Priority**: P2
- **Depends on**: T-005
- **Complexity**: low
- **Estimated effort**: 45m
- **Files to create**: 无
- **Files to modify**: 无
- **Details**:
  1. 记录「T4 机 ~13GB RAM + 14GB 数据 mmap 抖动」风险（R-006）
  2. 如可行，用 ≥32GB 多核 CPU 实例跑同 pipeline 对比 epoch 时间
- **Acceptance**: 记录风险并产出 CPU 对照数据（如有）
- **AC Mapping**: AC-008
