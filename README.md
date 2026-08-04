# Pokemon TCG AI Battle Challenge —— v23.1 Mega Lucario ex Agent

参加 Kaggle [Pokemon TCG AI Battle Challenge](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle)
的提交方案。当前主线为 **v23.1 メガルカリオex 能量循环墙推** 单文件 Agent
（2026-08-04 提交评分 600.0，历史最高）。

---

## 当前 Agent 概览 (v23.1)

**卡组 (60 张, `deck.csv`, 与 `main.py` 内联 `_INLINE_DECK` 一致):**

| 类型 | 卡 | 数量 | 作用 |
|------|----|------|------|
| 宝可梦 | 678 メガルカリオex (闘/340HP/Mega ex) | 3 | 主力打手: メガブレイブ 270 + オーラジャブ 130 回收 |
| 宝可梦 | 677 リオル (闘/80HP) | 3 | 进化链基础 |
| 宝可梦 | 675 ルナトーン (闘/110HP) | 2 | 特性 ルナサイクル: 弃1斗能抽3 |
| 宝可梦 | 676 ソルロック (闘/110HP) | 2 | コズミックビーム 70 无视效果 |
| 宝可梦 | 674 ハリテヤマ (闘/150HP) | 2 | 破墙: ワイルドプレス 210, 非 ex 免疫限制 |
| 宝可梦 | 673 マクノシタ (闘/80HP) | 2 | 进化链基础 |
| 训练家 | ゴング/リーリエ/ポケパッド/ハイパーボール 等 | 29 | 检索/抽牌/治疗/干扰/增伤 |
| 能量 | 闘×13 + ロック闘×4 | 17 | 斗系能量体系 |

**决策链 (18 步 + 前置耗牌):** 盾牌耗牌(打不动时磨光对手牌库) → KO 攻击(含弱点×2, 节能选最低伤害) → 铺场 → 进化 678 成核心 → 进化 674 破墙 → 678 满能斩杀 → 冲刺模式 → 训练家时机 → 进化 → 贴能(辅助满能时能量改道给 678) → 攻击 → 出训练家/宝可梦 → bench 贴能 → 特性(ルナサイクル) → 兜底攻击 → 切换(678↔辅助, 奖赏节奏) → END。

**核心制胜公式:** 678 メガルカリオex 340HP 站场 + 270 斩杀 + 1-Prize 辅助过渡（奖赏节奏不对称）。

---

## 文件结构（当前）

```
.
├── main.py           # 提交入口: v23.1 自包含 Agent (内联牌组 + 全量卡库 1267 卡)
├── deck.csv          # 60 张卡 (单一牌组来源, main.py 启动时读取)
├── pack.sh           # 打包 + DECK/deck.csv 一致性交叉校验 → submission.tar.gz
├── submit.py / submit.sh  # KGAT 提交/状态/天梯/本地验证
├── test_agent.py     # 本地单元测试
├── replay_regression_test.py  # 真实回放回归测试
├── gen_card_db.py    # [开发工具] 从官方 CSV 生成 _CARD_DB 内联数据
├── merge.py          # [开发工具] 旧模块化 Agent 合并器 (默认禁止覆盖 main.py)
├── sdk/              # cabt 引擎源码副本 (仅供阅读, 不参与提交)
├── pokemon-tcg-ai-battle-challenge-strategy/  # 官方卡牌数据 CSV + 分析 (开发用)
├── inference/        # 回放复盘 (subm_rec1-13) + TopRatedEpisodes + leaderboard_replay
├── battle-system-eval/    # 战斗系统评估报告 (HTML, 2026-08-04)
├── architecture-logic/    # 项目架构与逻辑关系文档 (HTML, 2026-08-04)
└── submission/       # 提交暂存 (已同步当前 main.py + deck.csv, 与根目录一致)
```

> 历史文件: `rule_agent.py`、`gen_deck.py`、`build_deck.py`、`analyze_cards.py`、
> `card_meta.py`/`option_scorer.py`/`state_parser.py`/`decision_gate.py`/`handlers.py`/
> `main_entry.py`(旧模块化 Agent)、`inference/main_v6.py`、`optimized_deck.csv`、
> `deck_mega_wall.csv`、`deck_v21_backup.csv` 等均为早期方案遗留, 不参与提交。

---

## 使用步骤

```bash
# 1. 打包提交 (含交叉校验: main.py DECK 必须与 deck.csv 一致)
bash pack.sh

# 2. 本地验证提交包
bash submit.sh validate-local

# 3. 提交到 Kaggle
bash submit.sh submit

# 4. 查看状态 / 天梯
bash submit.sh status
bash submit.sh leaderboard
```

---

## 关键设计原则

1. **单文件自包含**: main.py 仅用标准库, 提交只需 `main.py + deck.csv`。
2. **牌组单一来源**: `main.py` 启动时读取 `deck.csv`, 缺失/非法才回退内联
   `_INLINE_DECK`; `pack.sh` 强制校验两者一致, 杜绝双源漂移。
3. **全量卡库**: `_CARD_DB` 由官方卡池 CSV (1267 卡) 生成, 覆盖 1056 张宝可梦
   (hp/属性/弱点/rule 含 ex 与 mega_ex/进化链/最大伤害), 敌方 ex 识别与
   弱点×2 计算基于真实数据。重新生成: `python3 gen_card_db.py --inline main.py`。
4. **弱点归一化**: 引擎 weakness 的多种格式 (日文/英文缩写/全称/数字枚举)
   统一映射为规范日文属性后比较。
5. **无跨局状态**: 换墙意图标志只允许存活一次 Main→Card 决策, 新对局/非选卡
   决策自动清空, 防止污染下一局。
6. **动作铁律**: 返回长度 == maxCount、下标合法、无重复; 任何异常走确定性兜底。
7. **稳定性验证**: 148,772 次真实对局决策 0 崩溃 0 非法动作; 功能测试 17/17,
   bug 回归 7/7, 压力测试 37,556 次决策全部通过。

---

## 版本演化

| 版本 | 评分 | 说明 |
|------|------|------|
| v23.1 | 600.0 | 当前: P1 策略调优(节能KO+能量改道) + 3 bug 修复 |
| v23 | 600.0 | Mega Lucario ex 能量循环墙推体系 (0804 Top3 实证) |
| v22.5 | 471.6 | 动态墙切换 + 被动换人修复 |
| v22.4 | 414.4 | 345 墙破墙 + 换墙意图传递 |
| v22 | 371.3 | Mega Wall Push 756 + 345 墙推 |
| v12 | 499.4 | マリィ/オーロンゲex 暗系 Meta |

---

## 历史文档

- `README_supplement.md` — 早期"随机 Agent → 规则 Agent → Alakazam 卡组"路线
  (已废弃, 仅供回溯)。
- `PROJECT_ADJUSTMENT.md` — 早期卡组/策略调整建议 (已废弃, 仅供回溯)。
- `bug_audit_report.html` / `deck_v7_analysis.html` — 早期分析报告。
- `battle-system-eval/` — 2026-08-04 战斗系统评估报告 (平衡性/流畅度/视觉/体验)。
- `architecture-logic/` — 2026-08-04 项目架构与核心逻辑关系文档。

模拟赛道截止: 2026-08-16 23:59 UTC。
