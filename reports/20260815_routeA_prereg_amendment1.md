# 路线 A 预注册修订 1：proposer opportunity 与 deployed divergence 分离

冻结时间：2026-08-15 13:40 CST
时序保证：本修订发生在任何 Route-A 本地 W/L episode 生成之前；只查看了 82 场既有
live state 上的无结果行为覆盖。原始输出保留：
`routeA_behavior_canary_20260815.json` 与 `routeA_behavior_canary_v2_20260815.json`。

## 触发原因

原预注册试图用 fallback-score gap 将 proposer opportunity 控制在 8–33/82。
两次 canary 均为所有阈值 82/82。第一次包含可互换 source serial 的仪器假分叉；修正后
仍为 82/82，因为 v22 对“同一进化贴到不同同名目标”“同一能量贴到不同同名目标”等
真实可选动作大量给出完全相同分数。故 score gap 是动作安全邻域，不是 exposure gate。

这不是 W/L 结果驱动的调参，也不改变 action proposer、特征或 promotion gate。

## 唯一修订

- 固定行为阈值为网格最保守值 `max_score_gap=25`；不再从网格选择。
- randomized training/smoke 允许 opportunity pool 宽，但继续每局最多一次干预、
  预分配 turn bucket 与 50/50 treatment。
- 原 `8–33/82` 口径移动到它本来要约束的对象：**训练完成后的 deployed trained head
  首次真实 override**。其 decision threshold 仍只在训练 folds 上按既定网格选择；
  82 场 live holdout 只做 PASS/KILL，不允许回看后调 threshold。
- trained head 必须合并 8–33/82，且旧/新 ref、两 seat、胜败均有覆盖；否则
  `BEHAVIOR_KILL`。matched random control 仍须 intervention-rate 差 ≤2pp。

除上述 opportunity/divergence 分离外，`20260815_routeA_prereg.md` 全部规则不变。
后续不得再次修改 proposer、gap=25、特征、decision-threshold 网格或行为 canary。
