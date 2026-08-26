# merge ① dying_674 移植 pre-audit（2026-08-12）

> 对象：`submission_baseline/main.py`（config A = baseline policy + baseline 自家牌组，LB `459cf97`）。
> 移植源：我们 `main.py:2872` BUG-7（`hariyama_self_ko_hp=70`，674 ワイルドプレス自伤 70，HP≤70 非 KO 攻击=自杀白送奖品）。
> 形态：模块级 `FLAG_DYING_674`（默认 ON）+ 三处 `if FLAG and …` 纯前置短路；deck.csv 不动。

## parity 方法（已按顾问修正，action-diff 版本作废）

ledger #111 已证引擎不可播种、一切测量是无配对二项抽样 σ≈2.2pp——**逐 action 重放/比对不可达，不造该框架**。改为两条腿：

1. **结构审查**：三处 guard 全是 `if FLAG_DYING_674 and …` 前置短路；FLAG off 时每处控制流逐点等价于未编辑文件，肉眼可证（见 §2 伪码，off 时新增的 `if` 条件为 False 即落到原语句）。
2. **同批分数等价**：FLAG-OFF vs pristine config A 同批 9 腿 n=2000，期望每腿与加权 |Δ| < 2.2pp（噪声内），**不是精确相等**。

## 三处插入点伪码

**① target 层 skip（KO 豁免）** — `_plan_attack` 目标循环内，`damage` 经弱点/抗性调整后、打分前：

```python
# attacker 循环顶部 (无条件计数, 闸的 function 腿用):
if my_pokemon.id == C.HARIYAMA and my_pokemon.hp <= DYING_674_HP:
    _DYING674['situations'] += 1
# target 循环内, damage 调整后:
if FLAG_DYING_674 and my_pokemon.id == C.HARIYAMA and my_pokemon.hp <= DYING_674_HP:
    if damage < op_pokemon.hp:      # 非 KO = 自杀, 从打分空间剔除
        _DYING674['blocked'] += 1
        continue                    # KO 则交易照打 (KO 豁免)
```

**② ATTACK 门** — `_score_option` 的 ATTACK 分支，紧随现有 crustle 墙门（:395-403）之后（belt，① 已覆盖规划层，此处兜"计划外/陈旧计划"）：

```python
if (FLAG_DYING_674 and plan.attacker == 0 and plan.remain_hp > 0
        and self.me.active and self.me.active[0] is not None
        and self.me.active[0].id == C.HARIYAMA
        and self.me.active[0].hp <= DYING_674_HP):
    return -1                       # 现役 dying 674 的非 KO 攻击不打出
```

**③ RETREAT 偏置** — `_score_option` 的 RETREAT 分支（:394），别把 bench 上的 dying 674 换进场送死：

```python
if option.type == OptionType.RETREAT:
    if plan.attacker >= 1 and FLAG_DYING_674:
        _pm = self._my_board()[plan.attacker]  # 计划要换上来的 bench 打手
        if (_pm is not None and _pm.id == C.HARIYAMA
                and _pm.hp <= DYING_674_HP and plan.remain_hp > 0):
            return -1               # 非 KO 目的不换 dying 674 进场
    return 2000 if plan.attacker >= 1 else -1
```

**计数器（闸用，不影响决策）**：`_plan_attack` 收尾处，若最终 plan 是 dying 674 的非 KO 攻击（`plan.remain_hp > 0`），`_DYING674['attacks'] += 1`。FLAG-ON 应恒 0，FLAG-OFF 应 >0。

## 闸协议（`experiments/merge_gate_dying674.py`）

- 三配置同批：pristine（`runs/_configA/main_configA_pristine.py`）/ FLAG-OFF / FLAG-ON，9 腿 × n=2000，引擎不可播种故同一 batch 内交错测量。
- **parity 腿**：|OFF − pristine| 每腿与加权 < 2.2pp。
- **功能腿**：Crustle/Alakazam 上 ON ≥ pristine（噪声内不退即合格），且计数器 ON: blocked>0 且 attacks=0；OFF: attacks>0。
- **回归腿**：其余 7 腿 ON vs pristine 无 < −2.2pp。
- **提交判据**：ON 加权 > pristine 加权 **+2.2pp**（锚=config A 非 F1）且上三腿全过 → 交，顶出 F1。**现实预期：正确性卫生修复，加权 ≲1-2pp < 2.2pp，大概率不过闸 → 不交，属正常结局**（config A settle 到 8/17 本身就是 2.3× 锁定的胜利）。
