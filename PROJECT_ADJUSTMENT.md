# ⚠️ 历史文档（已废弃，仅供回溯）

> **本文档描述的是早期卡组/策略调整方案（Alakazam 进化链），
> 已被 v22.x Mega Wall Push Agent 取代。当前实现请见 [README.md](README.md)。**

# 项目调整建议：基于官方卡牌数据分析

## 一、关键发现

### 1. Alakazam 进化链（MEG 扩展包）

| 卡牌 | ID | HP | 阶段 | 能力 | 攻击 |
|------|-----|-----|------|------|------|
| Abra | 741 | 50 | Basic | - | Teleportation Attack (10 + 换位) |
| Kadabra | 742 | 80 | Stage 1 | **Psychic Draw**（进化时抽 2 卡） | Super Psy Bolt (30) |
| Alakazam | 743 | 140 | Stage 2 | **Psychic Draw**（进化时抽 3 卡） | **Powerful Hand** (2×手牌数伤害) |

**策略核心**：
- Kadabra 和 Alakazam 进化时都能抽牌，快速积累手牌
- Alakazam 的 Powerful Hand：每有 1 张手牌，放 2 个伤害指示物（即 20 点伤害）
- 如果手牌有 7 张，Powerful Hand 造成 140 点伤害（直接击杀大多数宝可梦）

### 2. Dudunsparce（TEF 扩展包）

| 卡牌 | ID | HP | 阶段 | 能力 | 攻击 |
|------|-----|-----|------|------|------|
| Dunsparce | 65 | 60 | Basic | - | Gnaw (10), Dig (30) |
| Dudunsparce | 66 | 140 | Stage 1 | **Run Away Draw**（抽 3 卡 + 洗牌回牌库） | Land Crush (90) |

**策略价值**：
- Run Away Draw：抽 3 卡后，把 Dudunsparce 和所有附加卡洗回牌库
- 这个能力非常灵活：可以抽牌找关键卡，然后撤退保留牌库资源
- 配合 Alakazam 的 Powerful Hand，快速积累手牌后打出高伤害

### 3. 抽牌支援者

| 卡牌 | ID | 效果 |
|------|-----|------|
| Amarys | 1207 | 抽 4 卡（回合结束手牌≥5 要弃牌） |
| Cheren | 1224 | 抽 3 卡 |
| Urbain | 1236 | 抽 3 卡 |

## 二、优化卡组（60 张）

### 宝可梦（20 张）
- Abra x4 (ID=741)：基础形态，开局上手
- Kadabra x3 (ID=742)：一阶进化，抽 2 卡
- Alakazam x3 (ID=743)：二阶进化，主力输出
- Dunsparce x2 (ID=65)：基础形态，进化用
- Dudunsparce x2 (ID=66)：抽牌能力
- Team Rocket's Mewtwo ex x2 (ID=431)：备用高 HP 打手（HP=280）
- Mega Zygarde ex x4 (ID=1056)：备用高 HP 打手（HP=310）

### 能量（24 张）
- Basic Psychic Energy x21 (ID=5)：Psychic 属性基础能量
- Telepath Psychic Energy x3 (ID=19)：特殊能量，贴给 Psychic 宝可梦时搜索 2 张基础 Psychic 宝可梦

### 训练家（16 张）
- Amarys x2 (ID=1207)：抽 4 卡
- Cheren x2 (ID=1224)：抽 3 卡
- Urbain x2 (ID=1236)：抽 3 卡
- Ultra Ball x2 (ID=1121)：搜索宝可梦
- Pokégear 3.0 x2 (ID=1122)：检索支援者
- Boss's Orders x2 (ID=1182)：换位对方宝可梦
- Roto-Stick x1 (ID=1077)：检索支援者
- Hole-Digging Shovel x1 (ID=1078)：弃牌
- Rare Candy x1 (ID=1079)：直接进化到 Stage 2
- Unfair Stamp x1 (ID=1080)：抽牌

## 三、Agent 策略调整

### 1. handle_main（主菜单选择）

**优先级调整**：
```python
PRIORITY = {
    OT_ATTACK: 1,   # 能攻击就攻击（Powerful Hand 伤害高）
    OT_ABILITY: 2,  # 用能力（Psychic Draw 抽牌）
    OT_EVOLVE: 3,   # 进化（快速到 Alakazam）
    OT_ATTACH: 4,   # 贴能
    OT_PLAY: 5,     # 出牌（支援者抽牌）
    OT_RETREAT: 6,  # 撤退（Dudunsparce 能力后撤退）
    OT_END: 8,      # 结束回合
}
```

**关键逻辑**：
- 如果手牌 ≥ 5 张，优先使用 Powerful Hand 攻击
- 如果 Kadabra/Alakazam 刚进化，优先使用 Psychic Draw 能力
- 如果 Dudunsparce 在场，优先使用 Run Away Draw 能力

### 2. handle_attack（选择攻击）

**Alakazam 攻击选择**：
- 如果手牌 ≥ 5 张：选择 Powerful Hand（2×手牌数伤害）
- 如果手牌 < 5 张：选择其他攻击或结束回合

**实现建议**：
```python
def handle_attack(options, max_count, obs, context):
    my = _my_state(obs)
    hand_count = len(_hand(my))
    
    # 查找 Powerful Hand 攻击
    for i, opt in enumerate(options):
        attack_id = opt.get("attackId")
        # 如果 attackId 对应 Powerful Hand，且手牌多
        if attack_id == POWERFUL_HAND_ID and hand_count >= 5:
            return [i]
    
    # 否则选伤害最高的
    return [len(options) - 1]
```

### 3. handle_yes_no（是/否决策）

**MULLIGAN 判断**：
- 如果手牌有 Abra 或 Dunsparce：NO（不重开）
- 如果手牌没有基础宝可梦：YES（重开）

**ACTIVATE 判断**：
- Psychic Draw 能力：YES（抽牌总是好的）
- Run Away Draw 能力：YES（抽 3 卡后撤退）

### 4. handle_card（选卡）

**SETUP_ACTIVE（开局选战斗位）**：
- 优先选 Abra（快速进化到 Alakazam）
- 其次选 Dunsparce（抽牌能力）

**ATTACH_FROM（贴给谁）**：
- 优先贴给 Alakazam（主力输出）
- 其次贴给 Dudunsparce（准备使用 Run Away Draw）

## 四、提交计划

### Day 1（2 次提交）
1. 提交当前 `main.py`（随机 Agent）→ 获取 baseline μ 分
2. 替换为 `rule_agent.py` + `optimized_deck.csv` → 看规则 Agent 是否提分

### Day 2（2 次提交）
3. 调整 `handle_attack`：实现 Powerful Hand 优先逻辑
4. 调整 `handle_main`：实现 Ability 优先逻辑（Psychic Draw）

### Day 3（1 次提交）
5. 调整 `handle_card`：实现开局优先铺 Abra/Dunsparce

## 五、文件清单

| 文件 | 用途 | 状态 |
|------|------|------|
| `optimized_deck.csv` | 优化卡组（60 张） | 已生成 |
| `analyze_cards.py` | 卡牌数据分析脚本 | 已创建 |
| `build_deck.py` | 卡组构建脚本 | 已创建 |
| `rule_agent.py` | 规则 Agent 骨架 | 已创建，需调整 |
| `EN_Card_Data.csv` | 官方卡牌数据（英文） | 已下载 |
| `JP_Card_Data.csv` | 官方卡牌数据（日文） | 已下载 |

## 六、下一步操作

```bash
# 1. 使用优化卡组
cp optimized_deck.csv deck.csv

# 2. 调整 rule_agent.py（实现上述策略）
# 编辑 handle_main, handle_attack, handle_yes_no, handle_card

# 3. 本地验证
bash submit.sh validate-local

# 4. 打包
bash pack.sh

# 5. 提交
bash submit.sh submit
```

## 七、PDF 卡牌图片 OCR（可选）

如果需要从 PDF 中提取卡牌图片并 OCR 识别效果：

1. 使用 `pdfplumber` 或 `PyMuPDF` 提取 PDF 页面为图片
2. 使用 `pytesseract` 或 `easyocr` 识别卡牌效果文本
3. 将识别结果与 CSV 数据对照验证

但 CSV 数据已经包含完整的效果说明（Effect Explanation 列），通常不需要 OCR。
