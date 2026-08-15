# v22 自生成 on-policy 残差 RL：第一轮裁决

时间：2026-08-15 09:50 CST
状态：`completed-negative`；没有形成可提交 challenger，线上 v22 与归档均未修改。

## 问题定义

这轮不是旧 BCRL。旧线从官方 replay 反推行为；本轮冻结线上最强提交 v22，
由本地官方 `cg` 引擎生成候选自己的对局，并只用终局胜负作为优化回报。

在截止前不从零训练 NN/PPO。采用保守的 episodic black-box residual ES：

- genome 只允许关闭 v22 的一个到三个窄 tactical guard / planner layer；
- 被关闭的层自动回退到 v22 已验证的下层规则，合法性兜底不变；
- population 自己生成对局，按终局 W/L 排序；
- screen 与 confirmation 使用独立 stochastic batches；
- 脚本只输出 genome，不自动改包或提交。

基线固定为 `candidates/grim_v22_final/`，对应线上归档 SHA256：
`599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`。

## 先修测量仪器

`scripts/candidate_h2h.py` 原先只在整批开始时发送一次 `select=None`。v22 用这个
启动观测清空 `_HISTORY` 与 `StrategicMemory`，因此旧 runner 会让上一局最后八个动作
进入下一局开场。现已改为每局显式请求 deck/reset，并在报告写入
`episode_reset=select-none-before-every-game-v1`。历史报告不追溯改写；本轮所有正式数据
均使用新语义。

同时，runner 的省略 `--opponent` 默认锁已从旧 retreat 更新为 exact v22
（main `d80d33c5…`、deck `92b92bac…`）；旧 `submission_baseline/` 目录保持冻结，
没有被覆盖。

原生引擎不暴露 shuffle seed；CLI seed 只能控制 Python 侧随机策略。因此同 seed 重跑
仍是独立随机批次，本轮没有声称 paired replay。

## Population screen

- 40 个 genome：incumbent、27 个单点消融、12 个二至三项组合。
- 对手与权重：v22 45%、Router 15%、Alakazam 30%、Lucario 10%。
- screen 每 genome：16 / 8 / 4 / 8 局。
- 前四名和 incumbent 进入独立 confirmation，局数放大四倍。
- 全部候选零 candidate fault。

小样本前四名中，三个在独立 confirmation 出现明确退化腿。唯一全腿方向不退化的是
`g-0e85294e1c`：关闭
`boss_damaged_basic_stall_guard` 与
`energized_impidimp_preservation_guard`。

其 confirmation 结果：

- vs v22：35-29，54.69%；incumbent 同批 34-30。
- vs Router：24-8，75.00%；incumbent 同批 24-8。
- vs Alakazam：14-2，87.50%；incumbent 同批 12-4。
- vs Lucario：26-6，81.25%；incumbent 同批 21-11。
- 按预注册权重相对 incumbent 为 +6.02pp，但 v22 主腿只有 64 局，不能晋级。

完整数据：`experiments/runs/v22_residual_es_screen_20260815.json`。

## n=256 主闸

预注册规则：8/16 12:00 前，候选对 exact v22 的独立 n≥256 点估计必须大于等于
55%；同时相对同制度 incumbent 增量至少 3pp、零 fault。未达即停止，不用小样本跨腿
尖峰破例。

定向批先读 n=64 为 37-26-1，58.73%，仍不记账。随后独立 n=256：

- `g-0e85294e1c`：133-123，**51.95%**，零 fault。
- incumbent 自镜像：125-130-1，49.02%，零 fault。
- 相对增量：+2.93pp。

候选同时错过绝对 55% 线和相对 +3pp 线，`winner=null`。按预注册规则淘汰，
不 materialize、不跑 exact archive、不提交 Kaggle。

完整数据：`experiments/runs/v22_residual_es_g0e_v22_n256_20260815.json`。

## 结论与残局动作

1. 用户提出的路线成立：有自己的 v22 后，可以做真正的 on-policy RL，不再受官方
   replay 行为分布上限约束。本轮已经打通了最小闭环。
2. 但“能做 RL”不等于“第一轮就有更强件”。40-genome 的高点在独立 n=256 回归到
   51.95%，再次证明小样本 winner's curse 会制造假 challenger。
3. GPU 不是本轮瓶颈：v22 主闸 n=256 每个策略约 79 秒；慢项是 Alakazam 的 CPU
   搜索对手（并行时约 10–15 秒/局）。本轮没有理由引入 NN 推理与部署债。
4. 8/16 没有 RL challenger。默认动作仍是精确重交测量最充分的 v22；不得把
   `g-0e85294e1c` 以“接近通过”为由送上 live。
5. 若赛后继续，本轮下一步应是对触发级别做随机化 contextual residual，而不是继续
   全局开关或 winner-only BC；该工作不占用本场最后提交槽。

## 实物

- 搜索器：`experiments/v22_residual_es.py`
- 修复后的隔离 runner：`scripts/candidate_h2h.py`
- screen：`experiments/runs/v22_residual_es_screen_20260815.json`
- n=256：`experiments/runs/v22_residual_es_g0e_v22_n256_20260815.json`

## 10:34 触发级 follow-up

按上节提出的 contextual residual 方向补做了 seat-balanced 2×2 可行性实验。四腿
144 局中两个目标 guard 均为 0 次真实触发；单侧 95% 触发率上界 2.06%，而原定
544 局 discovery 要达到 apply/skip 各 30 次至少需要 11.03% 触发率。该线因此以
`INSUFFICIENT_OPPORTUNITIES` 封口，不跑 544 局、不降低闸。详见
`reports/20260815_v22_guard_factorial_feasibility.md`。
