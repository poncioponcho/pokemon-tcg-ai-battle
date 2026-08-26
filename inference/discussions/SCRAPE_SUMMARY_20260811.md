# 讨论区/Discord 抓取总结（2026-08-11 09:15，webbridge via Brave）

## Kazuta 1005 溯源结论：Kaggle 公开面不存在

| 渠道 | 覆盖 | 结果 |
|---|---|---|
| 竞赛论坛主题列表 | 4 页 ~80 主题 | 无 Kazuta/beam/1005 |
| 论坛全文（12 重点帖） | grep kazuta/beam/bayesian/IS-MCTS/1005 | 零命中 |
| 论坛自带搜索 | "Kazuta" | 零主题 |
| Kaggle Discord 全服搜索（已验证机制有效，Sylveon 对照组命中） | Kazuta / 1005 / Bayesian / beam / opponent | pokemon 频道全零；Bayesian 17 命中全在别的频道 |
| Kaggle kernels | 作者 Kazuta MIZUTA 仅 1 篇公开（新手向导，23 票） | 无 1005 方法帖 |

→ 「Kazuta 的 1005 = beam + Bayesian 对手原型检测 + IS-MCTS」这条信息的来源不在 Kaggle 论坛/Discord/公开笔记本。可能在 X/note/Qiita/YouTube 或私下交流。若找到原始链接给我，我再抓。
→ 近缘真实人物：Kazuta MIZUTA（kazutamizuta，新手向导作者）；Kiyotah（官方 RL/MCTS sample 作者，见下）。

## 真正抓到手的高价值情报

### 赛制/工程约束
- **每队每局共 600s、无单步时限、CPU 1.6 vCPU / 8GB**（729219，Omkar Kadam/Mikael Kerimov 引官方）→ beam 37ms/决策 × ~20 次/局 ≈ 0.74s，预算无压力。
- 对手牌组在对局 logs 中透明 → 历史追踪+卡表计数可推剩余牌组（729793 ft.dev 提出，0 评论无人反驳）。
- ELO 大幅波动实证（733083）：同 agent 两发差 400 分、放 1-2 天才稳（ntumlnoob 第 10 名佐证）、官方称正常 → 支持瞬读不记账铁律。

### 方法生态（来自 728168/729644/729219 等）
- 纯启发式天花板：~top 10-20 / 880±20 分段（多人佐证）；gold 区间已被 model-based 占据（wangyuou, 139th）。
- sam_the_rice_cake（202nd, 850-900）：**BC/rollout 的离线提升不能迁移到 LB**——与我们 NN 克隆线证伪结论一致。
- wangyuou（139th）：BC+规则守卫混合 ~1000 分。
- Discord MCTS 讨论（6-7 月）：Vedant A.「我的 MCTS 破不了 1000」；thekaggleator「search api 明显在往 MCTS 方向引导」；官方 Kiyotah RL/MCTS sample（kaggle.com/code/kiyotah/reinforcement-learning-and-mcts-sample-code）+ 论坛 709304（sample rerun 教训）。

### Meta 动态（Sumi 两帖，220th，74,634→209,772 局全量分类）
- 四纪元：Crustle/Lucario（6 月中）→ Archaludon 泡沫（6/26-7/2，9%→41%→3%）→ Alakazam 平台期（7 月上中，峰值 46%）→ **Grimmsnarl 接管（7/26 达 51.3%，#1 和 top-25 主力）**。
- **Mega Lucario 顶部分段 7/26 已 0.03% 接近灭绝**（field WR 47%→35% 后遭弃）——⚠️ 我们 archetype 的 meta 地位预警（注意：8 月 Majkel1337 用 Lucario 回 rank1，meta 未死但在走钢丝）。
- matchup 循环：Grimmsnarl > Alakazam 57%；Alakazam > Garchomp 64%；Garchomp > Grimmsnarl 59%；**Tarountula > Alakazam 72%（专职猎手）**。
- 730823 方法论：Pr(i≻j)=σ(si−sj+Mab+zSab)，牌组/牌手强度分离——Majkel1337（技能 rank2，13,175 局）7 月开 Alakazam 让该牌组虚高。
- 「抄排行榜必死」定律：牌组可见占优时其 EV 已在回归（Archaludon 65%→26% 全程 3 周）。

### M3 直接资产
- **22-archetype 标注牌组数据集**（A.S.TENSHU，帖 730554）：22 套验证过的 60 张 + 战略标签 + 22×22 相似度矩阵 + 单行卡 ID 导出 → 对手牌组识别器的训练/评测集。
- 公开高分笔记本（CLI 可下载）：**makthanithin/pokemon-tcg-ai-battle-1084-5-baseline（8/9 还在跑）**、romanrozen LB950+ V10、jazivxt/codex-sol-eclipse-alakazam（Alakazam 专场）、pixiux/ptcg-mega-lucario-ex-v62。
- 我们自有的 meta_decks_raw.jsonl（4500 局带 archetype 标签与完整 60 张）。

## 落盘文件
- 论坛全文 12 帖：inference/discussions/{708492 未抓, 717697, 723591, 728168, 729219, 729644, 729793, 729926, 730155, 730554, 730823, 731298, 733083}.txt
- Discord 搜索为在线交互式，结果已并入本文件。
