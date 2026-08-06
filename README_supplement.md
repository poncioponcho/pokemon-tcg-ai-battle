# ⚠️ 历史文档（已废弃，仅供回溯）

> **本文档描述的是早期开发路线（随机 Agent → 规则 Agent → Alakazam 卡组），
> 已被 v22.x Mega Wall Push Agent 取代。当前实现请见 [README.md](README.md)。**

# 补充说明：从 Baseline 到规则 Agent + 胡地卡组

本文档在 [README.md](README.md) 基础上补充三个主题：
1. 获取官方完整 CardPool.csv
2. 规则 Agent 迭代策略（每天 5 次提交怎么花）
3. Alakazam（胡地）卡组线索

---

## 一、获取官方完整 CardPool.csv

### 方式 A：Kaggle Notebook 直接探索（推荐）

在 Kaggle 上创建 Notebook，选择比赛数据源后，直接运行 `kaggle_explore.py`：

```python
# 把 kaggle_explore.py 内容粘贴到 Notebook cell 中，或：
from kaggle_explore import main
main()
```

这会自动：
- 通过引擎 API `all_card_data()` 获取完整卡池（约 2000 张卡）
- 搜索 Alakazam / Abra / Kadabra 的卡 ID
- 生成 `alakazam_deck.csv`
- 导出 `CardPool_full.csv` 供本地使用
- 跑 3 场测试对局

### 方式 B：Kaggle CLI 下载（需要 kaggle.json 或 KGAT token）

```bash
# 如果有 kaggle.json：
pip install kaggle
mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json
kaggle competitions download -c pokemon-tcg-ai-battle
unzip pokemon-tcg-ai-battle.zip

# 如果有 KGAT token（当前使用的方式）：
export KAGGLE_API_TOKEN="KGAT_xxx"
python3 submit.py download-cardpool
```

### 方式 C：引擎内置 API（Linux 环境）

在 Kaggle Notebook 中直接调用：

```python
from kaggle_environments.envs.cabt.cg.api import all_card_data, all_attack

cards = all_card_data()   # 所有卡牌元数据
attacks = all_attack()    # 所有攻击信息

# 搜索胡地
for c in cards:
    if "alakazam" in c.get("name", "").lower():
        print(c)
```

---

## 二、规则 Agent 迭代策略（每天 5 次提交）

### 提交前的准备

```bash
# 1. 把 rule_agent.py 复制为 main.py（替换随机 Agent）
cp rule_agent.py main.py

# 2. 本地验证
bash submit.sh validate-local

# 3. 打包
bash pack.sh

# 4. 提交
bash submit.sh submit

# 5. 查看状态
bash submit.sh status
```

### Day 1（2 次提交）

| # | 改动 | 预期效果 |
|---|------|---------|
| 1 | 提交当前 `main.py`（随机 Agent）→ 获取 baseline μ 分 | 建立基准线 |
| 2 | 替换为 `rule_agent.py`，只改 `handle_main`：ATTACK 优先于 END | 看主动攻击是否提分 |

### Day 2（2 次提交）

| # | 改动 | 预期效果 |
|---|------|---------|
| 3 | 在 Kaggle Notebook 跑 `kaggle_explore.py`，拿到 Alakazam 卡 ID → 生成 `alakazam_deck.csv` → 替换 `deck.csv` | 卡组更稳定 |
| 4 | 改 `handle_attack`：优先选伤害最高的攻击；如果对方 HP 低，选能击杀的 | 减少浪费回合 |

### Day 3（1 次提交）

| # | 改动 | 预期效果 |
|---|------|---------|
| 5 | 改 `handle_card`：SETUP 时优先铺 Abra；SWITCH 时选 HP 最高/有能量的 | 开局更稳 |

### 每次提交后

1. **查看状态**：`bash submit.sh status` —— 等待验证赛通过
2. **查看天梯**：`bash submit.sh leaderboard` —— 看 μ 分变化
3. **下载回放**：在 Kaggle 比赛页面下载 episode replay
4. **分析失误**：用 `obs["logs"]` 分析哪些回合决策失误，针对性改下一个分支

### 各分支优化收益预估

| 分支 | 当前策略 | 填充后收益 | 难度 |
|------|---------|-----------|------|
| `handle_main` | ATTACK > ATTACH > EVOLVE > PLAY > RETREAT > END | 高：让 Agent 知道该攻击时攻击，该结束时结束 | 低 |
| `handle_attack` | 选最后一个 | 最高：选错攻击 = 浪费回合 | 中 |
| `handle_yes_no` | IS_FIRST=YES, MULLIGAN=NO | 中：MULLIGAN 时检查手牌 | 低 |
| `handle_card` | 选第一个 | 中：SETUP 时优先铺 Abra，撤退时选 HP 高的 | 中 |
| `handle_energy` | 选第一个 | 中：贴能给 Alakazam 或前场主力 | 低 |

---

## 三、Alakazam（胡地）卡组线索

### 为什么选胡地？

- Kaggle Discussion 提到 Alakazam + Dudunsparce 组合在当前卡池中表现稳定
- Alakazam 是 Psychic 属性，其攻击可能与对方能量数或手牌数挂钩
- 进化链 Abra → Kadabra → Alakazam 是经典三段进化，HP 递增

### 胡地进化链

```
Abra (基础, HP~50)  →  Kadabra (一阶, HP~80)  →  Alakazam (二阶, HP~130)
```

### 关键攻击（需在 Kaggle 确认）

| 宝可梦 | 攻击名 | 预期效果 | 伤害 |
|--------|--------|---------|------|
| Alakazam | Psychic | 对方能量越多伤害越高 | 10+ (30/能量) |
| Alakazam | Powerful Hand | 对方手牌越多伤害越高 | 10+ (10/手牌) |
| Alakazam | Mind Jack | 对方备战区越多伤害越高 | 30+ (30/备战) |

> 以上攻击名为推测，具体需在 Kaggle Notebook 中用 `all_attack()` 确认。

### 卡组构成建议

| 类型 | 卡名 | 数量 | 理由 |
|------|------|------|------|
| 基础宝可梦 | Abra | 4 | 进化起点，开局必须 |
| 一阶进化 | Kadabra | 3 | 中间过渡 |
| 二阶进化 | Alakazam | 3 | 主力输出 |
| 备用打手 | Dudunsparce | 2 | 对抗特殊属性 |
| 基础能量 | Psychic | 12 | 胡地主属性 |
| 基础能量 | Colorless | 4 | 部分攻击需要 |
| 支援者 | Professor's Research 等 | 4-8 | 抽牌/检索 |
| 道具 | Ultra Ball 等 | 4 | 检索宝可梦 |
| 工具 | Choice Band 等 | 2-4 | 增伤 |
| 场馆 | 1-2 | 2 | 辅助效果 |

### 卡组验证

在 Kaggle Notebook 中用 `kaggle_explore.py` 的 `run_test_battle()` 跑测试对局，
确认卡组合法、能完成对局。

---

## 四、关键 API 参考

### 官方文档

- 引擎 API 文档：https://matsuoinstitute.github.io/cabt/api.html
- 比赛页面：https://www.kaggle.com/competitions/pokemon-tcg-ai-battle

### 枚举速查

| 枚举 | 值 | 说明 |
|------|---|------|
| SelectType.MAIN | 0 | 主菜单选择 |
| SelectType.CARD | 1 | 选卡 |
| SelectType.ATTACK | 6 | 选攻击 |
| SelectType.YES_NO | 9 | 是/否决策 |
| SelectType.COUNT | 8 | 选数字 |
| SelectContext.SETUP_ACTIVE | 1 | 开局选战斗位 |
| SelectContext.MULLIGAN | 42 | 重开判断 |
| SelectContext.ATTACK | 35 | 选攻击招式 |
| SelectContext.IS_FIRST | 41 | 先手选择 |
| OptionType.ATTACK | 13 | 攻击选项 |
| OptionType.END | 14 | 结束回合 |
| OptionType.PLAY | 7 | 出手牌 |
| OptionType.ATTACH | 8 | 贴能 |
| OptionType.EVOLVE | 9 | 进化 |

完整枚举见 `rule_agent.py` 文件头部的常量定义。
