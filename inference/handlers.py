# -*- coding: utf-8 -*-
"""
handlers.py — 11 个 SelectType 专用 Handler

每个 handler 接收 (state, options, max_count, context)，返回选中的 index 列表。
简单场景直接返回，复杂场景委托 DecisionGate。
"""

from typing import List

from state_parser import GameState, get_my_active, get_opp_active
from option_scorer import Option, SelectType, SelectContext, OptionType, get_options_by_type, find_first_option_by_type
from decision_gate import DecisionGate

# 全局 DecisionGate 实例（单例）
_gate = DecisionGate()


# ------------------------------------------------------------------
# Handler 路由
# ------------------------------------------------------------------

def handle_main(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """MAIN(0)：主菜单 — 委托 DecisionGate"""
    return _gate.decide(state, options, max_count, SelectType.MAIN, context)


def handle_card(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """CARD(1)：选卡 — 按场景特化"""
    if context == SelectContext.SETUP_ACTIVE:
        return _pick_highest_hp(options, max_count)
    elif context == SelectContext.SETUP_BENCH:
        return _pick_evolution_basics(options, max_count)
    elif context in (SelectContext.SWITCH, SelectContext.TO_ACTIVE, SelectContext.TO_BENCH):
        return _pick_highest_hp(options, max_count)
    else:
        return _gate.decide(state, options, max_count, SelectType.CARD, context)


def handle_attack(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """ATTACK(6)：选攻击 — 委托 DecisionGate（内含伤害估算）"""
    return _gate.decide(state, options, max_count, SelectType.ATTACK, context)


def handle_yes_no(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """YES_NO(9)：是/否判断"""
    yes_opt = find_first_option_by_type(options, OptionType.YES)
    no_opt = find_first_option_by_type(options, OptionType.NO)

    if context == SelectContext.IS_FIRST:
        # 先手：YES
        return [yes_opt.index] if yes_opt else [0]

    elif context == SelectContext.MULLIGAN:
        # MULLIGAN：检查手牌是否有基础宝可梦
        has_basic = any(
            c.card_type == "pokemon" and c.stage == "basic"
            for c in state.you.hand
        )
        if has_basic:
            return [no_opt.index] if no_opt else [1]
        else:
            return [yes_opt.index] if yes_opt else [0]

    # 默认 YES
    return [yes_opt.index] if yes_opt else [0]


def handle_energy(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """ENERGY(4)：选能量 — 委托 DecisionGate"""
    return _gate.decide(state, options, max_count, SelectType.ENERGY, context)


def handle_evolve(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """EVOLVE(7)：选进化 — 委托 DecisionGate"""
    return _gate.decide(state, options, max_count, SelectType.EVOLVE, context)


def handle_attached_card(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """ATTACHED_CARD(2)：选贴卡"""
    return [opt.index for opt in options[:max_count]]


def handle_card_or_attached(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """CARD_OR_ATTACHED_CARD(3)：选卡或贴卡"""
    return [opt.index for opt in options[:max_count]]


def handle_skill(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """SKILL(5)：选技能"""
    return [opt.index for opt in options[:max_count]]


def handle_count(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """COUNT(8)：选数字 — 默认选最大值"""
    return [len(options) - 1] if options else []


def handle_special_condition(state: GameState, options: List[Option], max_count: int, context: SelectContext) -> List[int]:
    """SPECIAL_CONDITION(10)：选异常状态"""
    return [opt.index for opt in options[:max_count]]


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _pick_highest_hp(options: List[Option], max_count: int) -> List[int]:
    """选 HP 最高的选项（用于 SETUP_ACTIVE / SWITCH）"""
    # option 的 card_id 可能来自 raw_data 中的 cardId / index 等字段
    scored = []
    for opt in options:
        # 尝试从 raw_data 提取 card_id
        card_id = opt.raw_data.get("cardId") or opt.raw_data.get("index", -1)
        hp = 0
        if isinstance(card_id, int) and card_id >= 0:
            from card_meta import get_card
            card = get_card(card_id)
            if card and card.hp:
                hp = card.hp
        scored.append((hp, opt.index))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [idx for _, idx in scored[:max_count]]


def _pick_evolution_basics(options: List[Option], max_count: int) -> List[int]:
    """选有进化链的基础宝可梦（用于 SETUP_BENCH）"""
    from card_meta import get_card, get_evolution_chain

    scored = []
    for opt in options:
        card_id = opt.raw_data.get("cardId") or opt.raw_data.get("index", -1)
        score = 0
        if isinstance(card_id, int) and card_id >= 0:
            card = get_card(card_id)
            if card and card.stage == "basic":
                chain = get_evolution_chain(card_id)
                score = len(chain) * 10  # 进化链越长越优先
                if card.hp:
                    score += card.hp
        scored.append((score, opt.index))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [idx for _, idx in scored[:max_count]]
