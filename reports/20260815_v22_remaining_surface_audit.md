# v22 赛前剩余决策面审计

时间：2026-08-15 12:04 CST
状态：`completed-negative`
裁决：没有形成 challenger；8/16 默认精确重交 exact v22 不变。

## 结论先行

K3 复核后的三个已封口空间——二元 guard、全局数值 offset、不可实现的 paired/CRN——
之外，本轮继续检查了三个正交问题：live job 级控制面、完整结构删减、以及 live 中最强的
早期动作异常。三条线均未产生可进入 n=256 的候选。

这不是“没想到新点子”，而是两个新假设都实际跑到了自动停止条件：完整 hierarchy
删减在四腿主闸失败；早期 Dawn 的负相关无法转化为安全反事实动作。exact-v22 运行树
仍为 `0319fee3…ecc`，归档仍为 `599e19ae…b4c8bfcf`，线上与 Automation 均未修改。

## 1. 固定 82 场的 live 决策面

顺序重放 82 场、8,333 次 ACTIVE 调用、8,251 次真实选择，recorded action 仍为
0 mismatch。相对 validated fallback，manual guard 或 hierarchy 最终只有 44 次
语义动作改写，占 0.53%。

按旧 ref 50 场作发现、新 ref 32 场作复现，限定真正改变 fallback 的
`control:*@turn<=4`，并要求两 ref 同向和最低 exposed/unexposed 覆盖后，候选数为 0。
主要原因不是阈值太严，而是每个 job 的实际控制暴露极稀疏：绝大多数 job 只在一侧 ref
出现 0–2 场，无法区分真实效应与路径噪声。

产物：

- `experiments/v22_live_decision_surface.py`
- `experiments/runs/v22_live_decision_surface_20260815_1045CST.json`

## 2. manual guards × hierarchy 结构 2×2

历史检索确认 C-009 只关闭一至三个 guard/四个 MAIN layer，没有做完整 hierarchy
（包含 search/selection/target/protocol）的结构消融。因此先落预注册，再测试四个臂：
exact、hierarchy-only、manual-only、fallback-only。

行为 canary：

- exact：8,333 次 ACTIVE 调用，0 mismatch；
- hierarchy-only（只删 manual）：1/82 场首次语义分叉；
- manual-only（删完整 hierarchy）：24/82 场分叉；
- fallback-only：25/82 场分叉。

正式四腿每臂 144 局，全部 candidate/opponent fault=0，所有腿 seat 0/1 严格均衡：

- exact v22：加权 68.14%，对 v22 36-27-1（57.14%）；
- hierarchy-only：加权 54.38%，相对 exact −13.77pp；对 v22 28-36（43.75%）；
- manual-only：加权 64.69%，相对 exact −3.46pp；对 v22 28-36（43.75%）；
- fallback-only：加权 60.89%，相对 exact −7.25pp；对 v22 31-32-1（49.21%）。

三个删减臂都未同时达到主腿 WR≥53%、加权增量≥3pp和跨腿保护线，故
`selected_for_n256=null`、`winner=null`。按预注册不追跑。

manual-only 在本批 Router 持平、Alakazam +6.25pp、Lucario +6.96pp，但 Grim/v22
主腿 −13.39pp；这是一个可能的 matchup interaction，也可能只是小样本/独立 shuffle
噪声。它是在看过四腿后出现的切片，禁止倒推为本场候选。赛后若做可见牌组路由，应先
独立扩大每条跨牌组腿，再验证只能根据当时已公开的对手卡牌作路由，不能使用 replay
里赛后才知道的完整 60 卡标签。

产物：

- `reports/20260815_v22_structural_factorial_prereg.md`
- `experiments/v22_structural_factorial.py`
- `experiments/runs/v22_structural_factorial_20260815.json`

## 3. 早期 Dawn 异常簇

探索性 live 关联里，前 4 回合打出 Dawn（1231）的 11 场为 3-8，其余为 49-22；
旧 ref 为 1-6 vs 28-15，新 ref 为 2-2 vs 21-7，合并 Fisher p≈0.015。`context:4`
是 Dawn 搜索链下游，不能作为独立证据。

该现象最可能是反向因果：缺 Basic/Stage1/Stage2 的坏起手更需要 Dawn。为避免凭直觉
争论，预注册只对 turn≤4 的 Dawn score 施加 100–1200 分 penalty，并做 replay
首次分歧与替代动作安全审计：

- penalty 100/200：0/82 分叉；
- penalty 300：2/82 分叉；
- penalty 400/600/800/1200：均仅 3/82 分叉；
- 所有发生分叉的替代动作都是 early Boss，unsafe replacement=100%；
- 其余 Dawn 选择由 hierarchy 路径锁定，单改 fallback 分数不改变最终动作。

因此 `selected_for_wl_preregistration=null`。该信号被判为“坏起手/缺进化线的标记，
没有自然的安全替代动作”，不跑 W/L、不添加反 Dawn 规则。

产物：

- `reports/20260815_v22_early_dawn_prereg.md`
- `experiments/v22_early_dawn_screen.py`
- `experiments/runs/v22_early_dawn_screen_20260815.json`

## 残局动作与真正的新方向

赛前只剩一个正收益动作：继续分 ref 只读监测，并在 8/16 精确重交 archive
`599e19ae…b4c8bfcf`。本轮没有授权 Kaggle 提交，也没有改变 C-007/C-008。

赛后值得立项、但不能伪装成本场可交件的方向有三条：

1. **可见信息 matchup router**：验证 manual-only 的跨牌组方向性切片；只能使用对局当时
   已公开的卡牌与 board state，先做独立大样本，不允许用完整 replay deck label 泄漏。
2. **真正的 on-policy residual RL**：C-009 只证伪了稀疏“关开关”搜索，不等于证伪 RL。
   下一版应以 v22 为安全回退，让可学习策略只在高暴露 MAIN 决策上给 advantage/override，
   用自生成终局 W/L 训练，并把部署保真和四腿 arena 纳入每轮，而不是 winner-only BC。
3. **牌组与 pilot 联合重建**：Crustle live 2-3 仍只是假设生成信号；需更大真实样本后再做
   prize-trade/属性克制方向的 deck+policy 联合优化，不能在本场用 5 局做专项补丁。

原生 RNG 无 seed setter 仍是首要测量债。若下一场能获得可播种引擎或 state clone，
优先建设动作级 branch rollout；否则继续使用 blocked independent trial，并把局数预算
放在验证而不是更大的小样本搜索 population。
