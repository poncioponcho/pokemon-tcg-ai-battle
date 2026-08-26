# 外部对标情报消化 — 2026-08-10 晚（peer 清单 + 实抓验证）

## 1. Kazuta MIZUTA（#9 全球，Mega Lucario ex ≈1005）—— 已抓到全文 ✅

方法三件套（原话）：**beam search + Bayesian opponent archetype detection + information-set Monte Carlo**。

对我们的映射：
- 这**正是 ledger#77 里 deferred 的 C 方向（搜索 oracle）的外部成功样本**——且证明 Lucario  archetype 能到 ~1005（meta notebook 显示 1100+ 仅 1 支 Lucario，大概率就是他）。
- 「Lucario 悬崖是卡组上限」假说进一步被削弱：上限在**驾驶者**，搜索范式是破局路径。
- 他自述"纯算法策略、无预训练模型"——与我们纯规则主轴同源，说明搜索层是在规则 agent 之上叠加的，不是推倒重来。
- 他的教训（误把某卡当 ACE SPEC，1005→659）与我们今晚 M2 抓到的静默失效同坑类：**卡数据正确性是最致命回归源**——M2 校验 + 双引号截断修复正好是这个方向的加固，已被独立背书。
- 他"正在做 replay analysis + energy routing optimization"——energy routing 正是我们 F2 守成层/Q4 能量去向的同一条线，方向吻合。

落地约束（现实评估）：Kaggle kernel 有单步时限，我们 agent 是纯 Python（~150 局/秒本地）；beam search/IS-MCTS 的工程量大，4 天窗口内全量实现不现实。**候选折衷 = 1-ply beam（用规则 agent 做 rollout 评估叶子）**，即 C 方向的最小可行版——是否解禁，等明早 v4 结算拍板时定。

## 2. Abhyuday「从 Daily Top Episodes 做 BC」—— Kaggle 帖被 cookie 墙挡住 ⚠️ 需人工

peer 转述要点：挑强队 episode 做 behavioural cloning，「1/100 算力拿到和 RL 一样的结果，先验证架构再动 RL」。

与我们既有证据的关系（重要，防重复踩坑）：
- [2026-08-10 更正] 本节此前表述有误：我们的 NN 线**并非**克隆自己的规则 teacher。据 `inference/dataset/PROJECT_EVALUATION_REPORT.md`（2026-08-05）：BC+AWR 就是在 **4,432 条榜单精英 replay / 525,371 决策**上训的（fixed-test top1 0.5332 / canary 0.5432，模型 `inference/dataset/data/model_awr.pt`）——「换 teacher 克隆高分 bot」**已经做过**。
- 实测 elite-match（5,479 真实决策点）：NN 0.377 vs 规则 0.218；攻击 ctx=7 **0.388 vs 0.118（3.3×）**——NN 在模仿精英上全面优于规则，尤其攻击选择。
- 真正卡点是**部署**：Kaggle 无 torch；npz 蒸馏 student 保真崩塌（teacher canary 0.5432 → student 断崖），hybrid 接入有门禁 REJECTED 前科（ledger#77 关闭 A/D 的根据在此，不在训练侧）。
- **结论（修正后）：该方向的活路不是再训练，而是把 NN 已学到的精英知识蒸馏回规则**——用 model_awr.pt 当诊断器，找规则与精英分歧最大的攻击局面 → 手写规则修复。这正是 peer 08-10 映射第 1 条，已列为今晚主任务。

## 3. Daily Top Episodes 数据集 —— 本地已有存量，无需重下 ✅

`inference/leaderboard_replay/archive/`：all_replays.jsonl.zst（1.7GB）+ official_bulk_2026-07-30.jsonl.zst（331MB）+ episode_catalog.jsonl 19,834 条（含 rank/score_at_capture）。
peer 链接是 2026-07-10 版；我们已有 07-30 bulk。**若非要最新日期才需用户登录 Kaggle 下载（可选，非必需）。**

## 4. 未能自动抓取、需人工阅读的清单

| 项 | 链接/位置 | 状态 |
|---|---|---|
| Strategy 赛道 evaluation / rules / discussion 三页 | peer 清单 #7 | cookie 墙 ⚠️ |
| #731298 hengck23 RL 训练思路帖 | 讨论版 | cookie 墙 ⚠️ |
| 「Things I tried that didn't work」(Yohei Nakajima) | 讨论版搜标题 | 未抓 ⚠️ |
| 「0 DMG attack [Solved]」引擎 bug 帖 (danielwatabe) | 讨论版近期 | 未抓 ⚠️ |
| 「First or second — which do agents pick?」(e-toppo) | 讨论版 | 未抓 ⚠️（正对 Q3 诊断方向） |

引擎 bug 自查备注：我们的攻击选择走 _estimate_attack_damage + P1 只选 dmg≥KO 的攻击，不会主动选 0 伤攻击；但「0 DMG attack」帖的具体触发条件未读，**不能断言免疫**——需人工读帖确认。

## 5. Strategy 报告骨架 —— 已起草 ✅

见 `pokemon-tcg-ai-battle-challenge-strategy/STRATEGY_REPORT_SKELETON.md`。
已有素材：该目录已有卡表清洗/OCR 审计工具链（CSV_Final_Audit_Report.html 等）；骨架按「卡组构筑 + 原创性 + 报告质量」三评维起草，正文需用户写。

## 5. hengck23「RL 训练计划」帖 (#731298, docx 已读) —— 对手在做"回放→策略→规则bot"流水线

来源: inference/__pycache__/my plan on how to do RL training ... is it my hallucinations.docx (5 张截图, 正文已提取)。

要点:
- 背景: CV/LLM 出身, 没做过决策系统, 自承"imaginations"。核心方法 = **agent swamp**:
  chatgpt 当 PTCG 策略师分析 LB 回放 → 提炼 strategy (牌组/布局/动作序列/胜负原因) →
  chatgpt 当 coder 把策略写成规则 bot (不抄选项下标, 复制意图与优先级) → IL/BC 训练数据。
- 已落地: 败局分析报告 ptcg_loss_knockout_report.csv (每个 KO 一行: 死前HP/伤害/attackId/
  对手铺垫动作/推断死因/建议修复) + ptcg_loss_match_summary.csv; 并为 Marnie's Grimmsnarl
  (episode 88851349, attack 937) 写了一个"回放启发规则对手"。
- 三层训练对手设计: exact replay policy → **strategy-preserving perturbed opponent** (主训练对手:
  扰动牌组/起手/抽序/奖品位/先后手/辅助怪/检索数/攻击时机/目标选择/备用打手) → RL 混合。
- 有张我们牌型 (Lucario 线) 的动作序列桑基图 (win/loss 分流) —— 对手在解剖我们的 archetype。

对我们的意义:
1. **方向验证**: 严肃对手也在做"精英知识蒸馏回规则" —— 我们 peer 映射第 1 条 (攻击蒸馏诊断)
   与之同族但更直接 (NN 诊断器 + 30k 决策定量)。不是孤独的错误路线。
2. 他们的 knockout 报告结构比我们 vsfirst_diagnose 更围绕 KO 事件 —— 若做败局报告 v2 可借鉴
   (每个 KO 记对手铺垫链 + 死因推断)。
3. RL/扰动训练对手线: 4 天窗口不现实, 维持 ledger#77 关闭结论不变。
