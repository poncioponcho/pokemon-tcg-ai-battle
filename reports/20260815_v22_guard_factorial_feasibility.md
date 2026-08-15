# v22 近失 guard 的触发级 2×2 可行性封口

时间：2026-08-15 10:34 CST
状态：`completed-negative / INSUFFICIENT_OPPORTUNITIES`；不生成候选、不扩样、不提交。

## 目的

第一轮 on-policy residual ES 的唯一幸存者
`g-0e85294e1c` 同时关闭了两个窄规则：

- `boss_damaged_basic_stall_guard`
- `energized_impidimp_preservation_guard`

全局开关在独立 exact-v22 n=256 主闸只有 133-123（51.95%），已经按预注册规则
KILL。本轮不是重开该候选，而是检查两个规则是否有足够真实触发机会，值得继续做
contextual residual。

## 先修实验仪器

原型脚本在正式运行前做了三项修正：

1. 四个 factorial arm 不仅等量，而且按候选座位分层。每八局中，每个 arm 在
   candidate seat 0 和 seat 1 各出现一次，阻断先后手与 treatment 混杂。旧原型曾出现
   单臂 7:1 的座位偏斜，因此旧 arm WR 只保留为 smoke，不作效应证据。
2. verdict 区分 `NO_SIGNAL` 与 `INSUFFICIENT_OPPORTUNITIES`。没有真实触发时，不能把
   随机分臂后的终局 WR 差误写成 guard 效应。
3. `candidate_h2h.py` 的 exact-v22 baseline 锁从 main/deck 两个文件扩展为完整运行树：
   tree SHA256
   `0319fee37419983ad7137c1db9d1ac7d67024cc692eb495d73e6f46fedd12ecc`。
   长任务输出继续使用独占 lock、拒绝默认覆盖和原子替换。

合成触发态自测覆盖了 apply 与 skip 路径：两个 wrapper 均能记录 `guard_action`、
`final_action`、状态快照和 apply/skip 标志。因此正式批次的零事件不是埋点失效。

## 预注册 discovery 闸

每个 guard 必须同时满足：

- apply 与 skip 的真实触发机会各不少于 30 局；
- skip 相对 apply 的胜率优势至少 10pp；
- 至少两条 opponent 腿同向；
- 每条同向腿 apply/skip 各不少于 8 个真实触发局。

即使出现 `SIGNAL`，也只能授权另造 deterministic contextual residual；仍须重新通过
exact-v22 n≥256 主闸和跨牌组回归闸，不能直接提交。

## 正式可行性批次

运行物：`experiments/runs/v22_guard_factorial_feasibility_20260815.json`。

- 总计 144 局：v22 64、Router 32、Lucario 32、Alakazam 16。
- 四臂各 36 局；每臂 candidate seat 0/1 均为 18/18，各 opponent 腿内也严格平衡。
- 候选 fault 0，对手 fault 0，平均 185.78 steps。
- Boss guard：真实触发局 0，触发事件 0。
- Impidimp guard：真实触发局 0，触发事件 0。
- 两者 `gate_evaluable=false`，总 verdict=`INSUFFICIENT_OPPORTUNITIES`。

四臂终局 WR 虽在 61.1%–77.8% 间摆动，但 144 局里 treatment 从未真正触发，策略
行为没有因这两个开关发生可观测改变。该摆动只能按 native shuffle 不可播种、各局
非 paired 的路径噪声解释，不能用于挑 arm。

## 可行性数学

零触发的单侧 95% Clopper-Pearson 上界为
`1 - 0.05^(1/144) = 2.0589%`。

原计划 544 局若要让 apply/skip 各达到 30 次，至少需要 60 个触发局，即总体触发率
至少 `60/544 = 11.0294%`。在真实触发率恰好等于这个最低可行率时，144 局仍观察到
零触发的概率只有 `(1 - 60/544)^144 = 4.91e-8`。即使按 95% 上界 2.0589% 外推，
544 局也只期望约 11.2 个触发局，远低于 60。

这不证明两个 guard 在所有未来或 live 对局里绝不触发；它证明的是：在本场四腿分布与
剩余时间预算内，预注册 discovery 闸不可达。继续把 144 扩到 544 只会为寻找尖峰改变
实验目的。

## 裁决

- 触发级 contextual residual 线立即 KILL，不跑 544 局，不降低 30/10pp/两腿闸。
- 第一轮 ES 的 +2.93pp 近失没有形成可复现的行为层解释；零触发结果强烈支持其主要是
  未配对 native 路径方差，而不是可利用的两个 guard 残差。
- 没有 candidate 被 materialize、打包或提交；`candidates/grim_v22_final/` 与线上
  archive SHA `599e19ae…b4c8bfcf` 均未修改。
- 8/16 默认动作不变：按 live 两个独立 v22 实例的充分测量，精确重交 v22；不得用
  本轮 arm WR 或原 ES screen 尖峰替代主闸。
