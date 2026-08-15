# 路线 A 立即立项 GO/NO-GO 备忘录

核算时点：2026-08-15 12:25 CST
冻结时点：2026-08-17 07:59 CST（官方 2026-08-16 23:59 UTC）
状态：`CONDITIONAL_GO / READY_AWAITING_USER_AUTHORIZATION`

## 裁决

- **完整多步 PPO / actor-critic：赛前 NO-GO。** 43.56 小时不足以偿还多轮训练、部署和分布外验证债。
- **一次干预/局、exact-v22 永久回退的 on-policy residual contextual-bandit：条件 GO。** 这是终局 W/L 驱动的真实策略改进实验，不是 replay BCRL，也不是把旧 guard 搜索换名字；但它只承诺完成一次严格止损的 pilot，不承诺一定产出 v23。
- 本备忘录只解除“能否立项”的技术疑问。**在用户明确回复“开工路线A”前，不启动训练、不修改 exact v22、不打包、不提交 Kaggle、不动 Automation。**

## 已核实的硬数字

- 毛窗口 `43.56h`；扣除每日提交操作 `0.5h`、最终打包/复验 `3h`、冻结缓冲 `2h`，净窗口约 `38.06h`。
- CPU episode 吞吐实测：结构 2×2 为 `576/107.321s = 5.37局/s`；additive 三臂为 `432/112.932s = 3.83局/s`；residual ES 为 `2160/845.306s = 2.56局/s`；单进程 exact-v22 mirror 为 `256/79.142s = 3.24局/s`。episode 生成是 CPU/工程串行瓶颈；小型线性头不需要 P100/T4×2。
- 固定 82 场 live replay 精确重放：`8,333` 次 ACTIVE、`8,251` 次决策、`0 mismatch`。其中 MAIN `context=0` 共 `3,679` 次；回合桶为 `576 / 566 / 1,145 / 1,392` 次。四桶分别覆盖 `82 / 82 / 79 / 72` 个 episode，且这些已覆盖 episode 全都有语义不同的合法替代动作。
- 独立样本单位仍是 **episode**，不是 3,679 个决策。最坏 `p=0.5` 下：单率 95% CI 半宽 ±3pp 需 `1,068` 局；两个独立臂差值半宽 ±3pp 需每臂 `2,135` 局；80% power 检出真实 +3pp 需每臂 `4,361` 局。四桶按实际暴露率修正后，功效批约 `36,432` 局；按 `2.5局/s` 为 `4.05h`，即使 logger 使吞吐降到 `1局/s` 也为 `10.12h`。
- 以上只是**桶平均效应的功效下界**，不能替高维 advantage 模型背书。因此首版固定为不超过 32 个预注册特征、L2 正则线性头；一旦需要大网络、多动作头或多次干预/局，自动转赛后 NO-GO。
- 82/82 replay 含完整对手 60 卡牌表，共 43 个唯一牌组；Grim 23、Alakazam 22、Lucario 8、Dragapult 6、Archaludon 5、Crustle 4、other/混合 14。**它们不含可执行对手 policy**，所以牌表只用于 live 行为 canary 和可见信息覆盖，不能用于改写动作后的 terminal rollout。

## 最小可行路线 A

1. 冻结 incumbent：candidate tree SHA `0319fee37419983ad7137c1db9d1ac7d67024cc692eb495d73e6f46fedd12ecc`；线上 archive SHA `599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`。所有实验只在新目录包装，不改 exact tree。
2. 挂载点位于 `apply_manual_guards()` 返回 `None` 之后、完整 hierarchy `choose()` 得出 exact action 之后、hard legality guard 之前；仅允许 `context==0`。manual guard、selection/protocol、StrategicMemory reset 和最终合法性检查全部保留。
3. 每个 episode 预分配一个回合桶，并预分配 `Z∈{exact,alternative}`。到该桶第一次出现合格 MAIN 状态时最多干预一次，此后整局回 exact v22。这样终局 ±1 只需归因到一个随机化动作，避免多步 credit assignment 混叠。
4. alternative proposer 不是任意合法动作：从 v22 现有评分/回退层取语义不同的最高安全 runner-up；排除强制协议、非法多选和明显灾难动作。若同一条 proposer 无法在 82 场 live canary 上产生 `8–33/82` 个首次分叉，判为 TOO_SPARSE/TOO_BROAD 并 KILL。
5. 只用当前 observation 中可见的信息，禁止使用 replay 的完整对手牌表、ref、结果或未来状态作为特征。固定 ≤32 维状态/动作差分特征，拟合带 `Z×feature` 项的 L2 logistic advantage head；episode-level split，四个 executable opponent legs 做 opponent-held-out folds。
6. 部署头为 stateless 纯 Python；低置信、特征缺失、异常或超时一律 exact fallback；每局仍最多改写一次。随机初始化对照臂用相同架构、相同 proposer，并在独立 calibration 集上匹配 trained head 的 intervention rate。

## 十个疑难点与止损答案

1. **窗口**：一次单发流程够；完整 RL 迭代不够。任何阶段晚于下方绝对时间闸即 KILL。
2. **终局奖励归因**：同局约 186 步导致强噪声；用“一局一次随机干预”消除主要混叠，禁止赛前扩成多次 override。
3. **统计独立性**：决策帧不能冒充样本；训练、置信区间和 gate 全按 episode 聚类。
4. **替代动作质量**：随机 legal action 会把探索损失当学习信号；只开放 deterministic safe runner-up，先过 live 分叉 canary。
5. **模型容量**：36k 只支持小型、预注册特征空间；若首版需要神经网络/搜索或在线多动作规划，直接归档赛后。
6. **对手漂移**：live 有 Dragapult/Archaludon/Crustle，却无可执行 pilot。四腿 held-out 只能防已知腿过拟合，无法证明 live 泛化；这是路线 A 最大剩余风险。
7. **信息泄漏**：完整对手牌表只能审计，不能喂模型；matchup 只准由当时已公开卡牌推断。
8. **random-control 公平性**：必须匹配 intervention rate，否则“训练头更好”可能只是少出手；不匹配即无效实验。
9. **fault/时限**：官方逐步限时尚未在本地文档找到精确数值；采用更严内部线：override 开销 p99 `<1ms`、正式批 0 fault、吞吐 ≥1局/s，任何失败回 exact 并 KILL 候选。
10. **提交槽位**：best-of-latest-2 下，8/16 **禁止“先重交 v22、再交 RL”**，否则成熟 v22 会出槽。12:00 裁决后只交一件：RL 全闸 PASS 则它占当天唯一一发；否则精确重交 v22。8/17 07:59 前不再交未经充分沉淀的新实验件。

## 绝对时间闸（收到授权后执行）

- **8/15 17:00 前**：完成 candidate wrapper、single-intervention logger、episode reset、legality/fallback 单测。任一不变量破坏或无法稳定提出 safe alternative，KILL。
- **8/15 19:00 前**：约 1,000 局 smoke；必须每局 ≤1 次干预、treatment 50/50、0 fault、吞吐 ≥1局/s、override p99 <1ms。否则 KILL。
- **8/16 05:00 前**：最多 36,432 局随机化数据与 cross-fit。要求估计策略 uplift ≥+3pp、至少 3/4 opponent-held-out folds 同向、任一 fold 不得低于 −5pp；否则 KILL。
- **8/16 07:00 前**：82 场 live behavior canary 首分叉 `8–33/82`、两 ref/两 seat/胜败均有覆盖；random-init control 的 intervention rate 匹配误差 ≤2pp；否则 KILL。
- **8/16 10:00 前**：四腿 screen 必须相对同批 incumbent 加权 ≥+3pp、exact-v22 主腿 ≥53%、任一跨牌组腿不崩 >10pp、trained head 相对 matched random control ≥+3pp、0 fault；否则 KILL。
- **8/16 12:00 前**：exact-v22 `n≥256` 主闸必须 WR ≥55%、相对同批 incumbent ≥+3pp、0 fault；随后 exact archive、双入口、60 卡、纯 Python 推理和打包复验。任一未完成即 `winner=null`，当天改为精确重交 v22。

## 最终授权边界

技术结论是 **CONDITIONAL GO**，但当前状态仍是 `READY_AWAITING_USER_AUTHORIZATION`。明确授权后只启动上述一次 pilot；失败即封口，不降闸、不追小样本尖峰、不修改 baseline、不占用第二个提交槽。

核算输入：`experiments/runs/routeA_feasibility_audit_20260815.json`（SHA256 `7f2d8f265988774878888ec4eb1b607dc0a033e1ebf61e7065b6dae6e0113235`）。
