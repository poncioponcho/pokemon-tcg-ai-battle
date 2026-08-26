# 下一场 BC 保真决定性实验 Runbook（governing document）

> 落盘：2026-08-13 晚；**v2 修订同日 19:30**——C-0 探针执行完毕，原「更正1」（蒸馏 −28.5pp 并列瓶颈）**被实证证伪**，全文已按 C-0 终版判读重写。地位：下一场 RL/克隆 campaign 的执行手册——fresh session 接手先读本文件，再读 HANDOFF「下一场方向」条。
> 依据：08-13 BC 保真解剖三探针（ledger `bc_fidelity_autopsy_phase12_verdict`）+ C-0 provenance 审计（ledger `c0_provenance_verdict`）。所有关键数字均经仓库/本地复验，非转述。

---

## §0 一页判读（TL;DR，C-0 后终版）

- **瓶颈 ①= 模型类 × 特征表示**（in-distribution）：teacher 0.5494 / student 0.5372，中局行为上限 0.7337——headroom ~19pp。这是**主战场**（Track A/B）。
- **瓶颈 ②= 部署保真**（compounding error / covariate shift）：in-dist 0.54 → 实战 ~0.40。Track D（DAgger/online）。表示层治不了它，它也不替表示层背锅。**D0 已实体化这条（08-13 21:00）**：LB student（LB canary 0.5372）与 h384d1（跨 LB 分布仅 ~0.30）同环境实战居然互有胜负（+3.5pp vs 规则 / −6.8pp vs first）——**in-dist canary 优势不转化为部署优势**，这是 Track D 存在的最硬证据。
- **蒸馏是健康的**：teacher 0.5494 → student 0.5372 = **−1.2pp canary / −1.5pp fixed**（同 canary 成对实测）。日报挂了五天的 student 0.2633 是 **08-08 CPU 冒烟报告（limit=30000、distill 1 epoch/5.45s）的陈旧引用**，08-09 云端全量 run（8 蒸馏 epoch）早就产出了 0.5372 的 student——**测量错了，不是蒸馏坏了**。原「蒸馏 −28.5pp 并列瓶颈」证伪，Track C 降级。
- **里程碑锚 student canary = 0.5372**（新基线，C-0 本地精确复现云端日志）；上限锚中局 0.7337。
- **本机训练不可行已实证**（MPS 1.9s/batch、60 epoch 三連掐）；评测可本地（CPU 前向 memmap，分钟级），训练一律云 GPU。

---

## §1 锚定指标与里程碑（C-0 重校准）

| 层级 | 指标 | 现状（C-0 后） | 参照/上限 | 出处 |
|---|---|---|---|---|
| **主里程碑** | **student canary top-1** | **0.5372** | 阶段门：≥0.55 → 0.65 → 0.70（中局上限 0.7337） | 云 log `reports/kerr_selfplay/output/train_v2.log` + 本地复验精确一致 |
| 参照 | teacher canary / fixed top-1 | 0.5494 / 0.5410 | 行为上限锚 **中局 0.7337** | 同上（成对同 canary） |
| 部署现实（D0 同环境矩阵，08-13，n=2000/格，nn_first，宿主=根 main.py v24.8/F1 系+v4 FINAL deck（**更正：非 config A/PIVOT 态**，根系无 flag 机制），invalid=0） | LB student vs first / vs v23_2_rules / vs random | **0.4445 / 0.769 / 0.896** | h2h 对照见下 | `experiments/bc_fidelity/arena_report-d0_lb_nnfirst.json` |
| 部署现实（drift 对照，同批） | h384d1 vs first / vs v23_2_rules / vs random | **0.513 / 0.734 / 0.923** | 自身历史 0.3744/0.4024 → 今 0.513/0.734 = **arena 环境漂移（宿主牌组升级），历史基线作废** | `experiments/bc_fidelity/arena_report-d0_h384d1_nnfirst.json` |
| 部署现实（H2H 判读） | LB − h384d1 | **+3.5pp vs 规则 / −6.8pp vs first / −2.7pp vs random** | in-dist canary 优势（0.5372 vs 跨分布 ~0.30）**不转化为**部署优势；vs first 是全栈共性短板（规则 0.37 / LB 0.44 / h384d1 0.51） | 同上两报告 |
| 部署现实（D0e 新开格，vs 真 config A 镜像 `configA_pristine_79653e2c63b1`，同宿主 n=2000，avg_turns 79-83 非 donk） | LB student / h384d1 / v24.8 纯规则 | **0.0385 / 0.053 / 0.0615** | 「克隆打得过最好件吗」→ **打不过**；config A 镜像对 F1 系全三脑 94-96% 碾压 = 真实强度差；v23_2 稻草人实锤（同三脑 vs 旧镜像 0.73-0.77） | `experiments/bc_fidelity/arena_report-d0e_*.json` |

**判读纪律**：
1. 任何实验报告必须同时报 teacher 和 student 双 canary（虽然蒸馏现健康，单报 teacher 仍会掩盖未来回退）。
2. **canary 治理（C-0 新教训）**：`refresh_rolling_canary` 会在评测时按最新捕获剧集**重写 live manifest**（08-13 19:13 已发生一次非预期滚动，新旧 canary 0/100 重叠）。纪律：
   - 参照 canary 固定为 `experiments/bc_fidelity/canary_snapshot_20260809_cloud.json`（与全部历史数字可比的唯一基准）；
   - 时效检查用 `experiments/bc_fidelity/canary_snapshot_20260813_rolled.json`；
   - 一切评测走 `experiments/bc_fidelity/eval_lb_student.py --canary-json <快照>`，**禁止**调用会触发 refresh 的路径。
3. 里程碑不用 vs first / vs rules 胜率（matchup 难度混杂）；胜率只做最终部署现实检查。
4. 诚实 headroom：0.54 → 中局 0.73 ≈ **19pp**，不用 33pp（全局 0.8754 含套路化开局）。

---

## §2 已固化的判读（勿重新审理）

| # | 命题 | 证据 | 产物 |
|---|---|---|---|
| F1 | 多模态**不是**约束 | 1,815,639 帧状态哈希分组：LB 真人一致性 0.8754 ≈ 规则对照 0.8836；分层 t0-2=0.9643 / t3-10=0.7337 / t11+=0.7685 | `experiments/bc_fidelity/multimodal_probe.py` → `experiments/runs/multimodal_probe.json` |
| F2 | 零泛化差距 = **纯欠拟合** | v1 教师 train 0.5407 = fixed-test 0.5410 = canary 0.5498 | `experiments/runs/train_test_gap.log` |
| F3 | 多 epoch **到不了 0.65** | 边际价值 BC6 0.5207→AWR20 0.5332/0.5432（平台）；从零 epoch1 即 0.4709 | `experiments/runs/long_train_probe.log` |
| F4 | 管线本身不坏 | 同管线克隆规则 self-play 简单函数达 0.7735 | ledger `mainline_b_gates` |
| F5 | 数据锚本来就是对的 | 1.8M 决策帧，LB 高分段真人 replay（manifest 6873 条：rank≤500 占 42%、≤1500 占 92%，含 rank-20 @kdcyberdude 1079.7） | `inference/dataset/manifest.csv` |
| F6 | 奖励函数**不是**瓶颈（三阶） | 稀疏 ±1 + batch-mean 基线 = 过滤式 BC；AWR 仍 +13pp（0.40→0.53） | `selfplay_harvest.py:135/196`、`train_v2.py:334-336` |
| F7 | 本机长训练不可行 | MPS 前向 ~1.9s/batch；60 epoch 探针三次被掐 | `experiments/runs/long_train_probe.log` |
| **F8** | **蒸馏健康（−1.2pp），日报 0.2633 是测量 artifact** | 日报源头 = `inference/dataset/data/train_v2_report.json`（08-08 17:26，CPU，limit=30000，distill 1 epoch/5.45s）五日逐字节同值；云端全量 run（08-09，limit=0，distill 8 epoch）student best 0.5372@ep7；本地复验：student 0.5372 / teacher 0.5494（cloud-era canary，参数量断言 1,993,537 / 9,532,033 全过）；rolled 新 canary 上 student 0.5560（时效无衰减） | `experiments/bc_fidelity/eval_lb_student.py`、`canary_snapshot_20260809_cloud.json` |

---

## §3 原两条「更正」的终局（C-0 裁决）

### 更正 1（蒸馏 −28.5pp 并列瓶颈）→ **证伪，溯源链完整**
- 数字本身真实（daily report 08-09→08-13 确实印着 0.2633），但**溯源到 08-08 17:26 的 CPU 冒烟 run**：`limit=30000`（1.8M 的 1.7%）、`epochs_bc=1, epochs_awr=0, epochs_distill=1`（5.45 秒）。学生根本没被训练，0.2633 是「5 秒蒸馏」的必然结果。
- 08-09 云端全量 run 的真实蒸馏曲线：0.4856→0.5372（8 epoch，ep7 best）。**该 student 自 08-09 起就躺在 `reports/kerr_selfplay/output/model_student.npz`，全队却以为它是 0.26。**
- 附带修正：LB student 参数量 **1,993,537 ≈ 2M 顶格**（输入投影 4490×384 占 ~1.73M）——「996K 只用了半预算」是 rules 侧 h384d1 的旧印象，对 LB 特征 layout 不成立。宽度扩容**没有**余量；容量增长只能走输入特征重设计（并入 Track A）。
- 蒸馏损耗随数据代际「劣化」的旧叙事（−2.3→−12.2→−28.5）改写：self-play 的 −12.2pp 是真（ledger `mainline_b_gates`），LB 的 −28.5pp 是假；LB 真实值 **−1.2pp**，三代里最健康。

### 更正 2（表示层治不了部署塌方）→ **成立，维持**
- in-dist train=test=0.54 是同分布结论；实战 ~0.40 的差是 compounding error / covariate shift。fidelity→winrate 放大已有量化（35% 动作偏差→27% 胜率，ledger `mainline_b_gates`）。
- 分工不变：Track A/B 抬 in-dist top-1 向 0.73；Track D 抬实战向 top-1。两轨都成功才算赢。

### 小更正（headroom 锚中局 0.73）→ **成立，维持**（§1 纪律 4）。

---

## §4 实验轨道（C-0 后重排）

### Track C-0（✅ DONE 08-13 19:30，本地，零额度）
结论见 F8/§3。产物：`eval_lb_student.py`（无 canary 突变 v2）、两版 canary 快照、ledger `c0_provenance_verdict`。

### Track A（主战场，云 GPU）：表示层 ablation 矩阵
假设：4400+90 扁平特征表达不出卡牌关系与算术结构；且 student 2M 预算的 87% 被输入投影吃掉——特征重设计同时是「容量轨」。
- [ ] A1 关系化卡牌特征（zone×card 交互、attacker↔defender 对位）
- [ ] A2 能量/血量算术显式化（差值、比值、「能否 retreat」「差几能出手」直接喂入）
- [ ] A3 序列记忆（最近 N 回合事件摘要 / 简易 recurrence）
- **协议**：每维单独开关 × 同数据 × 200 epoch × 固定参照 canary；报 teacher+student 双 canary。
- **过/杀**：单维 +≥3pp teacher canary 保留；<1pp 杀。组合 teacher ≥0.65 → A 成功；组合仍 <0.60 → 表示层判死，转搜索 oracle。

### Track B：模型结构（A 出结果后按需）
- [ ] B1 选项结构化输出；B2 牌组上下文嵌入。过/杀同 A 口径。

### Track C（降级：健康，仅微调）：蒸馏
- 现状已 −1.2pp，**不开大活**。仅当 Track A 换了特征 layout 后重跑蒸馏基线；temp/alpha（3.0/0.3 未调过）顺手一扫即可。
- rules 侧「student 直接 BC 0.7418>蒸馏」先例的 human 重做降为可选（蒸馏已健康，动机大幅减弱）。

### Track D（并列主战场）：部署保真
- [x] **D0（✅ DONE 08-13 21:00，三格矩阵+drift 对照，n=2000/格）**：**判读 = LB 克隆没有部署优势，部署保真瓶颈实体化**。同环境 H2H：LB student +3.5pp vs v23_2_rules / **−6.8pp vs first** / −2.7pp vs random。关键警示：h384d1 自身同日复测 vs rules 0.4024→0.734、vs first 0.3744→0.513——**arena 环境随宿主牌组/规则升级漂移，一切历史 arena 基线作废，今后任何 arena 对比必须同批跑 drift-control 格**。两 student vs random 均 <99% sanity 线（0.896/0.923，invalid=0 非损坏，raw NN 复利失误）。caveat：NN 只覆盖 `_ST_MAIN/_ST_CARD/_ST_ATTACK` 三类 select，其余走宿主规则；**宿主更正：根 main.py = v24.8/F1 系（sha 9efb8606，无 flag 机制——RETREAT_PIVOT 不存在于该文件）+ v4 FINAL deck（01330d50），非 config A/PIVOT 态**（ledger#130 早有明断：根=v24.8，config A=submission_baseline/）。产物：`arena_report-d0_{lb_nnfirst,h384d1_nnfirst,smoke}.json`。
- [x] **D0e（✅ DONE 08-13 22:30，vs 真 config A 镜像）**：镜像 `configA_pristine_79653e2c63b1`（行为等价 pristine：探针件 411d9dff 翻 PIVOT→False+内联 deck 2a541d7b 断言+libcg sha 7a157f04 针+registry 登记；非逐字节 459cf97——盘上无此件，声明见文件头）。结果：LB 0.0385 / h384d1 0.053 / v24.8 纯规则 0.0615（n=2000，invalid=0，avg_turns 79-83）。**判读：config A 镜像碾压 F1 系全三脑 = 真实强度差；「克隆打得过最好件吗」打不过；旧 v23_2 镜像稻草人实锤。宿主真 config A 化（submission 系挂 NN）是下一场活。**
- [ ] **D0e-tail：configA 宿主挂 NN 移植清单（08-13 立项，下一场开局执行）**
  - **科学问题与判读规则（先写死，防过度解读）**：NN 在 config A 宿主上仍只覆盖 `_ST_MAIN/_ST_CARD/_ST_ATTACK` 三类 select，其余走 config A 规则——此格本质是「**config A 政策 + NN 微调叠加 vs config A pristine**」的干净消融。预期锚：config A 大概率仍赢（NN 叠加 ≈ 中性至微负）。**判读指标 = Δ = WR(NN 叠加宿主) − WR(纯 config A 宿主无 npz，同批 drift-control 格)**：Δ>+2.2pp → 叠加有助；|Δ|≤2.2pp → 中性；Δ<−2.2pp → 叠加有害。**不判「能不能赢 config A」**。
  - **移植步骤**：①审计根 main.py NN 块（~L3630+：`_NN_MODE` env / npz loader / 4490 编码器 / `_NN_SEL_TYPES` 门控）的**编码器输入契约**（根系 dict-obs vs submission 系 dataclass-obs——本清单的主要工程量，优先在 raw obs_dict 上跑编码器与 `to_observation_class` 平行，避免双路真源）；②派生新副本：以 `configA_pristine_79653e2c63b1.py` 为基（已行为 pristine+内联 deck+arena 短路），内容哈希定名 `configA_nnhost_<sha12>.py`——**禁止改 `submission_baseline/` 一个字节，禁止改已注册镜像**；③移植 npz loader+前向（numpy f16，obs 形态无关部分）+ env 门控+异常规则兜底；④冒烟：可导入、`agent({'select':None})` 返回内联 deck、n=100 vs random invalid=0；⑤挂载：arena_runner 加 `--main` 最小参数（3 行）指向新宿主，或等效挂载点；⑥三格同批：NN 叠加宿主 vs 镜像 + 纯 config A 宿主 vs 镜像（drift-control）+ h384d1/LB 双 npz 轮换，n=2000/格，按上面 Δ 口径判。
  - **纪律边界**：inline deck+逐表断言（#127）；若新宿主也冻为对手则 registry 登记+sha 校验；一切对比同批 drift-control（§9-7）；产物落 `experiments/bc_fidelity/`。
- [ ] D1 DAgger 分歧重标回流；D2 online self-play 回流。
- **判读**：nn_first h2h >0.50 = 成功；用实战指标判 D，不用 canary top-1 判 D。

---

## §5 终审协议（训练一律上云）

- 平台：云 GPU（先例 kernel `daniel1547/ptcg-gpu-train-teacher-distill`）。本机只做评测（CPU 前向 memmap 已实证分钟级）。
- 统一协议：同一 1.8M 决策帧、同 split、200 epoch、**参照 canary 快照固定**（§1 纪律 2）、双 canary 报告 + 方差。
- 消融纪律：一次一维；组合可回溯单维；对照组 = 现 teacher 0.5494 / student 0.5372（C-0 基线）。
- 产物规范：`experiments/runs/` + ledger 追加（JSON 校验）+ 日报引用。**日报生成器必须改读最新全量 run 的报告**——08-08 冒烟报告被引用五天是本次事故的源头。

## §6 数据与资产清单

| 资产 | 路径 | 备注 |
|---|---|---|
| 决策帧 tensor | `inference/dataset/data/*.npy` | 1,815,639 帧；states_u8 8GB、opts 6GB；layout 4400+90 |
| 数据清单 | `inference/dataset/manifest.csv` | 6873 条 replay 元数据 |
| v1 teacher（LB 真人） | `reports/kerr_selfplay/ckpt/teacher_best.pt` | canary 0.5494 / fixed 0.5410（C-0 复验） |
| **v1 student（LB 蒸馏，可部署）** | `reports/kerr_selfplay/output/model_student.npz` + `ckpt/student_best.pt` | **canary 0.5372**；1,993,537 参数（2M 顶格） |
| v3 teacher/student（self-play 系） | `reports/kerr_selfplay_v3/...` | teacher 0.7735 / student 0.6515；跨 LB 分布仅 0.2982 |
| 参照 canary 快照 | `experiments/bc_fidelity/canary_snapshot_20260809_cloud.json` | 与全部历史数字可比 |
| 时效 canary 快照 | `experiments/bc_fidelity/canary_snapshot_20260813_rolled.json` | 100 全新剧集 |
| 评测器（无突变） | `experiments/bc_fidelity/eval_lb_student.py` | `--arch student\|teacher --ckpt ... --canary-json ...` |
| 今晚探针脚本 | `experiments/bc_fidelity/{multimodal_probe,train_test_gap,long_train_probe}.py` | |
| student 直接 BC 训练器 | `experiments/student_bc_probe.py` | 注意硬编码 data-selfplay；用于 LB 需改数据路径 |

## §7 执行顺序与总判据

1. **D0**（本地 arena，便宜，先知道部署基线）→ 2. **Track A**（云，主战场）与 **Track D1/D2** 并行 → 3. Track B 按需 → 4. Track C 仅随 A 的特征变更重跑基线。
- **总成功判据**：student canary ≥0.65（新表示层下）且部署 nn_first h2h >0.50。
- **总失败判据**：A+B 组合 teacher 仍 <0.60 → 表示层/结构判死，主题转搜索 oracle（ledger `nn_direction_decision` deferred 选项）。

## §8 开放问题

- D0 后新问题：LB student 为何 vs first **反劣** 6.8pp？假设方向：人类示范里罕有 dumb-greedy 对手（克隆学不到反 greedy 剥削），self-play 数据反而覆盖。这直接呼应规则 agent 自身的 vs_first 0.37 洞——**vs first 是全栈共性短板**，值得 Track D 立项专项（反 greedy 防御训练/数据增广）。
- v3 self-play teacher 跨 LB 分布仅 0.2982——self-play 数据对 human 分布迁移性存疑；D2 online 回流的数据分布设计要小心。
- 为何 self-play 蒸馏 −12.2pp 而 LB 仅 −1.2pp？（假设：self-play teacher 更尖锐/自信；或 quality 子集更小。）不影响行动，记录备查。
- harvester 仍在跑——开训前冻结数据版本作对照；canary 治理按 §1 纪律 2 执行。

## §9 禁忌（违者重读 §2/§3）

1. 不重新审理奖励函数（F6）。
2. 不用 vs first / vs rules 胜率当里程碑。
3. 不在本机跑 epoch 级训练（F7）。
4. **不引用日报的 student 0.2633**——它是 08-08 冒烟报告的陈旧引用（F8）；蒸馏已健康，不许再开「修蒸馏」大活。
5. 评测不触发 `refresh_rolling_canary` 写路径（用显式快照）。
6. 不动 `submission_baseline/` 一个字节；本 runbook 与当前 campaign 提交纪律正交。
7. **arena 对比必须同批跑 drift-control 格**（D0 实证：宿主 lineage+牌组差异让 h384d1 自身基线漂移 +33pp/+14pp；不跑对照 = 把环境差异当模型进步写进结论）。另：**vs-rules 基准一律用 `configA_pristine_79653e2c63b1`**（08-13 已重冻，行为等价 pristine+断言电池过）——v23_2_rules 稻草人实锤（同三脑 0.73-0.77 vs 0.04-0.06），旧镜像仅留作 drift 考古。
