# v22 有界加性残差——分样本预注册

预注册时间：2026-08-15 11:15 CST。本文写入时，尚未运行本文定义的加性变体。

## 动机与 scope

已完成的乘法扰动闸显示：资源与手贴分数即使只乘 `0.975/1.025`，仍在 58–70/82 局发生首次动作分叉，不是局部残差；目标 asset 权重在 ±10% 内仅 0–2/82 局分叉，为死区。

本轮是新的、预先定义的参数化：不再对 8,000 左右的绝对分数乘百分比，而是对相应动作加一个有界常数偏置。只测两个族：

- `resource_timing_offset`：Gym search ability 及 setup/search/draw/recovery Trainer 的 MAIN score；不含 Pokémon play、Boss、Scrapper。
- `attachment_timing_offset`：手贴 Darkness Energy 的 MAIN score。

`target_asset` 不重开；`target_evaluator.py` 的 `energy*40` 无调用者，不得当成 exact-v22 活跃参数。

## 数据切分

- 设计/校准集：旧 exact-v22 ref `55499962`，50 局 PUBLIC。
- 盲验集：新 exact-v22 ref `55516725`，32 局 PUBLIC。
- 两批均固定为 2026-08-15 10:45 CST 快照；validation 各 1 局排除。
- 候选 offset 网格固定为 `±10, ±25, ±50, ±100`。

只能用设计集选 offset，不得根据盲验集改数值、降闸或补点。每个参数族×方向只保留绝对值最小的 PASS offset。

## first-divergence 口径

exact-v22 必须逐动作 100% 复现 replay。每局开始前对每个 agent 执行 `select=None` 重置。变体只在其历史动作与 incumbent 语义一致时继续重放；首次语义分叉后立即截断本局。后缀状态属于 incumbent 世界，不是 paired counterfactual。

语义键包含 action type、source/target card id 与 serial、zone/seat、attack id 及多选集合。仅 option index 变化或同一组重复卡的排列不算分叉。

## 设计集闸（50 局）

令 `D` 为发生首次语义分叉的 episode 数。PASS 必须同时满足：

- `5 <= D <= 20`；
- seat 0/1 各至少 1 局；原对局胜/负各至少 1 局；
- `turn <= 2` 的早分叉不超过 `D` 的 25%；
- 首分叉 decision ordinal 中位数至少 10；
- 零 fault、零非法动作、deck 完全一致。

## 盲验闸（32 局）

只运行设计集选出的 offset。PASS 必须同时满足：

- `3 <= D <= 13`；
- seat 0/1 各至少 1 局；原对局胜/负各至少 1 局；
- `turn <= 2` 的早分叉不超过 `D` 的 25%；
- 首分叉 decision ordinal 中位数至少 10；
- 零 fault、零非法动作、deck 完全一致。

合并 82 局还必须通过已有标准闸：`8 <= D <= 33`，两 ref 各至少 3，两 seat 各至少 2，原胜/负各至少 2，早分叉不超过 25%，decision ordinal 中位数至少 10。

## 后续权限

回放中的原始 W/L 只用于覆盖检查，不是变体的反事实 reward，不得用它选方向。只有设计集、盲验集和合并闸全部 PASS 的变体才可 materialize 并进入本地 W/L。

本地 W/L 必须称为 blocked independent trial：官方 native shuffle 没有 seed setter，不得称 paired/CRN。本线不授权 Kaggle 提交，不改 exact-v22 归档，不改 8/16 默认精确重交计划。

## W/L 闸补充（11:22 CST，胜负运行前写入）

回放盲验后的固定候选集为 `resource_timing_offset=+25` 与
`attachment_timing_offset=+50`。`resource=-10` 因盲验 0/32 已毙掉。不新增两轴 combo，不在看到 W/L 后补 offset。

W/L 第一阶段固定为与 C-009 相同的四腿和权重：

- exact v22：64 局，权重 0.45；
- Router：32 局，权重 0.15；
- Alakazam：16 局，权重 0.30；
- Lucario recovery baseline：32 局，权重 0.10。

两候选与一个 exact-v22 incumbent control 都跑完 144 局。每个四局块用 ABBA/BAAB 交替的 candidate-seat 顺序，每块两个座位各两局；这只是 blocked independent design，不是配对洗牌。

只有零 candidate fault、对 exact-v22 点估计至少 53%、相对同阶段 incumbent 的加权增量至少 +3pp，且任一跨牌组腿不得低于 incumbent 超过 10pp 的候选才有资格进主闸。多个合格时只取加权增量最高者；完全同分时取 exact-v22 WR 更高者。

主闸为候选 vs exact-v22 独立 256 局，另跑 exact-v22 vs exact-v22 256 局 control。PASS 必须同时满足：

- 候选 WR 至少 55%；
- 候选 WR 比同阶段 incumbent control 高至少 3pp；
- 候选零 fault。

主闸失败则 `winner=null`，不 materialize、不 exact-archive、不打包、不提交。主闸通过也只能生成待 exact-archive 复验的 challenger，不自动上 Kaggle。
