# -*- coding: utf-8 -*-
"""
⚠️ [孤儿管线 ORPHANED — 2026-08-09 hy3 审计 B4-1] ⚠️
依赖的 state_parser / option_scorer 模块在全仓库及 git 历史中不存在,
import 本文件必 ModuleNotFoundError。现役 NN 提交线走 build_pure.py, 勿用。

main_entry.py — Kaggle Agent 入口

提交格式：与 deck.csv 一起打包为 submission.tar.gz
"""

import os
import random
from typing import List

from state_parser import parse_observation, parse_select
from option_scorer import SelectType
from handlers import (
    handle_main, handle_card, handle_attack, handle_yes_no,
    handle_energy, handle_evolve, handle_attached_card,
    handle_card_or_attached, handle_skill, handle_count,
    handle_special_condition,
)


# ------------------------------------------------------------------
# 加载牌组
# ------------------------------------------------------------------
_DECK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deck.csv")


def _load_deck(path: str = _DECK_PATH) -> List[int]:
    deck = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                deck.append(int(line))
    if len(deck) != 60:
        raise ValueError(f"deck.csv must have 60 cards, got {len(deck)}")
    return deck


DECK = _load_deck()


# ------------------------------------------------------------------
# Handler 路由表
# ------------------------------------------------------------------
HANDLERS = {
    SelectType.MAIN:                    handle_main,
    SelectType.CARD:                    handle_card,
    SelectType.ATTACHED_CARD:           handle_attached_card,
    SelectType.CARD_OR_ATTACHED_CARD:   handle_card_or_attached,
    SelectType.ENERGY:                  handle_energy,
    SelectType.SKILL:                   handle_skill,
    SelectType.ATTACK:                  handle_attack,
    SelectType.EVOLVE:                  handle_evolve,
    SelectType.COUNT:                   handle_count,
    SelectType.YES_NO:                  handle_yes_no,
    SelectType.SPECIAL_CONDITION:       handle_special_condition,
}


# ------------------------------------------------------------------
# Agent 入口
# ------------------------------------------------------------------
def agent(obs, config=None):
    """
    Kaggle Agent 入口函数。

    参数：
        obs   : dict — Kaggle cabt 引擎传入的 observation
        config: any  — Kaggle Environments 配置（未使用）

    返回：
        list[int] — 选中的 option index 列表
    """
    # ---- Phase 0: 初始上牌阶段 ----
    if obs.get("select") is None:
        return DECK

    # ---- Phase 1-4: 解析 → 决策 → 返回 ----
    try:
        game_state = parse_observation(obs)
        select_type, context, options, max_count = parse_select(obs["select"])
        handler = HANDLERS.get(select_type)
        if handler:
            result = handler(game_state, options, max_count, context)
            return result
        select = obs["select"]
        options_raw = select.get("option", [])
        return list(range(min(max_count, len(options_raw))))
    except Exception:
        select = obs["select"]
        options = select["option"]
        max_count = select["maxCount"]
        indices = list(range(len(options)))
        return random.sample(indices, min(max_count, len(options)))
