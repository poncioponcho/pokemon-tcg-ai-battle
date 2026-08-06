#!/usr/bin/env python3
"""
PTCG伤害解析模块
处理CSV中特殊伤害格式：负数(伤害减少)、×(多段)、+(追加伤害)、-(自伤)
"""
import re


def parse_damage(damage_str, effect_text=""):
    """
    解析PTCG CSV中的伤害值，返回结构化信息。

    Args:
        damage_str: CSVダメージ列的值（str）
        effect_text: CSV効果の説明列的值（str），用于辅助解析

    Returns:
        dict: {
            "type": "direct"|"multi"|"reduction"|"self_damage"|"none",
            "base": int,          # 基础伤害值（绝对值）
            "modifier": str,      # 修饰符: "", "×", "+", "-"
            "description": str    # 人类可读描述
        }

    PTCG伤害格式说明:
        - 纯数字(如 "60"): 固定伤害
        - 数字+(如 "10+"): 基础伤害+追加条件伤害
        - 数字×(如 "90×"): 掷硬币，正面数×基础伤害
        - 数字-(如 "240-"): 基础伤害-条件减少量
        - 负数(如 "-120"): 伤害减少类招式（无基础伤害，按条件减少对手伤害）
        - "n/a"或空: 无伤害（效果类招式）
    """
    if not damage_str or damage_str.strip().lower() in ('n/a', 'na', ''):
        return {"type": "none", "base": 0, "modifier": "", "description": "无伤害（效果招式）"}

    damage_str = damage_str.strip()

    # 负数伤害 = 伤害减少类招式
    if damage_str.startswith('-'):
        abs_val = abs(int(damage_str))
        reduction_rate = _extract_reduction_rate(effect_text)
        return {
            "type": "reduction",
            "base": abs_val,
            "modifier": "-",
            "reduction_rate": reduction_rate,
            "description": f"伤害减少类：基础{abs_val}，每条件单位减少{reduction_rate}点"
        }

    # 提取数字和修饰符
    match = re.match(r'^(\d+)([×+\-]?)$', damage_str)
    if not match:
        # 无法解析，返回原始值
        return {"type": "unknown", "base": 0, "modifier": "", "description": f"无法解析: {damage_str}"}

    base = int(match.group(1))
    modifier = match.group(2)

    if modifier == '×':
        return {
            "type": "multi",
            "base": base,
            "modifier": "×",
            "description": f"多段伤害：掷硬币，正面数×{base}"
        }
    elif modifier == '+':
        return {
            "type": "bonus",
            "base": base,
            "modifier": "+",
            "description": f"基础{base}+追加条件伤害"
        }
    elif modifier == '-':
        return {
            "type": "self_damage",
            "base": base,
            "modifier": "-",
            "description": f"基础{base}-条件减少（可能含自伤）"
        }
    else:
        return {
            "type": "direct",
            "base": base,
            "modifier": "",
            "description": f"固定伤害 {base}"
        }


def _extract_reduction_rate(effect_text):
    """
    从效果文本中提取伤害减少类招式的每单位减少量。

    匹配模式:
        - "数×30ダメージ" → 30
        - "数×60ダメージ" → 60
        - 默认回退 30
    """
    if not effect_text:
        return 30

    # 匹配 "数×NNダメージ" 模式
    match = re.search(r'数×(\d+)ダメージ', effect_text)
    if match:
        return int(match.group(1))

    # 匹配 "の数×NNダメージ" 模式
    match = re.search(r'の数×(\d+)ダメージ', effect_text)
    if match:
        return int(match.group(1))

    # 默认回退
    return 30


def calculate_actual_damage(parsed, context=None):
    """
    根据解析结果和战斗上下文计算实际伤害。

    Args:
        parsed: parse_damage()的返回结果
        context: dict, 可选战斗上下文:
            - "coin_flips": int, 正面硬币数（多段伤害用）
            - "opponent_energy": int, 对手战斗宝可梦能量数（伤害减少用）
            - "has_bonus_condition": bool, 是否满足追加条件（bonus伤害用）

    Returns:
        int: 实际伤害值（>=0）
    """
    if context is None:
        context = {}

    if parsed["type"] == "none":
        return 0

    if parsed["type"] == "direct":
        return parsed["base"]

    if parsed["type"] == "multi":
        flips = context.get("coin_flips", 0)
        return parsed["base"] * flips

    if parsed["type"] == "bonus":
        base = parsed["base"]
        if context.get("has_bonus_condition", False):
            # 追加伤害需要从效果文本解析，这里返回基础值
            # 实际追加量由Agent根据效果文本判断
            return base  # Agent需额外解析追加量
        return base

    if parsed["type"] == "self_damage":
        base = parsed["base"]
        # 自伤类：基础伤害减去条件减少
        # 具体减少量需从效果文本解析
        return base  # Agent需额外处理自伤逻辑

    if parsed["type"] == "reduction":
        # 伤害减少类：这不是攻击伤害，而是减少对手攻击的效果
        # 返回0表示此招式不造成伤害
        opponent_energy = context.get("opponent_energy", 0)
        reduction = parsed.get("reduction_rate", 30) * opponent_energy
        return max(0, parsed["base"] - reduction)

    return 0


# ========== 批量验证 ==========
if __name__ == "__main__":
    import csv

    CSV_PATH = "/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/pokemon-tcg-ai-battle-challenge-strategy/JP_Card_Data_Cleaned.csv"
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 统计伤害类型分布
    type_dist = {}
    special_cases = []

    for row in rows:
        dmg = row.get('ダメージ', '').strip()
        effect = row.get('効果の説明', '').strip()
        name = row.get('カード名', '').strip()
        waza = row.get('ワザ名', '').strip()

        if not dmg or dmg.lower() == 'n/a':
            continue

        parsed = parse_damage(dmg, effect)
        t = parsed["type"]
        type_dist[t] = type_dist.get(t, 0) + 1

        # 记录特殊案例
        if t in ('reduction', 'self_damage'):
            special_cases.append({
                "id": row.get('カード ID', '').strip(),
                "name": name,
                "move": waza,
                "damage": dmg,
                "parsed": parsed
            })

    print("=== 伤害类型分布 ===")
    for t, cnt in sorted(type_dist.items(), key=lambda x: -x[1]):
        print(f"  {t}: {cnt}个招式")

    print(f"\n=== 特殊案例 ({len(special_cases)}个) ===")
    for case in special_cases:
        print(f"  ID={case['id']} {case['name']} - {case['move']}: {case['damage']}")
        print(f"    → {case['parsed']['description']}")
