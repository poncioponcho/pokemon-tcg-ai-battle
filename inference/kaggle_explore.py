# -*- coding: utf-8 -*-
"""
decision_gate.py — MRI 五级决策门控 + 选项评分器

设计来源：MRI notebook 的决策优先级策略
"""

import random
from typing import List, Optional
from dataclasses import dataclass

from state_parser import GameState, PokemonInPlay, get_my_active, get_opp_active, get_my_prizes
from option_scorer import Option, OptionType, SelectType, SelectContext, get_options_by_type, find_first_option_by_type
from card_meta import get_card


class DecisionGate:
    """
    MRI 五级决策门控

    优先级（从高到低）：
    1. FORCED      — 唯一合法选项，直接执行
    2. IMMEDIATE_WIN — 本回合攻击可 KO 对手并拿完 prize
    3. LOSS_SHIELD — 防止下回合被 KO（撤退/切换）
    4. VALUE_MAX   — 最大化场面价值评分
    5. FALLBACK    — 确定性回退（优先非 END）
    """

    # 动作类型基础优先级（数值越大越优先）
    ACTION_PRIORITY = {
        OptionType.ATTACK:  100,
        OptionType.ABILITY:  85,
        OptionType.EVOLVE:   75,
        OptionType.ATTACH:   65,
        OptionType.PLAY:       55,
        OptionType.RETREAT:  40,
        OptionType.DISCARD:    25,
        OptionType.END:         5,
    }

    def decide(self, state: GameState, options: List[Option], max_count: int,
               select_type: SelectType, context: SelectContext) -> List[int]:
        """主决策入口"""
        # Level 1: FORCED
        if len(options) <= max_count:
            return [opt.index for opt in options]

        # Level 2: IMMEDIATE_WIN
        win = self._check_immediate_win(state, options)
        if win is not None:
            return win

        # Level 3: LOSS_SHIELD
        shield = self._check_loss_shield(state, options)
        if shield is not None:
            return shield

        # Level 4: VALUE_MAX
        value = self._value_maximize(state, options, max_count)
        if value is not None:
            return value

        # Level 5: FALLBACK
        return self._fallback(options, max_count)

    # ------------------------------------------------------------------
    # Level 2: IMMEDIATE_WIN
    # ------------------------------------------------------------------
    def _check_immediate_win(self, state: GameState, options: List[Option]) -> Optional[List[int]]:
        """检查是否有攻击能直接获胜（KO 对手 active 且对手无 bench）"""
        my_active = get_my_active(state)
        opp_active = get_opp_active(state)
        if not my_active or not opp_active:
            return None

        opp_hp = opp_active.current_hp
        my_prizes = get_my_prizes(state)
        attack_opts = get_options_by_type(options, OptionType.ATTACK)
        if not attack_opts:
            return None

        for opt in attack_opts:
            damage = self._estimate_damage(my_active, opt)
            if damage >= opp_hp:
                opp_card = get_card(opp_active.card_meta.card_id)
                prizes = opp_card.prizes if opp_card else 1
                # 拿 prize 后剩余 <= 0 且对手无 bench → 直接赢
                if my_prizes - prizes <= 0 and len(state.opponent.bench) == 0:
                    return [opt.index]
        return None

    # ------------------------------------------------------------------
    # Level 3: LOSS_SHIELD
    # ------------------------------------------------------------------
    def _check_loss_shield(self, state: GameState, options: List[Option]) -> Optional[List[int]]:
        """防止下回合被 KO：HP 危急时撤退"""
        my_active = get_my_active(state)
        if not my_active:
            return None

        my_hp = my_active.current_hp
        threshold = 50 if my_active.status in ("poison", "burn") else 30

        if my_hp <= threshold and len(state.you.bench) > 0:
            retreat = find_first_option_by_type(options, OptionType.RETREAT)
            if retreat:
                return [retreat.index]
        return None

    # ------------------------------------------------------------------
    # Level 4: VALUE_MAX
    # ------------------------------------------------------------------
    def _value_maximize(self, state: GameState, options: List[Option], max_count: int) -> Optional[List[int]]:
        """价值最大化：给每个 option 打分，选最高分"""
        scored = []
        for opt in options:
            score = self._score_option(state, opt)
            scored.append((score, opt.index))

        scored.sort(reverse=True, key=lambda x: x[0])
        return [idx for _, idx in scored[:max_count]]

    def _score_option(self, state: GameState, opt: Option) -> float:
        """给单个 option 打分"""
        ot = opt.option_type
        base = self.ACTION_PRIORITY.get(ot, 0.0)

        if ot == OptionType.ATTACK:
            my_active = get_my_active(state)
            opp_active = get_opp_active(state)
            if my_active and opp_active:
                damage = self._estimate_damage(my_active, opt)
                if damage >= opp_active.current_hp:
                    base += 200          # KO 奖励
                else:
                    base += damage * 0.3  # 伤害加成

        elif ot == OptionType.ATTACH:
            my_active = get_my_active(state)
            if my_active and len(my_active.attached_energy) < 3:
                base += 15  # 能量不足时优先贴能

        elif ot == OptionType.EVOLVE:
            my_active = get_my_active(state)
            if my_active and my_active.is_active:
                base += 10  # active 位优先进化

        elif ot == OptionType.END:
            # 如果场面劣势，降低结束回合优先级
            my_hp = get_my_active(state).current_hp if get_my_active(state) else 0
            opp_hp = get_opp_active(state).current_hp if get_opp_active(state) else 0
            if my_hp < opp_hp:
                base -= 20

        return base

    # ------------------------------------------------------------------
    # 辅助：伤害估算
    # ------------------------------------------------------------------
    def _estimate_damage(self, attacker: PokemonInPlay, opt: Option) -> int:
        """估算攻击伤害（从 CARD_DB 读取）"""
        if not attacker:
            return 0
        card = get_card(attacker.card_meta.card_id)
        if not card or not card.moves:
            return 0

        attack_id = opt.attack_id
        if attack_id is not None and 0 <= attack_id < len(card.moves):
            return card.moves[attack_id].damage_base

        # fallback：取最高伤害招式
        return max((m.damage_base for m in card.moves), default=0)

    # ------------------------------------------------------------------
    # Level 5: FALLBACK
    # ------------------------------------------------------------------
    def _fallback(self, options: List[Option], max_count: int) -> List[int]:
        """确定性回退：优先非 END 选项"""
        non_end = [opt.index for opt in options if opt.option_type != OptionType.END]
        if non_end:
            return non_end[:max_count]
        return [options[0].index] if options else []
