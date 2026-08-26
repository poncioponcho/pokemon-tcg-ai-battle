# beam M3 Blueprint — 对手牌组识别 + 动态 OPP_DECK 注入

日期：2026-08-11 ｜ 状态：已批准开工（用户简报 G）｜ 目标：让 beam 在盲池局真正激活，撬动 Alakazam/Crustle 两个输局。

## 0. 问题定义（为什么 M3 是唯一杠杆）

- beam M2 已证机制有效：镜像腿 3 种子 **0.605/0.602/0.581**（纯规则基线 0.50），invalid=0，37ms/决策。
- 但 `beam_agent.py:44-46` 的 `OPP_DECK=mirror` + `_hidden_split` 负余量中止 → **对手任何一张异牌组可见卡即静默回退纯规则**（冒烟实测 vs_first 腿 54 次触发全部回退）。
- 真实天梯 88% 是非镜像局 → beam 当前 LB 贡献≈0。M3 = 用识别器把 OPP_DECK 从「假设=我自己」改成「识别=对手真实牌组」。
- 参照系：Kazuta 1005 源不存在于 Kaggle 公开面（已多路实锤），不等外部蓝本；1084.5 baseline（makthanithin）证明**规则agent+对手侦测**即可达 1084，但其侦测只是二元钩子（is_water/is_crustle）——M3 做的是全牌组识别，是这条路线的完整版。

## 1. 识别器设计（deck_recognizer.py）

### 1.1 输入信号（从 obs 可见，全部已在 calibration 中确认存在）

| 来源 | 字段 | 说明 |
|---|---|---|
| 对手 active/bench | `players[1-yi].active/bench[].id`（含 preEvolution） | 开局即亮，最强信号 |
| 对手 discard | `players[1-yi].discard[].id` | 随局推进增多 |
| 对手 prize 翻开 | `prize[]` 非 None 元素 | 偶发 |
| 场上 stadium | `current.stadium` | 弱信号（ Trainer 共有卡多） |
| 不用 | handCount（只有数量）、deck 背面 | 无 id 信息 |

### 1.2 分类方法：签名卡加权投票（v1 刻意简单）

- **签名表**从自有 4500 局标注数据（`experiments/runs/meta_decks_raw.jsonl`）自动导出：对每个 archetype A、每张卡 c，算 `score(c,A) = P(A|c) × log(P(A|c)/P(A))`（PMI 加权），取每 archetype top 签名卡（基本全是其 Pokemon 线：743/742/741→Alakazam，344/345→Crustle，648 线→Grimmsnarl，121→Dragapult，190→Archaludon，747→Gardevoir，117→Cornerstone，677/678→Lucario…）。
- **判决**：Σ 可见卡签名分 → argmax；要求 top1 − top2 ≥ margin（默认 1 个签名卡当量）否则弃权。**弃权 = beam 不激活 = 回退纯规则**（与现状一致，无新增风险）。
- **每决策重算**（O(#可见卡) < 1ms）：随着局推进信息单调增多，识别只会越来越准；开局 1-2 回合 setup 亮牌通常已足够（active+bench 基础宝可梦直接定 archetype）。

### 1.3 archetype → canonical 60 映射

- 主表：`experiments/arena_pool/meta/*.csv`（rank 最佳样本：Alakazam=rank4 M Sato 1168.6、Grimmsnarl=rank3 1180、Lucario=**rank1 Majkel1337 1265.6**…）。
- 交叉校验：22-archetype 标注集（`inference/ext/archetypes22/`，22 套 validated 60 张 + 标签）——对不上的 archetype 以 replay 提取为准（真实天梯在用）。
- 关键改进：即使对手是 Lucario 镜像族，也注入 **Majkel 的 60 张**而非我们自己的 deck.csv——他的表（保留 674、1192 等）与我们的 v4 差异显著，镜像假设在「同族不同表」下也会回退，注入真表后这部分也激活。

### 1.4 自纠错闭环

识别错误 → canonical 60 不含对手某张可见卡 → `_hidden_split` 负余量 → 自动回退纯规则。**错误识别不会产出错误 beam 决策，只会静默关闭 beam**。这层防御保留（简报 C 要求）。

## 2. 与 beam_agent.py 的接驳（最小 diff）

```
BEAM_OPP_DECK 语义变更: 'mirror' | csv路径 | 'auto'
'auto' → 每决策调 deck_recognizer.classify(obs) → canonical 60 | None(弃权→回退)
```

- 只改 `_build_hidden` 的 OPP_DECK 来源（约 :124-129），其余 rollout/计分/回退逻辑零改动。
- 识别器无状态纯函数，beam_agent import 一次；冷启动签名表构建 <100ms。
- 新 env：`BEAM_RECOGNIZER=auto`（默认 off = 现行为），闸内显式开。

## 3. 数据与资产清单（全部已在手 ✔）

| 资产 | 路径 | 用途 |
|---|---|---|
| 4500 局标注回放 | `experiments/runs/meta_decks_raw.jsonl` | 签名表导出 + 识别器离线准确率评测 |
| 22-archetype 标注集 | `inference/ext/archetypes22/`（decklists/ex01-22.csv + archetypes.csv + 相似度矩阵） | canonical 表交叉校验 |
| 9 个冻结 meta 牌组 | `experiments/arena_pool/meta/*.csv` | canonical 主表 + 闸腿对手 |
| 1084.5 baseline | `inference/ext/baseline1084_main.py` + deck | 侦测钩子写法参照；其 1192×4/674×2 牌组差异点 |
| M Sato Alakazam | `arena_pool/meta/Alakazam__rank4_1169.csv` | 最差 matchup 的 canonical（741/742/743×4 + 1081/1086/1225/1231×4…）✔ 已确认 |

## 4. 验收闸（G4，不达标不提交；全部 3 种子 9000/9001/9002）

| 腿 | 设置 | 基线(v4 纯规则) | 闸门 |
|---|---|---|---|
| 识别器离线准确率 | 回放 obs 序列重放分类 | — | **turn≥3 后 ≥90%**，误识不产错决策（自纠错） |
| Alakazam 腿 | beam(auto) vs first 驾驶 M Sato 牌组，n=1000/种子 | 0.466 | **>0.50** |
| Crustle 腿 | 同上 | 0.497 | >0.52 |
| Mirror 腿 | beam(auto) vs 纯规则同牌组 | 0.807 | 不退化（ci_lo 不降） |
| 加权期望 | meta 占比加权 | ~0.72 | 正向即胜，但提交仍需 R2 纪律（≥v4 现态 467.9 对应闸尺度） |

注意口径：闸腿对手由 builtin('first') 驾驶（与基线同口径，保证差值归因于 beam 激活）；真实精英驾驶更强，LB 迁移保留折让。
后续升级项（不在本次闸内）：把闸腿驾驶员从 first 换成公开 agent 池（kokinn_lucario_search_915、roman LB950 等，1084.5 的 Public21 玩法）——这是 v0 池的下一步。

## 5. 风险与避坑（简报 F 落锤）

- 离线 positive ≠ LB：只有冻结池实测达闸才算数；提交走 R1/R2 纪律。
- 时间预算：600s/局总时限实测 beam 全激活 ~0.74-3s/局，无超时风险；全量闸后仍在 arena_runner 真对局复验一次 latency。
- 克隆保真：用官方 search API（M1/M2 已校准 result 语义与一致性），不手搓状态转移。
- 不复活 F2c（H2 根因：Mega Brave 隔回合禁用，连续收割不存在，-2.05pp 已回滚）。
- 牌面漂移：meta 每周动（Sumi：Lucario 7 月底近灭绝、8 月 Majkel 回 rank1），签名表构建脚本保留可重跑入口，后续每周可刷新。

## 6. 交付物清单（简报 G）

1. 本文件 ✔
2. 730554 数据集 ✔ / 1084.5 baseline ✔ / M Sato 牌组 ✔（均已落盘）
3. `experiments/deck_recognizer.py` + `beam_agent.py` 的 auto 接驳
4. 三种子 × 全 meta 闸报告（`experiments/runs/beam_m3_gate.json`），**不提交**
