# v22 早期 Dawn 异常簇：行为暴露预注册

时间：2026-08-15 CST
状态：`preregistered-before-counterfactual-screen`
范围：只读 replay 行为审计；本文件不授权 W/L、打包或提交。

## 探索信号

固定 82 场 live replay 的 episode-level 关联中，前 4 回合实际打出 Dawn（card 1231）
的 11 场为 3-8，其余 71 场为 49-22；两侧 Fisher exact p≈0.015。按 ref 拆分：

- 旧 ref：Dawn 1-6，对照 28-15；
- 新 ref：Dawn 2-2，对照 21-7。

方向跨 ref 一致，但这不是因果结论。Dawn 用于补 Basic/Stage1/Stage2，坏起手更可能
迫使策略打 Dawn，因此最可信的原假设仍是“Dawn 是坏牌序的标记，而非败因”。
`context:4` 是 Dawn 搜索链的下游流程，不作为第二条独立证据。

## 唯一允许的行为族

只对 `turn<=4 && action.type==7 && source_id==1231` 的 fallback MAIN score 减去固定分值。
冻结 penalty grid：`100, 200, 300, 400, 600, 800, 1200`。不改其他资源、牌组、
hierarchy、manual guards、合法性或回合记忆。

用 exact-v22 逐状态重放 82 场；每个变体只跟随到该局首次语义分歧，之后立即 censor。
exact replay 必须 0 mismatch，penalty=0 control 必须 0 divergence/0 fault。

## 行为 PASS 规则

选择绝对值最小、且同时满足以下条件的 penalty：

- 首次分歧 episode 数 `8 <= D <= 14`；
- 两个 ref 各至少 3 场；历史胜/负各至少 2 场；两个 seat 均至少 1 场；
- 所有首分歧均在 MAIN context 0、turn<=4；
- candidate fault=0、牌组不变；
- 替代动作中 `decline/end_turn/early Boss` 的比例不得超过 25%。

替代动作的 recorded W/L 只作覆盖标签，不是反事实 reward。若没有 penalty PASS，
该异常按“坏起手标记/无安全反事实动作”封口，不跑本地 W/L、不调低门槛。

## 后续边界

行为 PASS 只允许另写一份 W/L 预注册，不自动晋级。任何 W/L 候选仍需 exact v22 主腿、
Router、Alakazam、Lucario 四腿和独立 n=256 主闸；8/16 默认精确重交 v22 不变。
