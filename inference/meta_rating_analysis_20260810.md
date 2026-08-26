# LB Meta × Rating 机制分析 → 优化方向（2026-08-10 晚）

数据源：
- `ptcg-ai-battle-leaderboard-deck-meta-by-score-band.ipynb`（快照 2026-08-09 UTC，分层抽样 2,359 支已分类队伍）
- `ptcg-ai-battle-rating-and-matchmaking-analysis.ipynb`（数据窗至 ~08-01）
- 项目现状：现役 main.py v24.8（sha 20a004ead12d），deck.csv=v4 FINAL；55390992 结算 485.4；v4 FINAL 瞬读 600 待结算。

---

## 1. 牌组 Meta：按分数段的关键事实

**总榜（2,359 队）**：Grimmsnarl 19.6% / Alakazam 19.5% / **Mega Lucario 17.8%** / Crustle Wall 8.9% / Archaludon 7.9% / Dragapult 5.7%。

**Mega Lucario 使用率随分数段的悬崖**（本分析最重要的一张表）：

| 分数段 | Lucario | 段内前三 |
|---|---|---|
| 500-599 (n=500) | **35.0% (#1)** | Alakazam 13.0%, Crustle 12.4% |
| 600-699 (n=500) | **28.6% (#1)** | Alakazam 15.0%, Dragapult 14.0% |
| 700-799 (n=500) | 12.6% (#3) | Alakazam 30.6%, Archaludon 24.2% |
| 800-899 (n=500) | 5.4% (#4) | Grimmsnarl 42.8%, Alakazam 20.0% |
| 900-999 (n=262) | 3.4% | Grimmsnarl 45.8%, Alakazam 19.1% |
| 1000-1099 (n=81) | 1.2% | Grimmsnarl 29.6%, Alakazam 16.1% |
| 1100+ (n=16) | 6.2%（1 队） | Alakazam 25.0%, 余者分散 |

读法：
- Lucario 是低分段第一大卡组，但使用率随段位单调崩塌（35%→1.2%）。**usage ≠ strength**（notebook 自己声明），悬崖可能来自卡组上限，也可能来自驾驶者平均水平；但 1100+ 确有 1 支 Lucario → 不是死罪，是稀缺。
- 我们结算 485.4，正处 Lucario 最稠密的池子底部 → **当前最可能的配对是 Lucario 镜像**。
- 爬分路径的对手谱随段位移：500-700 = 镜像 + Alakazam + Crustle/Dragapult；700s = Alakazam+Archaludon（合计 55%）；800+ = Grimmsnarl 控制（43-46%）。控制系（Grimmsnarl=手牌干扰、Alakazam）统治高分段——**与本地诊断收敛**：我们 F2 的 3 奖 swing 软肋正是控制 deck 最爱吃的点。

## 2. Rating 机制：关键事实

- 全部 6,113 队：均值 622.8 / 中位 637.8 / 标准差 186.6 / 最高 1262.2。
- **新提交从 600 起评**；首场比赛 ~3-5 分钟内；高活跃提交 ~12 场/小时；**~48 场 / ~22-24h 收敛**，之后比赛基本停止流入（观察窗 ~21.7h）。
- 早期高 K 方差巨大：同为强 agent，6-0 开局 → 1011；3-3 开局 → 642（同一时点）。
- 胜率→rating 参照（含对手强度噪声）：61.2% → 1155；65.3% → 928；53.5% → 801；57.8% → 720；49.1% → 593。
- 高分段 rematch 率 61.5%（池子小，反复互打）。

对我们结算纪律的验证与修正：
1. **「瞬读 600 不记账」铁证**——600 就是起始分，不是测量值。429.4 / 436.4 / 485.4 这类是收敛真值。
2. 每发新提交独立从 600 重 roll，前十场运气可造成 ±50-80 ELO 差 → **单发之间 <50 分的差不解读为 agent 差异**；LB 取最优发，下行成本只有额度。
3. 明早看 v4 FINAL（提交 12:12，到时 ~19-20h）≈ 接近收敛，可读；但严格满 24h 更稳。

## 3. 本次分析暴露的最大度量缺口（新发现）

**我们的两道闸对真实 meta 覆盖有限：**
- leg1「mirror」= 新 main+候选牌组 vs 旧 main.bak+旧牌组（Lucario 打 Lucario）；
- leg2「vs_first」= 候选牌组 vs naive greedy 驾驶**官方样例牌组**（`arena_runner.py:36` `COMP = inference/comp_data/sample_submission/sample_submission`，721/722/723 线+能量3；该文件冻结，历次闸门口径一致可比）。

含义：leg1 是纯 Lucario 镜像，leg2 是弱代理驾驶的非 meta 牌组——真实 LB 池子里 65-70% 的对手（Alakazam/Archaludon/Dragapult/Crustle/Grimmsnarl）我们**零本地信号**。结算分每次都在考我们没复习的科目。这解释了为什么本地闸全过的牌组，LB 迁移始终只能指望个位数 pp。

可行补法（分层，勿过度投资）：
- **v0（参考信号，非闸门）**：用存量回放基建（`inference/leaderboard_replay/`：episode_catalog 19,834 条 + bulk zst）抽取高分段 Alakazam/Grimmsnarl 真实 60 卡表，构造冻结对手，builtin 'first' 驾驶，给候选牌组一个「结构 matchup」参考数。弱代理，只作参考，不进闸门。
- **v1（更重）**：通用 greedy 驾驶 meta 牌组。工作量与误导风险都上升，4 天窗口内不建议。

## 4. 优化方向总表（ROI 排序）

**今晚可做（零 LB 依赖）：**
1. **F2c 落地 + 双腿验证**（审计 H1）——677 蓄 2 能才放行进化 678，攻 Q3「非 677 起手 WR 0.278 + 2.4 回合死亡窗口」。在镜像率 35% 的池子里，节奏优势双倍值钱。diff 现成，验证 ~18s。
2. **M1 decide 标杆参数化**（--bench-mirror/--bench-vf，~10 行）——今天 v5 已演示一次假 STRONG。
3. **M2 pack.sh ACE SPEC ≤1 校验**——防最后一发非法包烧额度。
4. H2 注释修正随 1 顺手。

**明早（结算复核后拍板）：**
- v4 FINAL 收敛分 vs 485.4；重点看 vs_first 薄边（+1.1~1.4pp）是否兑现。
- F2c 若今晚落地双腿过 → 明天走 3 种子闸对标现役标杆，过闸即下一发真候选。
- v4 翻车 → 退回 55390992 牌组基线。

**48h 内（F2c 站住后）：** 重跑采集器看 Q4 漏斗（attach_to_non_core 胜局占比应下降）→ F2 守成层剩余部分；param_tune 下一周期（self-test 已修，门禁可信）。

**中期可选（度量面）：** 上述 meta 对手 v0 参考信号。

**保持关闭/冻结：** NN-A/D（ledger#77）、C（search oracle，8/14 前不开）、v5 +シアノ（HOLD，除非 v4 翻车）。

**战略层（非技术、最高优先确认）：** Strategy 赛道是晋级第二轮的硬门槛（同队必须双赛道），报告准备是纯本地活——需用户确认是否已有动作。

## 5. 提交策略（rating 机制驱动）

- 剩余 ~4 天、每日额度有限：每发必须是「过真闸的候选」——过闸即交，正 EV；噪声假阳性则浪费 24h 收敛窗+额度。
- 结算判读窗 = 提交后 22-24h；明早 v4 读数接近收敛。
- 不因单发 ±50 ELO 内波动改方向（早期高 K 方差所致）。
