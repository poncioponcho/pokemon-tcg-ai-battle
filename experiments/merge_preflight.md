# merge 预读备忘录（2026-08-11 晚）— F1→baseline 移植的结构可行性

> 目的：为明天的 merge 可行性评估提供代码级地面真相。结论先行：**F1 机制反向移植 ≈ 零操作**（F1 本就从 baseline 移植，baseline 原版结构更优）；**唯一真缺口 = 674 自伤门控**（baseline 没有我们的 BUG-7 修复）。

## 1. 两家攻击架构对比

| | baseline1084（config A 现役） | 我们 main.py（F1 现役） |
|---|---|---|
| 结构 | **全局打分循环** `_plan_attack` :285-340：attacker×attack×target 全枚举，score=target_score(:119)×KO折算+50000终局奖+base_score+220 | **顺序优先级链** :3024-3216：P1 KO→P2铺场→P3进化→F1转火→撤退→P4攻击… |
| Crustle 转火 | :318-323 目标过滤 `wall && 678 && target==345 → continue`，345 从打分空间剔除；转火 344/bench **从打分涌现**，gust 由 can_gust+计划执行驱动 | :3073-3089 特例分支：no_attack_wall 时主动打 Boss(1182) 抓 bench 非墙目标 |
| 墙判定 | :232-233 `{344,345}` 全板检测 | `opp_is_wall`（345 系，较窄） |
| 水系钩子 | :229-230 + :256-257（奖≤3 时 -500） | 无（F3 从未做） |
| 674 破墙 | :263 `_base_attack` Hariyama 210/3能，与其他打手同循环打分 | P3.5 进化优先 + 换打手撤退 |

**判定**：F1（转火）、F2（344+345 拓宽）、F3（水钩子）三项在 baseline 里**全部已存在且形式更优**（全局打分 > 特例链）。F1 本就是从它移植的——把 F1 再移回去是零操作。顾问 (b) 预判在代码层坐实。

## 2. 唯一真缺口：674 自伤门控（候选增量 #1）

- 我们：`main.py:2872` `dying_674 = (my_cid==674 and my_hp <= hariyama_self_ko_hp)` — 674 ワイルドプレス自伤 70，HP≤70 时非 KO 攻击=自杀白送奖品，P5/P9/P14 门控+P16 撤退兜底（BUG-7）。
- baseline：`:263` Hariyama 攻击打分**无任何自伤项**——HP≤70 的 674 会照打，自 KO 白送对手 1 奖品。config A 牌组 674×2 是破墙件，Crustle/Cornerstone 局必用 → 缺口真实存在。
- 移植形态：`_base_attack` 里 Hariyama 分支加 `if pokemon.hp <= 70 and 攻击不KO目标: return None`（语义照抄 BUG-7：KO 交易照打）。
- 期望值校准：低频微修正，单腿 ≲+1-2pp，加权 ≪2.2pp 噪声地板——**单独不够第 3 发闸**，但近乎零成本的正确性修复，可与候选 #2 捆绑。

## 3. 候选增量 #2：archetype 条件化打分（唯一可能 >2.2pp 的方向）

- 手头资产：beam_m3 搁置的 `deck_recognizer.py`（22-archetype PMI 签名，冒烟 30 局 Alakazam 207/207 全识别）。
- 思路：baseline 的 target_score 是静态表；vs 不同 archetype 的最优选靶不同（如 vs Alakazam 0.841 还有 16pp 空间、vs Crustle 0.823 还有 18pp）。识别器开局拍 archetype → 对 target_score 加 per-archetype 调整项。
- 风险：调整项没有先验来源，需要搜索/手设+大 n 闸验证，容易过拟合噪声（ledger #111 纪律下每条调整都须 |Δ|>2.2pp 才算数）。**明天先试，预期管理中低。**

## 4. 已封死的方向（勿再开）

- 牌组轴：hybrid 搜索 rd1 收敛回 config A（ledger: hybrid_line_closed）。
- F1/F2/F3 移植：零操作（§1）。
- beam（M3）：加权 +0.7~1.0pp 噪声带内，已 shelve；beam-over-baseline 无新证据不重开。
- Budew 锁/冲刺/能量韧性：均我方牌组专属，config A 牌组无此件，零意义。

## 5. 明天评估序列 + 闸规格（顾问口径锁定）

1. 移植 dying_674 门控进 baseline 副本（`_P` 门控式 flag，默认 ON + OFF 对照嵌闸）。
2. 同批 A/B：merge vs config A，9 腿 n=1000（中大一头腿 n=2000）。
3. 闸：**merge 加权 > config A + 2.2pp**（锚是 config A 不是 F1！），全腿退化 <|2.2pp|，invalid=0。Crustle/Alakazam 两腿重点看。
4. archetype 条件化若做：每条调整单独 flag + 单独过闸，不达标即弃。
5. 提交纪律：闸过即交（顾问修正：越早越吃沉淀+波动红利；8/15 晚仅为红线非目标）；顶出 F1，last-2={config A, merge}，地板=config A 不自伤。
6. 若全灭：正确结局=不交第 3 发，config A + F1 settle 到 8/17（2.3× 跃迁已锁定）。
