# 2026-08-16 彩票分支收官 runbook

> **16:25 最终覆盖：** Roman live 后续回落，用户批准以一发冻结 exact-v22 替换其
> 槽位。新 ref `55547740` 已 COMPLETE；最终 latest-2 为
> `{55547740新v22, 55539446成熟v22}`。以下历史彩票分支不再执行。禁止第二次成功
> 提交；余一发仅用于 ERROR/失效恢复。执行记录见
> `reports/20260816_exact_v22_slot2_duplicate_submission.md`。

本文件覆盖 `reports/20260816_收官runbook.md` 中“只允许双 v22”的旧分支。平台仍为
自动 `best-of-latest-2`，截止为 2026-08-17 07:59 CST，之后约两周继续对局。

## 当前目标

锁定时必须是 `{exact-v22, 当时证据最强的一张彩票}`。exact-v22 是不可丢的地板；
第二槽追求上限。短暂探索可以挤出 v22，但只允许在还有明确恢复额度和时间时发生。

冻结件：

- exact-v22：`artifacts/grim_v22_final/submission.tar.gz`
  SHA `599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`
- 胡地 v5：`artifacts/alakazam_msato_lottery_v1/submission.tar.gz`
  SHA `83372cfecfe0308a129c9e11b87e4730fa204251ed23f8d8d599a8cf035993a9`

## 分支 A：只提交胡地彩票

胡地 COMPLETE 后 latest-2 应为 `{exact-v22, 胡地-v5}`。若长毛巨魔研究没有形成
更好彩票，保持该组合直到截止，不需要为了形式再重交 v22。

## 分支 B：随后提交长毛巨魔彩票

提交 Grim-X 会让 latest-2 暂时变为 `{胡地-v5, Grim-X}`，因此 exact-v22 会出槽。
只有同时满足以下条件才允许：

1. Grim-X 已通过 60 卡、双入口、零 fault、确定性归档和 exact-archive smoke；
2. 当日仍保留至少一次 exact-v22 恢复额度；
3. 距截止至少留出 Kaggle validation ERROR 处理缓冲；
4. 提交前已记录胡地与 Grim-X 的选择规则，不以单局或瞬时分拍板。

Grim-X 获得最小 live 反馈后，截止前最后一发必须精确重交 exact-v22。最终 latest-2
变为 `{Grim-X, exact-v22}`，胡地票出槽。若 Grim-X ERROR 或工程闸失败，不提交或用
同一归档仅重试一次，最终保留 `{胡地-v5, exact-v22}`。

## 彩票选择口径

认知层不把早期分数尖峰当真值。行动层按以下顺序挑第二槽：

1. validation COMPLETE 且无 runtime fault；
2. 公开局数、对手均分、W/L 与置信区间同时报告；
3. 同时段对手强度校正后明显领先者优先；
4. live 证据仍无法区分时，选择上限来源更直接、行为复现更扎实的一件；
5. 无论哪张票，exact-v22 都必须留在锁定 latest-2。

## 提交前后硬检查

每次上传前：回读当前 team submissions、核对 archive/manifest SHA、确认额度和恢复路径。
每次上传后：保存返回 ref，立即 inspect；+5/+15/+60 分钟只读检查状态、latest-2、
公开 episodes 和团队榜。COMPLETE 后不得现场改包；ERROR 只允许同一 SHA 重试。

## 绝对停止条件

- SHA、manifest、60 卡或 entrypoint 任一不符；
- candidate/opponent fault 非零；
- 不能证明截止前可恢复 exact-v22；
- submit 未返回 ref，或 inspect 无法确认状态；
- 2026-08-17 07:30 CST 仍未完成 exact-v22 托底恢复。

07:30 后不再追新票，只做 latest-2 和 COMPLETE 状态封口。
