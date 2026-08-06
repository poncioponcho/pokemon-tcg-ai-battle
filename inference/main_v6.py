# -*- coding: utf-8 -*-
"""
PTCG Battle Agent v6 — 状态感知规则 Agent

设计原则：
1. 单文件自包含，DECK 内联，纯标准库
2. 动作铁律：长度==maxCount、下标合法、无重复
3. 状态感知：读 obs["current"] 双方 HP/能量
4. 硬编码 deck 卡数据（9 种卡，从 JP CSV 提取）
5. 动态决策：能 KO 就攻击，否则发育

修复历史：
- v3: 随机 Agent，COMPLETE 443.5
- v4: merge 复杂架构，ERROR（非法动作）
- v5: 静态优先级，COMPLETE 376.6（永远先攻击是陷阱）
- v6: 状态感知动态决策 + deck 重构
"""

import os
import random

# ------------------------------------------------------------------
# 0. 内联牌组（60 张，全部 Kaggle 已验证合法 ID）
# ------------------------------------------------------------------
# 331 ゼルネアスex ×4 : 超系主力 HP210, ライジングホーン 120
# 554 タブンネ       ×4 : 無系副攻 HP100, おんがえし 30+抽牌
# 157 カムカメ       ×4 : 無系副攻 HP80,  ずつき 60
# 532 イシズマイ     ×4 : 無系肉盾 HP70
# 9  ブーメラン能量   ×2 : 無色特殊能量
# 5  超能量          ×42: 喂 331
DECK = (
    [331] * 4 + [554] * 4 + [157] * 4 + [532] * 4 +
    [9] * 2 + [5] * 42
)

# ------------------------------------------------------------------
# 1. 硬编码卡数据（Kaggle 上读不到 CSV，内嵌关键信息）
# ------------------------------------------------------------------
# 格式: {card_id: {"hp": int, "moves": [(damage, name), ...]}}
# 注意：引擎的 attackId 是【全局招式 ID】，不是卡内索引！
#       实测（replay 反查）：554→791(おんがえし30), 532→760(じたばた10)/761(ツメをたてる20)
#       全局 ID 无法从卡 ID 直接推导，这里记录已知映射，未知时退回卡招式表
_CARD_DB = {
    77:  {"hp": 70,  "moves": [(10,  "ねこだまし")]},
    157: {"hp": 80,  "moves": [(60,  "ずつき")]},
    331: {"hp": 210, "moves": [(50,  "オーロラビーム"), (120, "ライジングホーン")]},
    408: {"hp": 70,  "moves": [(20,  "ひをはく")]},
    528: {"hp": 70,  "moves": [(10,  "けたぐり"), (50, "かいりき")]},
    532: {"hp": 70,  "moves": [(10,  "じたばた"), (20, "ツメをたてる")]},
    554: {"hp": 100, "moves": [(30,  "おんがえし")]},
}

# 已实测的全局 attackId → 招式伤害（replay 反查）
# 330 是超系主力ゼルネアスex，其ライジングホーン(120) 是 deck 最高输出
_ATTACK_ID_DMG = {
    791: 30,   # タブンネ おんがえし
    760: 10,   # イシズマイ じたばた
    761: 20,   # イシズマイ ツメをたてる
}

# 能量类型枚举（与引擎一致）
_ET_COL = 0   # Colorless
_ET_PSY = 5   # Psychic

# OptionType 枚举
_OT_NUMBER = 0
_OT_YES = 1
_OT_NO = 2
_OT_CARD = 3
_OT_TOOL_CARD = 4
_OT_ENERGY_CARD = 5
_OT_ENERGY = 6
_OT_PLAY = 7
_OT_ATTACH = 8
_OT_EVOLVE = 9
_OT_ABILITY = 10
_OT_DISCARD = 11
_OT_RETREAT = 12
_OT_ATTACK = 13
_OT_END = 14
_OT_SKILL = 15
_OT_SPECIAL_CONDITION = 16

# SelectType 枚举
_ST_MAIN = 0
_ST_CARD = 1
_ST_ATTACHED_CARD = 2
_ST_CARD_OR_ATTACHED_CARD = 3
_ST_ENERGY = 4
_ST_SKILL = 5
_ST_ATTACK = 6
_ST_EVOLVE = 7
_ST_COUNT = 8
_ST_YES_NO = 9
_ST_SPECIAL_CONDITION = 10

# SelectContext 枚举（常用）
_SC_SETUP_ACTIVE = 1
_SC_SETUP_BENCH = 2
_SC_SWITCH = 3
_SC_TO_ACTIVE = 4
_SC_TO_BENCH = 5
_SC_ATTACH_FROM = 21
_SC_ATTACH_TO = 22
_SC_ATTACK = 35
_SC_DRAW_COUNT = 38
_SC_IS_FIRST = 41
_SC_MULLIGAN = 42


# ------------------------------------------------------------------
# 2. 辅助函数
# ------------------------------------------------------------------

def _get_option_type(opt):
    """安全读取 option 的 type 字段"""
    return opt.get("type", -1) if isinstance(opt, dict) else -1


def _get_card_id_from_option(opt):
    """从 option 提取 card_id（多种字段名兼容）"""
    if not isinstance(opt, dict):
        return -1
    for key in ("cardId", "card_id", "id", "index"):
        val = opt.get(key)
        if isinstance(val, int) and val >= 0:
            return val
    return -1


def _get_pokemon_hp(pokemon):
    """从 pokemon dict 安全读取 HP"""
    if not isinstance(pokemon, dict):
        return 0
    return pokemon.get("hp") or pokemon.get("remainingHp") or 0


def _get_pokemon_energy_count(pokemon):
    """从 pokemon dict 安全读取能量数量"""
    if not isinstance(pokemon, dict):
        return 0
    energies = pokemon.get("energies")
    if isinstance(energies, list):
        return len(energies)
    if isinstance(energies, dict):
        return sum(energies.values())
    return 0


def _get_pokemon_card_id(pokemon):
    """从 pokemon dict 安全读取 card_id"""
    if not isinstance(pokemon, dict):
        return -1
    for key in ("cardId", "card_id", "id"):
        val = pokemon.get(key)
        if isinstance(val, int) and val >= 0:
            return val
    # fallback: 用 name 匹配硬编码表
    name = pokemon.get("name", "")
    if name:
        for cid, data in _CARD_DB.items():
            if data.get("name") == name:
                return cid
    return -1


def _estimate_attack_damage(card_id, attack_id):
    """估算攻击伤害。

    优先用已实测的全局 attackId → 伤害映射（_ATTACK_ID_DMG）。
    查不到时退回卡招式表：attackId 作为卡内索引（0 起）尝试，
    仍失败则取该卡最大伤害（保守）。
    """
    if attack_id is not None and attack_id in _ATTACK_ID_DMG:
        return _ATTACK_ID_DMG[attack_id]
    data = _CARD_DB.get(card_id)
    if not data:
        return 0
    moves = data.get("moves", [])
    if attack_id is not None and isinstance(attack_id, int) and 0 <= attack_id < len(moves):
        return moves[attack_id][0]
    return max((m[0] for m in moves), default=0)


def _get_my_active(obs_current, my_idx):
    """获取我方 active 宝可梦"""
    try:
        players = obs_current.get("players", [])
        if not players or my_idx >= len(players):
            return None
        active_list = players[my_idx].get("active", [])
        if active_list:
            return active_list[0]
    except Exception:
        pass
    return None


def _get_opp_active(obs_current, my_idx):
    """获取对方 active 宝可梦"""
    try:
        players = obs_current.get("players", [])
        opp_idx = 1 - my_idx
        if opp_idx >= len(players):
            return None
        active_list = players[opp_idx].get("active", [])
        if active_list:
            return active_list[0]
    except Exception:
        pass
    return None


def _get_my_bench(obs_current, my_idx):
    """获取我方 bench"""
    try:
        players = obs_current.get("players", [])
        if not players or my_idx >= len(players):
            return []
        return players[my_idx].get("bench", [])
    except Exception:
        return []


def _get_my_hand(obs_current, my_idx):
    """获取我方手牌"""
    try:
        players = obs_current.get("players", [])
        if not players or my_idx >= len(players):
            return []
        return players[my_idx].get("hand", [])
    except Exception:
        return []


def _has_basic_in_hand(hand):
    """检查手牌是否有基础宝可梦"""
    for card in hand:
        if not isinstance(card, dict):
            continue
        stage = card.get("stage")
        if stage == 0 or stage == "basic" or stage == "Basic":
            return True
        # fallback: 从硬编码表查
        cid = _get_card_id_from_option(card)
        if cid in _CARD_DB:
            return True
    return False


def _sanitize(indices, options_len, max_count):
    """动作合法性铁律：长度==maxCount、下标合法、无重复"""
    if not indices:
        indices = list(range(min(max_count, options_len)))
    # 去重且保序
    seen = set()
    clean = []
    for idx in indices:
        if isinstance(idx, int) and 0 <= idx < options_len and idx not in seen:
            clean.append(idx)
            seen.add(idx)
    # 长度不足时补第一个合法下标
    while len(clean) < max_count and options_len > 0:
        for i in range(options_len):
            if i not in seen:
                clean.append(i)
                seen.add(i)
                break
        else:
            break
    # 长度超长时截断
    return clean[:max_count]


# ------------------------------------------------------------------
# 3. 各场景 Handler
# ------------------------------------------------------------------

def _handle_main(options, max_count, context, obs_current, my_idx):
    """MAIN(0)：主菜单 — 状态感知动态决策"""
    n = len(options)
    if n == 0:
        return []

    my_active = _get_my_active(obs_current, my_idx)
    opp_active = _get_opp_active(obs_current, my_idx)
    my_hp = _get_pokemon_hp(my_active)
    opp_hp = _get_pokemon_hp(opp_active)
    my_cid = _get_pokemon_card_id(my_active) if my_active else -1
    my_energy = _get_pokemon_energy_count(my_active)
    bench = _get_my_bench(obs_current, my_idx)

    # 收集各类型 option 下标
    attack_idx = []
    ability_idx = []
    evolve_idx = []
    attach_idx = []
    play_idx = []
    retreat_idx = []
    discard_idx = []
    end_idx = []

    for i, opt in enumerate(options):
        ot = _get_option_type(opt)
        if ot == _OT_ATTACK:
            attack_idx.append(i)
        elif ot == _OT_ABILITY:
            ability_idx.append(i)
        elif ot == _OT_EVOLVE:
            evolve_idx.append(i)
        elif ot == _OT_ATTACH:
            attach_idx.append(i)
        elif ot == _OT_PLAY:
            play_idx.append(i)
        elif ot == _OT_RETREAT:
            retreat_idx.append(i)
        elif ot == _OT_DISCARD:
            discard_idx.append(i)
        elif ot == _OT_END:
            end_idx.append(i)

    # 决策逻辑
    chosen = []

    # 1. 能 KO 对手 → 必攻击
    if attack_idx and opp_hp > 0:
        for idx in attack_idx:
            attack_id = options[idx].get("attackId") if isinstance(options[idx], dict) else None
            dmg = _estimate_attack_damage(my_cid, attack_id)
            if dmg >= opp_hp:
                chosen.append(idx)
                break

    # 2. HP 危急且有 bench → 撤退
    if not chosen and my_hp <= 30 and bench and retreat_idx:
        chosen.append(retreat_idx[0])

    # 3. 有攻击选项且 my_active 有能量 → 攻击（选伤害最高的）
    #    无能量时攻击浪费回合 → 走发育（贴能/进化/出牌）
    if not chosen and attack_idx and my_energy > 0:
        best_idx = attack_idx[0]
        best_dmg = -1
        for idx in attack_idx:
            attack_id = options[idx].get("attackId") if isinstance(options[idx], dict) else None
            dmg = _estimate_attack_damage(my_cid, attack_id)
            if dmg > best_dmg:
                best_dmg = dmg
                best_idx = idx
        if best_dmg > 0:
            chosen.append(best_idx)

    # 4. 发育：ATTACH > EVOLVE > PLAY > ABILITY
    if not chosen:
        for idx_list in (attach_idx, evolve_idx, play_idx, ability_idx):
            if idx_list:
                chosen.append(idx_list[0])
                break

    # 5. 有 RETREAT 且无更好动作 → 撤退（比 END 积极）
    #    （修复：replay 显示 active HP 健康但只有 [RETREAT, END] 时，
    #      v6 误选 END 浪费回合；撤退可换宝可梦继续发育）
    if not chosen and retreat_idx:
        chosen.append(retreat_idx[0])

    # 6. 最后：DISCARD > END
    if not chosen:
        for idx_list in (discard_idx, end_idx):
            if idx_list:
                chosen.append(idx_list[0])
                break

    # 7. 兜底：第一个
    if not chosen and n > 0:
        chosen.append(0)

    return _sanitize(chosen, n, max_count)


def _handle_card(options, max_count, context, obs_current, my_idx):
    """CARD(1)：选卡 — 按场景特化"""
    n = len(options)
    if n == 0:
        return []

    # SETUP_ACTIVE: 选 HP 最高的基础宝可梦放 active
    if context == _SC_SETUP_ACTIVE:
        scored = []
        for i, opt in enumerate(options):
            cid = _get_card_id_from_option(opt)
            hp = _CARD_DB.get(cid, {}).get("hp", 0) if cid >= 0 else 0
            scored.append((hp, i))
        scored.sort(reverse=True)
        return _sanitize([idx for _, idx in scored[:max_count]], n, max_count)

    # SETUP_BENCH / SWITCH / TO_ACTIVE / TO_BENCH: 选 HP 高的
    if context in (_SC_SETUP_BENCH, _SC_SWITCH, _SC_TO_ACTIVE, _SC_TO_BENCH):
        scored = []
        for i, opt in enumerate(options):
            cid = _get_card_id_from_option(opt)
            hp = _CARD_DB.get(cid, {}).get("hp", 0) if cid >= 0 else 0
            scored.append((hp, i))
        scored.sort(reverse=True)
        return _sanitize([idx for _, idx in scored[:max_count]], n, max_count)

    # 默认：前 max_count 个
    return _sanitize(list(range(max_count)), n, max_count)


def _handle_attack(options, max_count, context, obs_current, my_idx):
    """ATTACK(6)：选攻击 — 选伤害最高的"""
    n = len(options)
    if n == 0:
        return []

    my_active = _get_my_active(obs_current, my_idx)
    my_cid = _get_pokemon_card_id(my_active) if my_active else -1

    scored = []
    for i, opt in enumerate(options):
        attack_id = opt.get("attackId") if isinstance(opt, dict) else None
        dmg = _estimate_attack_damage(my_cid, attack_id)
        scored.append((dmg, i))

    scored.sort(reverse=True)
    return _sanitize([idx for _, idx in scored[:max_count]], n, max_count)


def _handle_yes_no(options, max_count, context, obs_current, my_idx):
    """YES_NO(9)：是/否判断"""
    n = len(options)
    if n == 0:
        return []

    yes_idx = None
    no_idx = None
    for i, opt in enumerate(options):
        ot = _get_option_type(opt)
        if ot == _OT_YES:
            yes_idx = i
        elif ot == _OT_NO:
            no_idx = i

    # IS_FIRST: 先手 YES
    if context == _SC_IS_FIRST and yes_idx is not None:
        return _sanitize([yes_idx], n, max_count)

    # MULLIGAN: 有基础宝可梦选 NO，否则 YES
    if context == _SC_MULLIGAN:
        hand = _get_my_hand(obs_current, my_idx)
        has_basic = _has_basic_in_hand(hand)
        if has_basic and no_idx is not None:
            return _sanitize([no_idx], n, max_count)
        if yes_idx is not None:
            return _sanitize([yes_idx], n, max_count)

    # 默认 YES
    if yes_idx is not None:
        return _sanitize([yes_idx], n, max_count)

    # 兜底：第一个合法选项
    return _sanitize([0], n, max_count)


def _handle_energy(options, max_count, context, obs_current, my_idx):
    """ENERGY(4)：选能量 — 优先贴给 active"""
    n = len(options)
    if n == 0:
        return []

    # 优先选 inPlayArea == 0（active）的选项
    for i, opt in enumerate(options):
        if isinstance(opt, dict) and opt.get("inPlayArea") == 0:
            return _sanitize([i], n, max_count)

    # 其次选 inPlayIndex == 0 的
    for i, opt in enumerate(options):
        if isinstance(opt, dict) and opt.get("inPlayIndex") == 0:
            return _sanitize([i], n, max_count)

    return _sanitize([0], n, max_count)


def _handle_evolve(options, max_count, context, obs_current, my_idx):
    """EVOLVE(7)：选进化 — 优先 active 位"""
    n = len(options)
    if n == 0:
        return []

    # 优先选 inPlayArea == 0（active）的选项
    for i, opt in enumerate(options):
        if isinstance(opt, dict) and opt.get("inPlayArea") == 0:
            return _sanitize([i], n, max_count)

    return _sanitize([0], n, max_count)


def _handle_attached_card(options, max_count, context, obs_current, my_idx):
    """ATTACHED_CARD(2)：选贴卡"""
    n = len(options)
    return _sanitize(list(range(min(max_count, n))), n, max_count)


def _handle_card_or_attached(options, max_count, context, obs_current, my_idx):
    """CARD_OR_ATTACHED_CARD(3)：选卡或贴卡"""
    n = len(options)
    return _sanitize(list(range(min(max_count, n))), n, max_count)


def _handle_skill(options, max_count, context, obs_current, my_idx):
    """SKILL(5)：选技能"""
    n = len(options)
    return _sanitize(list(range(min(max_count, n))), n, max_count)


def _handle_count(options, max_count, context, obs_current, my_idx):
    """COUNT(8)：选数字 — 默认选最大值"""
    n = len(options)
    if n == 0:
        return []
    # 选最后一个（最大值）
    return _sanitize([n - 1], n, max_count)


def _handle_special_condition(options, max_count, context, obs_current, my_idx):
    """SPECIAL_CONDITION(10)：选异常状态"""
    n = len(options)
    return _sanitize(list(range(min(max_count, n))), n, max_count)


# ------------------------------------------------------------------
# 4. Agent 入口
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

    try:
        select = obs["select"]
        options = select.get("option", [])
        max_count = select.get("maxCount", 1)
        sel_type = select.get("type", -1)
        context = select.get("context", -1)
        obs_current = obs.get("current", {})
        my_idx = obs_current.get("yourIndex", 0)

        n = len(options)
        if n == 0:
            return []
        if max_count >= n:
            return list(range(n))

        # 路由到对应 handler
        if sel_type == _ST_MAIN:
            return _handle_main(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_CARD:
            return _handle_card(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_ATTACK:
            return _handle_attack(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_YES_NO:
            return _handle_yes_no(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_ENERGY:
            return _handle_energy(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_EVOLVE:
            return _handle_evolve(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_ATTACHED_CARD:
            return _handle_attached_card(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_CARD_OR_ATTACHED_CARD:
            return _handle_card_or_attached(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_SKILL:
            return _handle_skill(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_COUNT:
            return _handle_count(options, max_count, context, obs_current, my_idx)
        elif sel_type == _ST_SPECIAL_CONDITION:
            return _handle_special_condition(options, max_count, context, obs_current, my_idx)
        else:
            return _sanitize(list(range(max_count)), n, max_count)

    except Exception:
        # 绝对安全的兜底：随机选择
        try:
            select = obs["select"]
            options = select.get("option", [])
            max_count = select.get("maxCount", 1)
            n = len(options)
            if n == 0:
                return []
            if max_count >= n:
                return list(range(n))
            return random.sample(range(n), max_count)
        except Exception:
            return []
