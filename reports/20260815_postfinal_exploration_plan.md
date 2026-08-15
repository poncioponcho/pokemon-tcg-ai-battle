# 赛后方向只读探索计划（结果查看前冻结）

冻结时间：2026-08-15 19:14 CST
用途：只生成赛后假设；不得重开已被 `TRAINING_KILL` 封口的 Route A pilot，也不得据此
生成、打包或提交赛前候选。

## A. Router 正切片归因

固定输入为 Route A 正式采集 SHA
`ea7be6e7a948c211f132f4b6b79fee61c3b49743acc50861a60b026f380ce241` 与正式训练输出
SHA `ae140f957cc5484d3fa417e1627e1e60d95b27053f2e9c029c54a71724feae65`。

1. 完全复现 opponent-held-out Router fold：只用非 Router learning episodes 拟合相同
   L2 logistic response model，并在训练腿选择冻结阈值网格；复现失败则分析无效。
2. 固定分层只有四组：预注册 turn bucket、alternative action type、
   exact→alternative action pair、score gap 桶 `{0,(0,5],(5,15],(15,25]}`。
3. 每层同时报告原始随机处理均值差与 held-out policy IPS uplift/95% 正态区间；
   分解贡献按该层样本占 Router fold 的比例计算。
4. exact→alternative pair 少于 200 个 episode 只保留原始 JSON，不进入摘要排序。
5. interaction coefficient 只作相关性解释，不称为因果特征。所有切片均为事后探索，
   不做多重比较后的显著性宣称，不据正切片改阈值或追跑。

## B. 可见信息 matchup 识别

固定输入为 82 个 PUBLIC replay（旧 ref 50、新 ref 32）及归档 SHA
`62cc7a89425c8d807f06d83d106f30453209171b6d28db28b3b70eef076919d2`。

1. 运行时输入仅为截至当时 observation 已公开的对手 active/bench/discard、其公开
   evolution/tool/energy cards 与对手放置的 stadium；忽略隐藏 hand/deck、未来状态和
   replay 完整牌表。
2. 完整牌表只用于离线 gold label 和旧 ref marker 学习。
3. 基线为既有 archetype signature IDs 的累计可见识别；报告 turn
   `0,1,2,3,4,5,6,8,10,end` 的 coverage、precision、exact accuracy 和混淆矩阵。
4. 学习型 marker router：仅旧 ref 50 局构造 card→primary-archetype marker，要求
   design deck support `>=2` 且 purity `>=0.80`；在新 ref 32 局盲验，并另报剔除旧 ref
   重复 deck hash 后的 novel-deck 子集。预测至少命中一个 marker，得分并列则 unknown。
5. “稳定识别回合”定义为首次预测正确且此后所有可观测回合不再改变；结果只裁决
   赛后 matchup router 的可行形态，不授权赛前候选。
