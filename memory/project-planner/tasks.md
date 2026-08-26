# Task List — 蒸馏数据管道加速与 T4 满载（修正版 v2）

> 2026-08-14 截止赛覆盖：下面原 T4 项目保留为历史任务；8/17 07:59 前以本节为当前任务板。

## 截止赛残局任务板（2026-08-14 14:50 CST）

| ID | Task | Priority | Status | Exit rule |
|----|------|----------|--------|-----------|
| C-001 | 锁定历史 retreat 恢复件（已被 v22 取代） | P0 | completed-superseded | `submission_baseline/` 保持冻结；当前主 baseline 见 C-006/C-009 的 exact v22 |
| C-002 | Control/Search/router v13 跨牌组漏斗 | P0 | completed-negative | Control 死 Grim；Search 死 Alakazam；router 仅保住 Alakazam baseline、未形成综合提升 |
| C-003 | 盘点 Grim 固定牌组的现有规则 pilots | P0 | completed | v22/v24/v28 等消融完成；未硬套 Lucario 专用规则 |
| C-004 | Grim pilot 四腿闸：retreat / Grim / Router / Alakazam | P0 | completed | v22 修复后 n=64 三腿 + exact Alakazam 51-13；v29 重审加权仅 +0.27pp、直接 H2H 区间跨 50%，不翻案 |
| C-005 | 最佳 Grim 候选净包验证与确定性归档 | P0 | completed | v22 包含卡表/cg；双入口、60 卡、零 fault、双打包 SHA 一致、exact-archive 四腿通过 |
| C-006 | 8/15 发射裁决 | P0 | completed | 08:46 精确重交 v22，ref `55516725`；latest-2={新/旧 v22}；+84m 新796.9/旧829.4/团队829.4，封口 best-of-latest-2 |
| C-007 | 8/16 双 v22 旧收官分支 | P0 | superseded | 被 C-018/C-019 彩票分支覆盖；exact-v22 仍是最终不可丢托底 |
| C-008 | 8/17 07:59 冻结 | P0 | pending | 最后一发必须是测量最充分件；按收官 checklist 执行 |
| C-009 | v22 自生成 on-policy 残差 RL 单发 | P0 | completed-negative | 40-genome screen 后唯一幸存者对 exact v22 独立 n=256 为 133-123（51.95%）<55% 预注册线；`winner=null`，不生成/提交 challenger |
| C-010 | 两个近失 guard 的触发级 2×2 可行性 | P0 | completed-negative | seat-balanced 四腿 n=144、每臂36且先后手18/18、零 fault；两 guard 均 0 触发，95% 上界2.06%<闸所需11.03%，`INSUFFICIENT_OPPORTUNITIES`，不扩至544 |
| C-011 | live 校准 + 高暴露数值残差 | P0 | completed-negative | 82 replay 精确重放0 mismatch；两 guard live 0/82；分样本筛出 resource+25 / attachment+50，但四腿相对 incumbent −1.28/−2.68pp，winner=null，不进 n256 |
| C-012 | live job 决策面 + manual×hierarchy 结构消融 | P0 | completed-negative | 44/8,251 semantic controls；job 级无跨 ref 候选；2×2 每臂144局零 fault，三删减臂相对 exact 全负且 v22 主腿<53%，不进 n256 |
| C-013 | 早期 Dawn live 异常反事实暴露 | P1 | completed-negative | Dawn turn≤4 的 3-8 仅为探索关联；penalty 100–1200 最多改3/82场且替代全为 early Boss，selected=null，不跑 W/L |
| C-014 | 路线 A：单干预 on-policy advantage pilot | P0 | completed-negative | 36,432 局健康采集后 cross-fit 仅 +0.20pp、2/4 folds 同向、最差 −3.89pp，`TRAINING_KILL`；不进 canary/WL/materialize，8/16 只精确重交 v22 |
| C-015 | Route-A Router 正切片只读归因 | P1 | completed-postseason | 正信号集中 turn>=9、gap=0、same-type ability/attach；仅形成赛后R1预注册，禁止翻案或赛前追跑 |
| C-016 | live matchup 可见识别可行性 | P1 | completed-postseason | 新ref盲验turn2为20/32且20/20正确，A/L=12/12；裁决高精度可弃权router赛后GO，unknown仍exact-v22 |
| C-017 | 决赛机制与收官runbook | P0 | ready | 自动latest-2、无需手选、截止后约两周对局；8/16一发exact-v22，8/17 07:30前封口 |
| C-018 | M Sato 胡地 v5 高上限彩票 | P0 | completed-submitted | 455场专家审计；v5对v22独立42–86/128但较公开父策略+13.28pp；累计544局零fault、archive复验PASS；Kaggle ref `55537313` COMPLETE |
| C-019 | 高分长毛巨魔公开策略学习与彩票构建 | P0 | completed-negative | 157票公开件=exact-v22同核旧wrapper；Raihan真正同牌表专家为 refs `55177269/55202823`，135场残差模仿两轮尖峰均未复现；最佳v14镜像累计约51.0%，且Lucario/Crustle较v22同批回归约−12.5/−14.1pp，所有Grim-X KILL、未提交 |
| C-020 | 彩票分支最终锁定 | P0 | completed-superseded-by-C022 | 10:40曾KEEP `{55539395,55539446}`；16:00新增战绩与校正读数拉开后被C-022双v22最终编排覆盖 |
| C-021 | Public Alakazam Courage v22 高上限彩票 | P0 | completed-submitted-out-of-final2 | ref `55539395` 已按预期被C-022挤出；署名台账继续保留，writeup不得宣称策略或LB950原创 |
| C-022 | exact-v22 第二槽独立实例 | P0 | completed-submitted-final | 冻结SHA `599e19ae…b4c8bfcf` 单发为ref `55547740` COMPLETE；latest-2=`{55547740新v22,55539446成熟v22}`，禁止第二次成功提交，余1发仅ERROR恢复 |
| C-023 | 8/16夜间封盘只读监视 | P0 | running | smoke HEALTHY；22:30/00:30/02:30/05:30固定采集两ref状态、latest-2与逐局数据；任何分数/WR波动不授权提交，05:30后进程自动退出 |

当前禁止项：按瞬时峰值追单、用 config A 当主 baseline、重开 NN/search 训练、为寻找
guard 尖峰把 C-010 扩到 544 局或降低预注册闸、修改七件既有 Automation。

C-014 是对“重开 NN/search 训练”禁令的**已授权窄例外**：只允许每局最多一次干预、
exact-v22 永久回退的小型线性 advantage 头；不得外扩为完整 PPO/大网络/搜索。
预注册见 `reports/20260815_routeA_prereg.md`，立项核算见
`reports/20260815_routeA_gonogo_memo.md`。

当前 baseline/托底为 `artifacts/grim_v22_final/submission.tar.gz`（archive SHA256
`599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`）；当前活跃
lottery challenger 为 `artifacts/roman_alakazam_public950_lottery/submission.tar.gz`
（SHA256 `14dfb7666fc14c0fe16e5b9d5e843b0edcd4dd1187f06d22c5114d04e94a53fc`）。
M Sato v5 归档 `83372cfe…993a9` 保留为明早两发回退链的候选。收官槽位规则见
`reports/20260816_lottery_branch_runbook.md`。

RL 负结果与测量修复见 `reports/20260815_v22_onpolicy_residual_rl.md`；8/16 不得以
screen 尖峰替代 n=256 裁决。触发级封口见
`reports/20260815_v22_guard_factorial_feasibility.md`。

live 校准、RNG 口径与数值残差封口见
reports/20260815_live_calibration_and_dense_residual.md；C-011 的行为 PASS
不是 W/L PASS，不得据此生成或提交候选。

剩余决策面封口见 `reports/20260815_v22_remaining_surface_audit.md`；C-012/C-013
均为 `winner=null`，不得把 manual-only 的跨腿切片或 Dawn 负相关倒推成赛前候选。

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
