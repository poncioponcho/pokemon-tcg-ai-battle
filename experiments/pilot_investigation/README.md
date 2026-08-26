# pilot_investigation/ — pilot 层行为 diff 调查 (2026-08-12 CLOSED)

**状态: 收线 (a) — advisor 2026-08-12 20:41 终判。** 时间盒原定 8/15 晚, 提前达标关闭。

## 结论 (闸灵敏度天花板)

两条独立行为差 (证据扎实) → 两发候选 → 本地 first-pilot 闸均测得 ~0:
- nrg_bench: 加权 **−0.09pp** (regression 全过, invalid 0) — 闸全盲 (收益只对真 pilot 存在)
- retreat_pivot: 加权 **−0.50pp** (regression 全过, invalid 0) — 闸半可见仍归零

**first-pilot 闸对 pilot 质量改进已达灵敏度天花板**: 本地加权 WR 0.92 贴结构顶,
live 0.476 缺口全在 first-pilot 不会做的事上 (猎 3 奖身 / 惩罚能量错配)。
闸能证无害、证不了有益 → 纯规则工具箱在 pilot 层够不着, 剩余差距在 pilot 能力层 (NN/search)。

live 探针 (b) 因统计功效不足未执行 (n≈42-72 时 σ≈7.7pp, <15pp 跳动检不出) — 载具备份见
`retreat_probe_plan.md` (BACKUP, 未授权不执行)。

## 实测行为差 (us vs top-3 pilots, 68+41 局)

| 维度 | 我们 | Sixth/Dipam/ミワ | 判读 |
|---|---|---|---|
| pre-KO 喂 active 能量% (W) | 28.2% | 10.9 / 30.0* / 6.2 | 真差 (*Dipam=deck对照) → nrg_bench 闸 ~0 |
| 付费 retreat /局 (W) | 0.42 | 2.14 / 1.76 / 1.50 | 真差 (赛中 prize-denial pivot) → retreat_pivot 闸 ~0 |
| Boss's Orders /局 | 3.1-3.8 | 1.65-3.18 | 无 portable 差 (我们还更多) |

## 内容物

- `top_pilot_diff_plan.md` — 调查方案 (决策树/抗偏差/限速/时间盒)
- `top_pilot_pull.py` — replay 拉取 (5s 限速, 断点续拉; raw 已删, 重跑可再拉)
- `top_pilot_analyze.py` — 参数化解析器 (player_name 参数; 6 维 + type8 换位三分解 + pre-KO 防伪刀)
- `merge_gate_{nrgbench,retreatpivot}.py` — 两候选三配置闸脚本
- `retreat_probe_plan.md` — live 探针 BACKUP (三铁律)
- `artifacts/` — top_pilot_diff.json + 两闸 json/log + pull log

## 复用注意

- 脚本内 PROJ 绝对路径仍有效; 解析器读 `experiments/runs/top_pilot_replays/` (已删, 需重拉)。
- ours 侧 live replays 保留在 `experiments/runs/live_replays/` (150MB, #132 管线复用)。
- 目标池 submissionId: Sixth 55439076 / Dipam 55449184 / ミワ 55449976。
- 解析器锚点: ours_L 奖品 2.45/4.09 ≈ #132 2.35/4.04; ours_W KO 3.74 精确一致。
