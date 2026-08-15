# v22 live 校准、RNG 审计与稠密数值残差裁决

时间：2026-08-15 11:28 CST

状态：completed-negative。没有新 challenger，没有 materialize、打包或提交；exact-v22 归档与线上两实例未改。

## 结论

live 数据否决了重开 C-010 两个 guard 的理由；连续分数扰动在解决“行为是否真正暴露”后，仍未产出 W/L 更强件。因此 8/16 默认动作不变：只精确重交 archive SHA 599e19ae…b4c8bfcf 的 v22，不把今天的行为候选送上 Kaggle。

## 一、live 全量回放校准

固定使用 10:45 CST 快照，排除两个 validation episode：

- 旧 v22 ref 55499962：29-21，50 局，WR 58.0%。
- 新 v22 ref 55516725：23-9，32 局，WR 71.875%。
- 合并 52-30，WR 63.41%，Wilson 95% [52.61%, 73.02%]。
- 两实例差异 Fisher 双侧 p=0.245，不能宣称新实例更强。

82 个 PUBLIC replay 共重放 8,333 次 ACTIVE agent call。正确对齐是 steps[s] 的 ACTIVE observation 对 steps[s+1].action；锁定 exact-v22 顺序重放为 0 mismatch。

C-010 的两个目标 guard 在 live 也均为 0 events / 0 episodes。0/82 的单侧 95% 触发率上界是 3.587%，仍低于 544 局设计所需的 11.029%；82 局在真实触发率 11.029% 下仍见零次的概率仅 6.89e-5。同一仪器能重算出其他 manual guard 9 次有效命中，因此不是仪器整体失灵。

结论：contextual guard residual 不重开。两 guard 可列入赛后 dead-path cleanup，但不修改截止前的 exact-v22。

主要 live matchup 为 Grimmsnarl 14-9、Alakazam 15-7、Lucario 5-4、Dragapult 5-1、Archaludon 4-1、Crustle 2-3、other 7-5。Crustle 是唯一点估计低于 50% 的签名类，但仅 5 局，且历史诊断已指向结构性奖品交换，不足以在截止前重开专项规则。

实物：

- experiments/runs/livecal_55499962_20260815_1045CST.json
- experiments/runs/livecal_55516725_20260815_1045CST.json
- experiments/live_v22_replay_audit.py
- experiments/runs/live_v22_replay_audit_20260815_1045CST.json
- experiments/runs/live_v22_replays_20260815_1045CST.tar.gz（82 replay，11 MB，SHA256 62cc7a89425c8d807f06d83d106f30453209171b6d28db28b3b70eef076919d2）

## 二、采样器与 RNG 口径修正

live_episodes_probe.py 现默认跟踪新 v22 ref 55516725，保存 episode type/state、公开/验证标志、双方 state/team id，WR 默认排除 validation，并使用独占 lock + 原子替换。probe_wr_watch.py 的默认 ref 已与主探针同源，JSON 也改用同一写入协议；11:11 smoke 为 34 PUBLIC、23-11、WR 67.65%。这是后续新快照，不追溯混入 10:45 固定分析。

native RNG 审计的硬结论是：本地 Python/ABI 没有 shuffle seed setter；random.seed/seed0 只固定 Python 侧随机，dylib 使用 random_device。所以旧脚本中的“配对种子/CRN”措辞已降级，后续只能称 blocked independent trial。ABBA/BAAB 只平衡座位和粗时间块，不能重放相同洗牌。

## 三、乘法连续参数闸

审计只找到三个真正位于 exact-v22 活跃路径的数值族：资源时机、手贴时机、目标 asset-vs-HP clock。target_evaluator.py 虽有 energy×40，但没有调用者，本轮没有把死分数当成活参数。

在 82 局 live replay 上运行 12 个 ±5%/±10% 变体，并按预注册对过广的 ±5% 方向只允许一次 ±2.5% 缩小：

- 资源 ±2.5% 仍在 57/82 和 70/82 局分叉。
- 手贴 ±2.5% 仍在 58/82 和 68/82 局分叉。
- 目标 asset ±5%/±10% 仅 0–2/82 局分叉。

因此乘百分比的资源/手贴参数是全局策略替换，不是残差；目标 asset 是死区。没有候选进入 W/L。

实物：

- experiments/v22_live_param_exposure.py
- experiments/runs/v22_live_param_exposure_20260815_1045CST.json

## 四、分样本有界加性残差

新参数化在运行前先写入预注册：只对相应 MAIN action 加固定分差，网格为 ±10/±25/±50/±100；旧 ref 50 局用于设计，新 ref 32 局作完全盲验。

设计集选出三个 offset：

- resource −10：5/50，但盲验 0/32，淘汰。
- resource +25：20/50，盲验 11/32，合并 PASS。
- attachment +50：19/50，盲验 8/32，合并 PASS。

这一步只证明后两件在 live 分布上有适中行为暴露，不证明有益。原 replay 的胜/负仅作覆盖标签，没有用作反事实 reward。

实物：

- reports/20260815_v22_additive_residual_prereg.md
- experiments/v22_live_additive_screen.py
- experiments/runs/v22_live_additive_screen_20260815_1045CST.json

## 五、四腿 W/L 裁决

回放闸合格的两件与 exact-v22 incumbent control 各跑 144 局：v22 64 / Router 32 / Alakazam 16 / Lucario 32，权重 0.45/0.15/0.30/0.10。三组全部零 fault，每腿座位完全平衡。

- resource +25：对 v22 33-31，WR 51.56%；加权 64.45%，比 incumbent 低 1.28pp。
- attachment +50：对 v22 29-34-1，WR 46.03%；加权 63.06%，比 incumbent 低 2.68pp。
- incumbent control：对 v22 31-32-1，WR 49.21%；加权 65.74%。

两候选都未达到预注册的 n=256 资格条件（v22 WR 至少 53%、加权相对增量至少 +3pp），所以主闸没有运行，winner=null。

实物：

- experiments/v22_additive_wl_gate.py
- experiments/runs/v22_additive_wl_gate_20260815.json

## 六、方法收益与剩余动作

本轮新增的可靠认识：

1. live replay 可以对 exact-v22 做 100% 动作复现，可作为 on-distribution 行为暴露闸。
2. “触发很多”不等于“有改进信号”；它只解决可测性，终局 W/L 仍是必要闸。
3. 大绝对优先级上的 ±5% 不是小扰动。分样本盲验也成功拦下了设计集假合格的 resource −10。
4. 迄今所有 v22 局部改动都未打赢 exact-v22；当前最强提交仍是已有 v22。

截止前只保留三项工作：

- 继续对两个 v22 ref 分开拉 PUBLIC episodes；报告 WR 时同时报告对手强度/牌组，不拼接不同 submission 的分数轨迹。
- 8/16 上交前核查 latest-2 中至少一个 v22 已充分沉淀；没有过闸 challenger 时精确重交 v22。
- 8/17 按已有 checklist 收官；不重开 NN/search、不扩 guard 样本、不降闸、不追 offset。

赛后若继续，优先投资 native engine seed 注入/可重放 shuffle，再将 live first-divergence 作为每个数值候选的前置闸。
