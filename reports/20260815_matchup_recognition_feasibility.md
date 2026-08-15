# 可见信息 matchup 识别可行性

时间：2026-08-15 19:22 CST
输入：冻结的 82 场 exact-v22 PUBLIC replay；只读分析，不生成赛前候选。

## 裁决

**`GO_POSTSEASON`，但形态必须是高精度、可弃权、命中后锁存的 matchup router。**
全局强制分类不可行；unknown/conflict 必须保持 exact-v22。

## 严格 signature 上界

仅等待 archetype 的既有签名卡公开出现：

- turn 4：27/82 可识别，27/27 精确；
- turn 6：50/82 可识别，50/50 精确；
- turn 8：64/82 可识别，63/64 exact、64/64 与真实组合标签兼容；
- 全局结束：66/82 有预测，65/66 exact；稳定 exact 为65/82，中位 turn 5、P90 turn 7。

该方法很准但偏晚；12 场 `other` 本来就不应被强制映射，另有少量签名卡整局未公开。

## 旧 ref 学 marker、新 ref 盲验

从旧 ref 50 场的 26 个唯一 deck hash 学习 card marker，固定 support `>=2`、purity
`>=0.80`；在新 ref 32 场盲验：

- turn 1：8/32 预测，8/8 正确；
- turn 2：20/32 预测，20/20 正确；
- turn 4：24/32 预测，23/24 正确；
- 稳定正确 23/32，中位 turn 2、P90 turn 2。

剔除设计集重复 deck hash 后只剩18场，turn 2 仍为10/18覆盖且10/10正确；turn 4 为
12/18覆盖、11/12正确。最关键的目标腿在32场 holdout 中表现最好：Alakazam 6/6、
Lucario 6/6 都在 turn 2 前正确识别。

错误结构也很清楚：设计集中没有可学的 Archaludon marker，4场全部保持 unknown；
弱关联 marker 随回合累积后会把部分 other/Archaludon 错投为 Crustle，使 end precision
从 turn 4 的95.8%降到85.2%。所以运行时不应无限累计弱票，而应只允许高置信进化线/专属
卡触发一次锁存。

## 推荐的赛后 router 形态

1. `UNKNOWN` 起步；仅对冻结 whitelist 中的公开卡累计证据。
2. Alakazam 使用 Abra/Kadabra/Alakazam，Lucario 使用 Riolu/Mega Lucario 及专属引擎；
   通用能量、通用 Trainer 和纯相关性弱 marker 不得单独触发。
3. 达到高置信后锁存 archetype；后续冲突回 exact-v22，不从一个策略分支跳到另一个。
4. 首版只实现 `{Alakazam, Lucario}` 两个分支：命中后尝试历史上局部为正的 manual-only，
   其他类别与 unknown 全部 exact-v22。
5. classifier 与 policy 必须分开过闸，避免“识别准确”被误写成“策略有收益”。

## 赛后预注册门槛

- 按 opponent deck hash 分组切分，禁止同牌表跨 train/test；另留时间后移的 live holdout。
- A/L 在 turn<=2 的 precision `>=95%`，合计 coverage `>=70%`；conflict/fault 为0。
- router candidate 对 A/L 两腿分别独立 `n>=1024`，相对 exact-v22 `>=+3pp`；
  v22/Grim/Router/Dragapult/Archaludon/Crustle 各 `n>=512` 且任一 delta 不低于 `-2pp`。
- 任一门槛失败则 classifier 可保留为观测工具，但 policy candidate `winner=null`。

## 证据

- JSON：`experiments/runs/live_matchup_recognition_audit_20260815.json`
- SHA256：`37d33d3c235abbf3789be8dc563eb2ae60fbbc1c14aadec8d82f7c45bae1dac5`
- 原始 replay 归档 SHA：`62cc7a89425c8d807f06d83d106f30453209171b6d28db28b3b70eef076919d2`
- 可见信息不包含隐藏 hand/deck、未来状态或完整牌表；完整牌表只用于离线 gold/旧 ref
  marker 学习。
