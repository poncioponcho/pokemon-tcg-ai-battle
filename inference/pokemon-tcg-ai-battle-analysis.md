# Pokémon TCG AI Battle — 参赛分析与策略手册

> 整理时间：2026-08-10（GMT+8）
> 数据来源：Kaggle 比赛页、讨论版（按最近评论排序）、两条高热度讨论帖（708586、732331）
> 可信度标注：`[事实]` = 直接从官方/讨论抓取；`[推断]` = 基于讨论与赛制推导；`[未抓取]` = 目标页面动态加载未能自动提取，需自行打开核对

---

## 0. 基本信息速览

| 项目 | 内容 |
|---|---|
| 比赛全称 | The Pokémon Company - PTCG AI Battle Challenge Simulation |
| 主办方 | The Pokémon Company - PTCGABC Team |
| 任务 | 搭建一个 **AI Training Agent** 来自动对战 Pokémon Trading Card Game（宝可梦卡牌） |
| 标签 | Games / Artificial Intelligence / Reinforcement Learning |
| 评分 | Custom Metric（自定义，基于模拟对战的 ELO/rating 体系）|
| 参与规模 `[事实]` | 14,175 Entrants / 7,941 Participants / 6,701 Teams / 12,742 Submissions |
| 关键时间 `[事实+用户]` | Kaggle 页显示 "Close 6 days to go"（约 8/16）；**用户跟踪：8/14 停止提交 → 2 周封闭榜 → 最终成绩即初赛最终成绩** |
| 公开 Notebook 分享截止 `[事实]` | 已于 **8/2** 截止（帖 728935）|
| 双赛道 | 第一轮的 **Simulation（模拟）** + **Strategy（策略）** 两个 Category |

> ⚠️ 时间节点请以比赛页 Leaderboard / 官方公告为准。Kaggle 倒计时（≈8/16）与你说的 8/14 提交截止略有出入，建议核对确切 cutoff。

---

## 1. 比赛机制与赛制

### 1.1 第一轮：双赛道，缺一不可晋级
`[事实，来源：帖 732331 / 比赛结构]`

- **Simulation Category**：提交能自动打牌的 Agent，在官方模拟器里 AI vs AI 对战，按 ELO/rating 排榜。
- **Strategy Category**：比**卡组构筑 + 方案原创性 + 报告质量**。模拟榜排名会被"参考"，但**不是唯一决定因素**，综合评估。
- **晋级硬条件**：想在 Simulation 赛道晋级第二轮，**同一支队伍必须同时参加 Strategy 赛道**（用同一队）。

### 1.2 第二轮（Top 8，东京线下）`[事实，来源：帖 732331]`
- 第一轮 Strategy 结束后，**Top 8 队伍**晋级，东京**线下**举办。弃赛则顺延替补。
- **赛制变化**：
  - **BO3（三局两胜）**，同卡组、同代码打满整场；
  - **顺序进行**（非同时）：第 2 局可看第 1 局 log，第 3 局可看前两局 log → 信息利用与稳定性变关键；
  - **思考时间**：每局 **30 分钟总思考时间**，BO3 各局独立计时、不累计；**超时即判该局负**。
- **算力上限**：AWS p5.4xlarge 同级 / NVIDIA H100（80GB）/ 256 GiB RAM / 16 vCPU。
- **卡池**：第一轮所有卡可用 + **扩充卡池**（细节在 Simulation 最终排名确认后公布）。
- 官网：https://ptcg-abc.pokemon.co.jp/

---

## 2. 讨论区要点梳理

> 按主题归类，标注热度（👍 upvote / 💬 评论数）与时效。链接前缀均为 `https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/`

### 2.1 官方资源类（必看，节省大量时间）
| 帖 | 标题 | 热度 | 说明 |
|---|---|---|---|
| 717141 | Game Engine Source Code | 👍125 / 💬11 | **最热帖**。官方放出模拟器源码，环境搭建的根基 |
| 709160 | Daily Top Episodes Datasets | 👍76 / 💬5 | Bovard 分享每日 Top 对局数据集，RL 训练金矿 |
| 713051 | Official Visualiser/Replay Viewer | 👍25 / 💬2 | Addison Howard 放出官方回放/可视化工具，看自己的对局 |
| 708492 | How to Get Started + Official Discord | 👍16 / 💬4 | 入门指南 + 官方 Discord 入口 |
| 728935 | Public Notebook Sharing Deadline: Aug 2 | 👍20 / 💬11 | 公开 notebook 分享截止（已过）|

### 2.2 规则 / 赛制澄清类（避坑）
| 帖 | 标题 | 热度 | 说明 |
|---|---|---|---|
| 708586 | Differences Between Official TCG Rules & Simulator Behavior | 👍36 / 💬27 | **官方逐条列出模拟器与正版规则的差异**（见第 3 节详述）|
| 732331 | Second Round Information | 👍24 / 💬18 | 第二轮赛制全貌（见 1.2）|
| 714189 | Reminder about Kaggle Simulation Competition Format | 👍16 / 💬8 | 模拟赛制提醒 |
| 708493 | Important Information About this Challenge | 👍16 / 💬1 | 总览性重要信息 |
| 708584 | Welcome 帖 | 👍30 / 💬4 | 官方欢迎与总览 |

### 2.3 技术讨论类（策略灵感）
| 帖 | 标题 | 热度 | 说明 |
|---|---|---|---|
| 731298 | my plan on how to do RL training ... is it my hallucinations? | 👍12 / 💬16 | hengck23 的 RL 训练思路 + 社区纠错，**训练方向必读** `[未抓取正文]` |
| 733995 | From Simulation ladder to Strategy top 8: confirmed vs needs clarification | 近期 | 梳理"模拟天梯→策略 Top8"已确认/待澄清项 `[未抓取正文]` |
| 733267 | Shaymin vs Battle Cage | 💬4 | 具体卡牌/机制对局讨论 |
| 733811 | Local environment help | 💬8 | 本地环境搭建求助（新手常踩）|

### 2.4 问题 / Bug / 坑类（近期活跃）
| 帖 | 标题 | 时效 | 说明 |
|---|---|---|---|
| 734166 | Missed Team Merger Deadline and Duplicate Submissions | 24 分钟前 | 队伍合并截止已过 + 重复提交问题 → 组队/提交要合规 |
| 733137 | Timing of solution sharing after the deadline | 1 小时前 | 截止后方案分享时机（Addison Howard 已回复）|
| 733083 | **ELO inconsistency** | 9 小时前 / 💬9 | 参与者发现 ELO 计算不一致 → 见第 4 节 `[未抓取正文]` |
| 734065 | ApiBattleStart rejects decks with a bare integer（错误码对照）| 18 小时前 | 提交 API 报错码速查 |
| 734027 | Watching your games locally, without uploading | 21 小时前 | 本地看对局（不上传）技巧 |
| 733975 | **Engine Bug**：Koraidon ex（卡 979）英文攻击名/文本整体偏移一位 | 1 天前 | 具体卡牌引擎 bug → 验证卡牌行为时留意 |

---

## 3. 榜单与卡组 Meta 分析 `[部分未抓取]`

### 3.1 目标 notebook
- myso1987：**PTCG AI Battle Leaderboard Deck Meta by Score Band**
  https://www.kaggle.com/code/myso1987/ptcg-ai-battle-leaderboard-deck-meta-by-score-band

### 3.2 抓取状态与说明 `[未抓取]`
该 notebook 正文为 JS 动态加载，本环境无 Kaggle 登录凭据，**两次抓取均只拿到 cookie 页 / 元数据，未能提取正文**。因此下面的内容是**基于讨论与赛制的推断**，具体卡组名称、各分数段占比、图表结论**请以你打开 notebook 为准**。

### 3.3 可推断的方法论与用途 `[推断]`
- 该 notebook 按**分数段（score band）**切分当前榜单，统计各卡组原型（archetype）在每个 band 的出现率/胜率，用来回答"高分榜靠什么卡组"。
- 实战价值：`[推断]` 若高分 band 高度集中某几套卡组，说明meta 固化 → 要么照搬该 meta 卡组 + 更强 Agent，要么找 counter；若分布分散，则 Agent 强度 > 卡组选择。
- 行动建议：打开 notebook 后重点看 (a) 各 band 的 top 卡组列表、(b) 是否存在"低分 band 强、高分 band 弱"的陷阱卡组、(c) 作者结论。

---

## 4. Rating 与 Matchmaking 分析 `[部分未抓取]`

### 4.1 目标 notebook
- keidroid：**PTCG AI Battle Rating and Matchmaking Analysis**（v5，运行 26s，Apache 2.0）
  https://www.kaggle.com/code/keidroid/ptcg-ai-battle-rating-and-matchmaking-analysis

### 4.2 抓取状态 `[未抓取]`
同上，正文未能自动提取。以下为**讨论 + 赛制推导**。

### 4.3 已知线索
- 评分体系为 **ELO/rating 类**（参赛者普遍用 "ELO" 指代）。
- 讨论帖 **733083「ELO inconsistency」**（近期、💬9，活跃争论）：参与者发现 ELO 计算存在**不一致/异常** → 意味着榜单分数可能带噪声，单场波动大时名次不可全信。`[事实：存在该争议帖；推断：分数有噪声]`
- 模拟赛采用**匹配（matchmaking）**机制把 Agent 配对对战，`[推断]` 高分 Agent 更可能互相对打，rating 收敛受匹配池影响。

### 4.4 对参赛的启示 `[推断]`
- 因为是 rating 制，**多提交、多对局**有助于 rating 收敛到真实水平，但需注意 8/14 后进入封闭榜（2 周），封闭期内的对局即最终成绩。
- 若 ELO 确有不一致，短期冲分可能被噪声放大，**稳健的 Agent + 足够的对局量**比赌一把更可靠。
- 详细数值（rating 分布、匹配算法、与分数的映射）请打开 keidroid notebook 核对。

---

## 5. 参赛 / 上分策略（行动清单）

### 阶段 A：环境搭建（立即）
1. `[事实]` 拉取 **Game Engine Source Code（帖 717141）**，本地跑通模拟器。
2. `[事实]` 用 **Official Visualiser（帖 713051）** 看回放，理解状态空间与合法动作。
3. `[事实]` 下载 **Daily Top Episodes Datasets（帖 709160）** 作为训练/蒸馏数据。
4. 加入 **官方 Discord（帖 708492）**，实时跟公告与答疑。

### 阶段 B：训练 Agent
5. 参考 **帖 731298（RL 训练思路）** 的社区讨论定方案（RL / 搜索 / 规则混合）。`[未抓取正文，需自行阅读]`
6. 注意**模拟器 ≠ 正版规则**（见 5.1），训练目标要对齐模拟器行为，否则线上掉分。
7. 留意已知引擎 bug（如 **Koraidon ex 文本偏移，帖 733975**），验证关键卡牌效果。

### 阶段 C：避坑（来自官方规则差异帖 708586）`[事实]`
- **模拟器行为 = 本次比赛的正确行为**，不要按正版规则"纠错"。
- 三类已知差异（影响极小但要知道）：
  1. 某些攻击在模拟器中**根本不可选**（正版可声明但效果无法结算）→ 模拟器直接禁选；
  2. **Mega Zygarde ex「Nullifying Zero」**：目标顺序模拟器强制左→右自动抛币（正版可选顺序），但 KO 同时处理，不影响结果；
  3. **双方同时 KO 时的拿奖顺序**不同（官方 vs 模拟器顺序见帖原文），但若双方最终都拿满奖则判**平局**，不影响胜负。
- 官方承诺若发现新差异会在讨论区补充公告 → 定期刷帖。

### 阶段 D：双赛道（晋级硬门槛）
8. `[事实]` 想进二轮，**必须同队参加 Strategy 赛道**：准备**卡组构筑 + 原创方案 + 高质量报告**。
9. 模拟榜排名只是"参考"，Strategy 维度的质量权重不低 → 别只卷模拟分。

### 阶段 E：冲击 / 收尾
10. **8/14 前**完成最终提交（确认确切 cutoff，Kaggle 显示约 8/16，以官方为准）。
11. 封闭榜 2 周期间对局即最终成绩 → 提交前充分自测，避免上线即定生死。
12. 若目标 Top8：提前按 **BO3 / 30 分钟思考上限 / 可看历史 log / 超时判负** 的二轮规则做压力测试与一致性优化。

---

## 6. 参考链接清单

**比赛与讨论**
- 比赛主页：https://www.kaggle.com/competitions/pokemon-tcg-ai-battle
- 讨论版（最近评论）：https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion?sort=recent-comments
- ⚠️ 你最初给的"leaderboard 链接"与讨论版是同一个 URL（疑似复制串了）；真实榜单在比赛页 **Leaderboard** 标签。

**分析 notebook（未自动抓取正文，请自行打开）**
- 卡组 meta：https://www.kaggle.com/code/myso1987/ptcg-ai-battle-leaderboard-deck-meta-by-score-band
- Rating/Matchmaking：https://www.kaggle.com/code/keidroid/ptcg-ai-battle-rating-and-matchmaking-analysis

**官方资源帖（discussion/ 前缀）**
- 708586 规则差异｜732331 第二轮赛制｜717141 引擎源码｜709160 每日对局数据集｜713051 官方回放器｜728935 公开notebook截止｜714189 模拟赛制提醒｜708492 入门+Discord｜731298 RL训练思路｜733083 ELO不一致｜733975 Koraidon bug｜734027 本地看对局｜734065 提交API错误码

**其他**
- Strategy 赛道评分：https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy/overview/evaluation
- 二轮官网：https://ptcg-abc.pokemon.co.jp/

---

## 7. 数据来源与可信度说明

- **已直接抓取（高可信）**：比赛页统计、讨论版热门帖清单及热度、帖 708586（规则差异全文）、帖 732331（二轮赛制全文）。
- **基于讨论/赛制推断（中可信）**：meta 分析方法论、rating 噪声影响、各阶段策略建议。
- **未能自动抓取（需你核对）**：两个分析 notebook 正文、以及 731298 / 733083 / 733995 等讨论帖的正文（Kaggle 动态渲染 + 需登录）。相关结论已在文中明确标注 `[未抓取]`，并给出直接链接。
- **时间节点**：8/14 提交截止为你跟踪信息；Kaggle 倒计时显示约 8/16，务必以官方 Leaderboard/公告为准。
