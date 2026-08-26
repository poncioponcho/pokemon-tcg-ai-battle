# Progress Log — 蒸馏数据管道加速与 T4 满载（v2）

## 2026-08-08 17:55 — 修复轮：输出膨胀✓ / T-005✓ / arena 选拔落地 / first 归因
- **输出膨胀修复**：run_experiment.py 收尾删 working/data 的 7 个 npy，本轮产物下载秒级完成（上轮 ~10GB）
- **T-005 正式收尾**：T4 --profile 实测 —— 冷启动 ep1-2 prepare 68%（页缓存冷），
  稳态 ep3+ **prepare 0.1% / transfer 0.1% / compute 99.8%**（完全计算 bound）；
  17.4s/epoch distill、26.6s/epoch teacher。prepare<10% 达标 → tasks.md completed
- **arena 选拔机制落地**（RCA 修复①）：train_v2.py distill 每 epoch 存 student_epN.pt；
  8 快照本地导出 npz 逐一对战 → **ep6 胜出**（mirror 8000 局合计 0.518），
  canary 最优 ep8（0.5293）arena 仅 0.509 → canary↔arena 脱节二次实锤
- 仓库根 npz 已换 ep6（sha ed7669…）；ep8 备份 reports/model_student.distill-v2t-ep8-canarybest.backup.npz
- ledger 记 distill_snap_ep6：R=+0.62，first_ok/canary_ok ✓，mirror 仍不达 +2pp → REJECTED 不提交
- **first 弱点归因**（deck_policy_isolation n=1000）：策略效应 -0.044（规则本身有效）、
  **卡组效应 +0.111** → 对 first 的 0.33 胜率是**牌组构筑问题**，不是决策问题
- 待决：牌组构筑优化（新方向，预期收益最大）；T-006 放大 teacher 价值存疑
  （student 已弱于规则，teacher 更大解决不了分布外模仿根因）

## 2026-08-08 17:40 — RCA 裁决：npz 无增益根因 = student 实战弱于规则（分布外模仿）
- 机制排除：rerank 介入率 10.1%（~4次/局），npz 加载正常，无静默降级
- 决定性实验：nn_first（NN 全权）vs 规则 champion 仅 **27.2%** 胜率（n=500）
- A/B 剂量效应：gap=0 介入 34% → wr 0.487；gap=1 介入 10% → ~0.52；gap=2 介入 0.8% → 0.520
  → **NN 介入单调负期望**，gap=1.0 的"≈中性"已是该模型质量下的最优
- 数据层根因：训练=13.8K 局 LB replay 双视角（1.8M 决策），与我方牌组多重集重叠
  中位数 **11/60 张**，≥30 张重叠的 episode 仅 5.2% → 我方牌组上近乎纯分布外泛化
- 特征 skew 排除：extract.py / agent.py / main.py 三处特征构造逐字段一致（4D 对手牌组槽已堵泄漏）
- 次级因素：mirror 同牌组轮换先手，抽牌运气主导，+2pp 门禁对价值中性改动不可达
- 修复方向（优先级）：①训练分布对准部署（自对局/相似牌组 replay 加权 ~720 局微调）
  ②选择压力换实战 metric（student ckpt 用 arena 选而非 canary top1）
  ③'first' 对局 0.33 是更大 R(e) 机会（30*dwr_first），deck_policy_isolation.py 待跑
- 产物：experiments/nn_override_probe.py、arena_report-rca_nn_first.json

## 2026-08-08 17:05 — 蒸馏完成 + arena 门禁 REJECTED（不提交）
- 蒸馏运行 ~7min（17.4s/epoch，T4，全程 8/8 epochs，best @ ep8）
- student：canary 0.5282 / fixed 0.5228 / 1.99M params；export self-check top1_agreement=1.0 ✓
- teacher 校验：hash b96c26… = v2 ✓（报告内 teacher 指标 0.5515/0.5412 一致）
- arena 2000 局：mirror 0.519 vs champ(v23_2 纯规则) 0.5205 → Δ-0.15pp，需 +2pp → **REJECTED**
  first 0.341 ✓（+1.25pp）、total 0.6306、v22_5 0.9025、R=+1.71（修正 canary 后）
- 质量规律再现：块读管道 ~1.5x 快但 ~1pp 质量回退（今早 P100 student canary 0.5385 > 本轮 0.5282）
- 但 arena 主指标本轮更好：mirror 0.519 > 今早 0.4996（final_v4_v2）→ npz 保留新版，
  旧版备份 reports/model_student.morning-v1.backup.npz
- 修正：inference/dataset/data/train_v2_report.json 原是旧 CPU 残值（0.2622），已换真值，
  ledger 重记 distill_v2t（R=+1.7116, canary_ok=true, promoted=false）
- 结论：champion 仍是 v23_2 纯规则（champion.json 不存在）；npz hybrid 在 mirror 上
  相对纯规则无增益（今日全部候选 0.50~0.52），+2pp 门槛差距大 → 本轮不提交
- 下一步方向：T-005 补 --profile 收尾 → T-006 放大 teacher；或排查 npz rerank 无增益根因

## 2026-08-08 16:42 — 蒸馏（v2 teacher）已推送，RUNNING
- 决策：蒸馏用 v2 teacher（canary 0.5515 > v3 0.5437；远端 ptcg-ckpt 已校验 hash b96c26…）
- 推送：preflight 全项通过（含 P6 本地 distill smoke，种子=真实 v2 teacher）
  → session id=340958490，shape=NvidiaTeslaT4，状态 RUNNING
- 挂载：ptcg-ckpt + ptcg-tensors + ptcg-code（push 后 metadata 已恢复，stage 默认值已还原 teacher）
- 预期产物：student_best.pt + output/model_student.npz（8 epochs distill，参考上轮 ~11min）
- 后续：npz 下回仓库根 → 本地 arena 验收 → pack.sh 提交（提交前查近期 Validation failed 原因）

## 2026-08-08 08:20 — T-001 Completed ✓
- 实现：train_v2.py 加 SegProfiler + make_blocked_perm + BatchPrefetcher workers/depth/block 参数
- 决策（按 design.md 分支表）：**prepare 占比是主瓶颈**（T4 场景）；本地 CPU 因 compute 慢掩盖 prepare，
  故用 bench_prefetch.py 隔离测纯数据管道
- 证据（500K 行热缓存，本机可信）：
  - A 全局随机：283.8ms/batch → **块读 w=1: 17.9ms (16x)**、**w=2: 10.0ms (28x)**、w=4: 12.4ms（GIL 回退）
  - pin_memory 保留（12.7ms vs 36ms，不 pin 反而慢）
- 全量 1.8M 本地不可信：14GB≈24GB RAM 内存压力触发页驱逐，与 T4(~13GB RAM) 冷读行为不同 → R-003 确认
- **决策：T-002 采用「物理连续块 + 块内 shuffle + 2 worker」**，默认 block=8、workers=2
- Blockers: 无

## 2026-08-08 — T-002 Started
- BatchPrefetcher 已改为多 worker + 块读；make_blocked_perm 验证：无重复无缺失、bs 窗口落在单块内
- 待办：正确性等价对比（T-003）、部署链路（T-004）、T4 实测（T-005）

## 2026-08-08 16:30 — teacher v3 运行完成（T-004 ✓ / T-005 证据）
- kernel daniel1547/ptcg-gpu-train-teacher-distill 15:38(+0800) 起跑，状态 COMPLETE
- 配置：stage=teacher，全量 1,815,639 decisions，BC 16 + AWR 10 epochs，prefetch w=2/d=4/block=8，T4x2 cuda
- 速度：冷启动 62s → 稳态 **26.6s/epoch**（v2 为 41s，再提速 1.54x）；全程训练 ~12min
- 指标：canary top1 **0.5437**（AWR best @ ep7）、fixed_test top1 0.5373、recall 0.4027/0.4061
  - 对比 v2 teacher：canary 0.5515 / fixed 0.5412 → v3 低 0.4~0.8pp（同 seed，差异来自块读采样顺序改变训练轨迹）
- 产物：reports/kerr_teacher_v3/ckpt/teacher_best.pt（sha256 e690f8…，与 v2 b96c26… 不同）
- 注意：v3 output 把完整 data/（~10GB npy）打进内核输出 → 下载极慢；建议后续把 data 排除在输出外
- 暂存状态：.kaggle_stage_ckpt 仍是 v2 teacher_best.pt（b96c26…）→ **蒸馏用哪版 teacher 待定**
- T-005 收尾缺口：本轮 profile=false，prepare 占比未直接测；需一次 --profile 短跑正式验收

## 2026-08-08 — 本地不推送内容完成
- 参数扫描（800K 行热缓存）：legacy 68ms/batch → 块读+多 worker 最优 ~10-13ms（5-7x）
  block=2-4 w=2-3 区间稳定；默认 block=8/w=2/d=4 在合理范围
- measure_tflops.py 完成并验证：本地 CPU distill = 0.35 TFLOPS（T4 上会显著更高）
- ptcg_code.tar.gz 重建：含新 train_v2.py + measure_tflops.py，hash 校验一致，嵌套 splits 结构保持
- run_experiment.py TRAIN_ARGS 同步：--prefetch-workers/depth/block + KAGGLE_PROFILE env 门控
- 待办（需 push Kaggle，待 notebook 跑完）：T-005 T4 实测、T-006 M2 放大、上传 ptcg-code dataset
