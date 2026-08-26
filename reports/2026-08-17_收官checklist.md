# 8/17 截止锁定 Checklist（08-15 机制核查后重写）

> 官方在 8/17 07:59 CST 锁定新提交，但随后继续约两周 episodes，期末才形成最终榜。
> 07:59 的分数只是决赛期起点，不是 final score。

## 07:15 CST：双槽盘点

1. 拉 team submissions 与 leaderboard，只读确认 latest-2。
2. latest-2 必须均为 exact Grim v22：
   - 新独立实例 ref `55547740`；
   - 成熟托底实例 ref `55539446`。
3. 两件交付来源必须对应 archive SHA
   `599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`；
   新 ref 状态必须 COMPLETE/有效。
4. 页面无需手动勾选 final submission；若突然出现选择 UI 或规则文字变化，截图并暂停，
   不凭记忆操作。

## 07:30 CST：锁定记录

1. 保存 latest-2 refs、状态、individual score、团队 score/rank 与时间戳。
2. ledger 记“submission slots locked”，明确写 `provisional at deadline, not final score`。
3. 完成 HANDOFF 的提交槽状态；保留至少29分钟缓冲。
4. 正常情况下不再提交。只有新 ref ERROR 或 latest-2 出现非 v22 才升级人工复核；不得
   现场重包或提交实验件。

## 07:59 CST 之后：约两周 Final Evaluation

1. 平台禁止新提交，继续自动跑 episodes；不关闭仍负责只读采样的观测链路。
2. 每天一次按 ref 分开保存：score、PUBLIC n/W/L、对手均分、校正实力与 team rank。
3. 禁止把两个相同代码的 submission 分数拼成一条 bot 时间序列；它们是独立匹配路径。
4. 不以单日 spike/decay、名次抖动或截止瞬读改写策略结论。
5. 只有官方约两周阶段结束、榜单明确停止变化后，才写最终成绩 ledger 与 campaign
   复盘；不得在 8/17 晚或 8/18 晨提前称“最终分”。

## 冻结事实

- final slots：平台自动 latest-2；无手动选择控件。
- exact-v22 archive SHA：`599e19ae…b4c8bfcf`。
- 详细提交步骤：`reports/20260816_收官runbook.md`。
- 网页证据：`reports/20260815_决赛机制核查_kimi.md`。
