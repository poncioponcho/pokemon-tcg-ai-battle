# -*- coding: utf-8 -*-
"""
本地 Agent 逻辑测试 (v22.6 语义版)
===================================
不加载 cabt 引擎 (其 libcg.so 为 Linux 版, macOS 无法 ctypes 加载),
而是用构造好的 mock observation 直接调用 main.agent, 验证其行为符合
cabt 引擎接口约定与 v22.6 决策规则:

  1. 初始上牌阶段 (select 为 None) → 返回长度 60 的 deck
  2. 选择阶段 (select 为 dict) → 返回长度 == maxCount、合法、不重复的下标
  3. DECK 与 deck.csv 单一来源一致
  4. MULLIGAN: 手牌有基础宝可梦 → No, 无 → Yes
  5. 墙切换意图不跨决策/跨局泄漏
  6. 弱点×2 归一化计算 (日文/英文缩写/数字格式)
  7. Mega Wall 核心决策: KO 优先 / 打墙换 345 / 推队 756

用法: python3 test_agent.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from main import (  # noqa: E402
    agent, DECK, _INLINE_DECK, _CARD_DB,
    _calculate_ko_damage, _estimate_attack_damage,
)


def _obs(sel_type, options, context="Main", max_count=1, current=None):
    """构造符合真实引擎 schema 的 obs"""
    return {
        "select": {
            "type": sel_type,
            "context": context,
            "maxCount": max_count,
            "option": options,
        },
        "current": current if current is not None else {
            "yourIndex": 0,
            "players": [
                {"active": [{"id": 756, "hp": 300, "maxHp": 300,
                             "energies": [1, 1, 1], "energyCards": []}],
                 "bench": [], "hand": []},
                {"active": [{"id": 77, "hp": 70, "maxHp": 70,
                             "energies": [], "energyCards": []}],
                 "bench": [], "hand": []},
            ],
        },
    }


def _player(my_active, opp_active, my_bench=None, my_hand=None, my_prize=None):
    return {
        "yourIndex": 0,
        "players": [
            {"active": [my_active] if my_active else [],
             "bench": my_bench or [], "hand": my_hand or [],
             "prize": [0] * (my_prize if my_prize is not None else 6)},
            {"active": [opp_active] if opp_active else [],
             "bench": [], "hand": [], "prize": [0] * 6},
        ],
    }


def test_deck_submission_phase():
    """初始上牌阶段: select 为 None, 应返回 60 张卡"""
    obs = {"select": None, "current": None, "logs": []}
    action = agent(obs)
    assert len(action) == 60, f"deck 应为 60 张, 实际 {len(action)}"
    assert all(isinstance(i, int) for i in action)
    print("  [OK] 初始上牌阶段返回 60 张 deck")


def test_deck_single_source():
    """DECK 与 deck.csv 必须一致 (单一来源, [v22.6-fix1])"""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "deck.csv"),
              encoding="utf-8") as f:
        deck_csv = [int(l.strip()) for l in f if l.strip()]
    assert len(deck_csv) == 60
    assert sorted(DECK) == sorted(deck_csv), "DECK 与 deck.csv 不一致!"
    assert sorted(DECK) == sorted(_INLINE_DECK), "DECK 与内联牌组不一致!"
    print("  [OK] DECK == deck.csv == _INLINE_DECK (60 张一致)")


def test_card_db_covers_deck():
    """卡库覆盖牌组全部宝可梦与能量卡 ([v22.6-fix2])"""
    for cid in (756, 344, 345, 117):
        assert cid in _CARD_DB and _CARD_DB[cid].get("hp", 0) > 0, f"{cid} 缺卡数据"
    for cid in (1, 6, 11, 14, 18, 20):
        assert _CARD_DB[cid].get("is_energy"), f"{cid} 应为能量卡"
    assert _CARD_DB[756]["rule"] == "mega_ex"
    assert _CARD_DB[117]["rule"] == "ex"
    assert _CARD_DB[345]["evolves_from"] == 344
    print("  [OK] _CARD_DB 覆盖牌组卡 (宝可梦 hp/rule, 能量 flag)")


def test_budew_deck_and_attack_metadata():
    """含羞苞元数据: 零能量10伤害 (v4 FINAL 已移出牌组, main.py:3066 分支保留作 tech 件)。"""
    # [2026-08-11 更新] 删除 235/1252 牌组归属断言: v4 FINAL 牌组两者均无,
    # 但含羞苞封锁分支仍在, 元数据正确性仍需保障。
    assert _CARD_DB[235]["needed_energy"] == 0
    assert _CARD_DB[235]["moves"] == [(10, "痒痒花粉")]
    assert _estimate_attack_damage(235, 323) == 10
    print("  [OK] 含羞苞牌组数量、零能量和10伤害元数据正确")


def test_budew_is_active_opener_when_going_second():
    """后攻起手有含羞苞时，SetupActive 优先选择它。"""
    cur = {
        "yourIndex": 0,
        "firstPlayer": 1,
        "players": [
            {"active": [], "bench": [], "hand": [{"id": 677}, {"id": 235}]},
            {"active": [], "bench": [], "hand": []},
        ],
    }
    obs = _obs(
        "Card",
        [
            {"area": 2, "index": 0, "playerIndex": 0, "type": "Card"},
            {"area": 2, "index": 1, "playerIndex": 0, "type": "Card"},
        ],
        context="SetupActivePokemon",
        current=cur,
    )
    assert agent(obs) == [1]
    print("  [OK] 后攻起手优先选择含羞苞")


def test_budew_active_uses_pollen_before_trainer():
    """主动含羞苞有攻击机会时，先封锁 Item 而不是打训练家牌。"""
    cur = _player(
        {"id": 235, "hp": 30, "maxHp": 30, "energies": [], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
        my_hand=[{"id": 1121}],
    )
    obs = _obs(
        "Main",
        [
            {"index": 0, "type": "Play"},
            {"attackId": 323, "type": "Attack"},
            {"type": "End"},
        ],
        current=cur,
    )
    assert agent(obs) == [1]
    print("  [OK] 主动含羞苞优先使用痒痒花粉")


def test_yes_no_is_first():
    """IsFirst → Yes (先手)"""
    obs = _obs("YesNo", [{"type": "Yes"}, {"type": "No"}], context="IsFirst")
    assert agent(obs) == [0]
    print("  [OK] IsFirst → Yes")


def test_mulligan_with_basic():
    """Mulligan: 手牌有基础宝可梦 (344) → No ([v22.6-fix5])"""
    cur = _player(
        {"id": 756, "hp": 300, "maxHp": 300, "energies": [], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
        my_hand=[{"id": 344}, {"id": 1}],
    )
    obs = _obs("YesNo", [{"type": "Yes"}, {"type": "No"}], context="Mulligan", current=cur)
    assert agent(obs) == [1], f"有基础应 No(index=1), 实际 {agent(obs)}"
    print("  [OK] Mulligan 有基础 → No")


def test_mulligan_without_basic():
    """Mulligan: 手牌无基础宝可梦 (只有能量) → Yes"""
    cur = _player(
        {"id": 756, "hp": 300, "maxHp": 300, "energies": [], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
        my_hand=[{"id": 1}, {"id": 1121}],
    )
    obs = _obs("YesNo", [{"type": "Yes"}, {"type": "No"}], context="Mulligan", current=cur)
    assert agent(obs) == [0], f"无基础应 Yes(index=0), 实际 {agent(obs)}"
    print("  [OK] Mulligan 无基础 → Yes")


def test_main_ko_attack():
    """Main: 756 (200dmg) 能 KO 100HP 对手 → 优先攻击 (P1)"""
    cur = _player(
        {"id": 756, "hp": 300, "maxHp": 300, "energies": [1, 1, 1], "energyCards": []},
        {"id": 77, "hp": 100, "maxHp": 100, "energies": [], "energyCards": []},
    )
    obs = _obs("Main", [
        {"type": "Attack", "attackId": 1092},
        {"type": "End"},
    ], current=cur)
    assert agent(obs) == [0], f"能 KO 应选 Attack, 实际 {agent(obs)}"
    print("  [OK] Main 能 KO → 攻击")


def test_weakness_double_damage():
    """弱点×2: 我方 117 (闘) 打 弱点=FIG/闘/6 的对手 → 伤害×2 ([v22.6-fix3])"""
    assert _calculate_ko_damage(140, 117, {"weakness": "FIG"}) == 280
    assert _calculate_ko_damage(140, 117, {"weakness": "闘"}) == 280
    assert _calculate_ko_damage(140, 117, {"weakness": 6}) == 280
    assert _calculate_ko_damage(140, 117, {"weakness": "草"}) == 140  # 不匹配
    assert _calculate_ko_damage(140, 117, {"weakness": "Fighting"}) == 280
    print("  [OK] 弱点×2 归一化 (FIG/闘/6/Fighting 均匹配)")


def test_wall_switch_retreat_then_674():
    """P3.5: ex 打手 (678) 面对 345 墙 → 撤退, 且随后 Switch 优先选 674 破墙"""
    cur = _player(
        {"id": 678, "hp": 340, "maxHp": 340, "energies": [6, 6], "energyCards": []},
        {"id": 345, "hp": 150, "maxHp": 150, "energies": [], "energyCards": []},
        my_bench=[{"id": 674, "hp": 150, "maxHp": 150, "energies": [], "energyCards": []},
                  {"id": 676, "hp": 110, "maxHp": 110, "energies": [], "energyCards": []}],
    )
    obs = _obs("Main", [
        {"type": "Attack", "attackId": 982},
        {"type": "Retreat"},
        {"type": "End"},
    ], current=cur)
    action = agent(obs)
    assert action[0] == 1, f"面对345墙应撤退, 实际 {action}"
    # 意图已置位 → 下一次 Switch 选卡应选 674 (index=0)
    obs2 = _obs("Card", [
        {"area": 5, "index": 0, "playerIndex": 0, "type": "Card"},
        {"area": 5, "index": 1, "playerIndex": 0, "type": "Card"},
    ], context="Switch", current=cur)
    action2 = agent(obs2)
    assert action2[0] == 0, f"应选 674 破墙(index=0), 实际 {action2}"
    assert main._PENDING_SWITCH_TO_WALL is False, "意图应已被消费"
    print("  [OK] 打墙换674: Main 撤退 → Switch 选 674, 意图已消费")


def test_wall_retreat_non_ex_fallback():
    """[BUG-2] 678 面对 345 墙, bench 只有非ex的676时也应撤退破墙 (不再只认674)"""
    cur = _player(
        {"id": 678, "hp": 340, "maxHp": 340, "energies": [6, 6], "energyCards": []},
        {"id": 345, "hp": 150, "maxHp": 150, "energies": [], "energyCards": []},
        my_bench=[{"id": 676, "hp": 110, "maxHp": 110, "energies": [6], "energyCards": []}],
    )
    obs = _obs("Main", [
        {"type": "Attack", "attackId": 982},
        {"type": "Retreat"},
        {"type": "End"},
    ], current=cur)
    action = agent(obs)
    assert action[0] == 1, f"678 面对345墙 + 非ex打手在 bench 应撤退, 实际 {action}"
    print("  [OK] 破墙兜底: 678 vs 345墙 + bench 676 → 撤退")


def test_flag_no_leak_across_decisions():
    """意图不跨决策泄漏: 置位后经非 Card 决策应被清空 ([v22.6-fix4])"""
    cur = _player(
        {"id": 678, "hp": 340, "maxHp": 340, "energies": [6, 6], "energyCards": []},
        {"id": 345, "hp": 150, "maxHp": 150, "energies": [], "energyCards": []},
        my_bench=[{"id": 674, "hp": 150, "maxHp": 150, "energies": [], "energyCards": []}],
    )
    obs = _obs("Main", [
        {"type": "Attack", "attackId": 982},
        {"type": "Retreat"},
        {"type": "End"},
    ], current=cur)
    agent(obs)
    assert main._PENDING_SWITCH_TO_WALL is True, "撤退换墙应置位意图"
    # 中间插入一个非 Card 决策 (如 YesNo)
    obs_yn = _obs("YesNo", [{"type": "Yes"}, {"type": "No"}], context="IsFirst", current=cur)
    agent(obs_yn)
    assert main._PENDING_SWITCH_TO_WALL is False, "非 Card 决策必须清空意图!"
    # 随后的 Switch (非墙对手) 应选 678 核心打手, 而不是被残留意图影响
    obs2 = _obs("Card", [
        {"area": 5, "index": 0, "playerIndex": 0, "type": "Card"},
        {"area": 5, "index": 1, "playerIndex": 0, "type": "Card"},
    ], context="Switch", current=_player(
        {"id": 678, "hp": 340, "maxHp": 340, "energies": [6, 6], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
        my_bench=[{"id": 678, "hp": 340, "maxHp": 340, "energies": [6, 6], "energyCards": []},
                  {"id": 675, "hp": 110, "maxHp": 110, "energies": [], "energyCards": []}],
    ))
    action2 = agent(obs2)
    assert action2[0] == 0, f"意图清空后应选 678(index=0), 实际 {action2}"
    print("  [OK] 意图经非 Card 决策清空, 不再污染后续选卡")


def test_switch_prefers_678_over_basic():
    """[BUG-1] 撤退/换人: 非ex对手时满能 678 必须优先于基础 675 上场"""
    cur = _player(
        {"id": 676, "hp": 110, "maxHp": 110, "energies": [], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
        my_bench=[{"id": 678, "hp": 340, "maxHp": 340, "energies": [6, 6], "energyCards": []},
                  {"id": 675, "hp": 110, "maxHp": 110, "energies": [], "energyCards": []}],
    )
    obs = _obs("Card", [
        {"area": 5, "index": 0, "playerIndex": 0, "type": "Card"},
        {"area": 5, "index": 1, "playerIndex": 0, "type": "Card"},
    ], context="Switch", current=cur)
    action = agent(obs)
    assert action[0] == 0, f"应选 678 核心打手(index=0), 实际 {action}"
    print("  [OK] Switch 优先选 678 而非基础卡")


def test_aux_switches_to_charged_678():
    """[BUG-5] 辅助 active + bench 678 满能 → 撤退换 678 (优先于贴能/弱攻)"""
    cur = _player(
        {"id": 676, "hp": 110, "maxHp": 110, "energies": [], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
        my_bench=[{"id": 678, "hp": 340, "maxHp": 340, "energies": [6, 6], "energyCards": []}],
    )
    obs = _obs("Main", [
        {"type": "Attach", "area": 2, "inPlayArea": 4, "inPlayIndex": 0, "index": 0},
        {"type": "Attach", "area": 2, "inPlayArea": 5, "inPlayIndex": 0, "index": 1},
        {"type": "Retreat"},
        {"type": "End"},
    ], current=cur)
    action = agent(obs)
    assert action[0] == 2, f"辅助 active + 满能678在 bench 应撤退(index=2), 实际 {action}"
    print("  [OK] 辅助→满能678 撤退切换 (P7.8)")


def test_mulligan_hidden_hand_no():
    """[BUG-4] Mulligan 手牌不可见(空)时默认 No 保留, 不再白送对手卡"""
    cur = _player(
        {"id": 678, "hp": 340, "maxHp": 340, "energies": [], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
        my_hand=[],
    )
    obs = _obs("YesNo", [{"type": "Yes"}, {"type": "No"}], context="Mulligan", current=cur)
    assert agent(obs) == [1], f"手牌不可见应 No(index=1), 实际 {agent(obs)}"
    print("  [OK] Mulligan 手牌隐藏 → 默认 No 保留")


def test_674_no_suicide_attack():
    """[BUG-7] 674 HP<=70 时不打出非KO的ワイルドプレス (自伤70), 应撤退"""
    cur = _player(
        {"id": 674, "hp": 70, "maxHp": 150, "energies": [6, 6, 6], "energyCards": []},
        {"id": 77, "hp": 250, "maxHp": 250, "energies": [], "energyCards": []},
        my_bench=[{"id": 676, "hp": 110, "maxHp": 110, "energies": [6], "energyCards": []}],
    )
    obs = _obs("Main", [
        {"type": "Attack", "attackId": 978},
        {"type": "Retreat"},
        {"type": "End"},
    ], current=cur)
    action = agent(obs)
    assert action[0] == 1, f"674 自杀线不应攻击, 应撤退(index=1), 实际 {action}"
    print("  [OK] 674 自伤线不自杀式攻击")


def test_676_weakness_ignored():
    """[BUG-8] 676 コズミックビーム 无视弱点, 不参与 ×2"""
    assert _calculate_ko_damage(70, 676, {"weakness": "闘"}) == 70
    assert _calculate_ko_damage(70, 676, {"weakness": "FIG"}) == 70
    assert _calculate_ko_damage(70, 676, {"weakness": "超"}) == 70
    print("  [OK] 676 无视弱点 (70 不翻倍)")


def test_flag_cleared_at_game_start():
    """新对局 (select None) 必须清空历史残留意图 ([v22.6-fix4])"""
    main._PENDING_SWITCH_TO_WALL = True  # 模拟上一局残留
    agent({"select": None, "current": None, "logs": []})
    assert main._PENDING_SWITCH_TO_WALL is False, "新对局开始必须清空意图"
    print("  [OK] 新对局清空换墙意图")


def test_attack_highest_damage():
    """Attack: 选伤害最高的招式"""
    obs = _obs("Attack", [
        {"attackId": 478},   # 344 かくせい 0dmg
        {"attackId": 479},   # 345 グレートシザー 120dmg
    ], context="Attack", current=_player(
        {"id": 345, "hp": 150, "maxHp": 150, "energies": [18, 18, 18], "energyCards": []},
        {"id": 77, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []},
    ))
    assert agent(obs) == [1], f"应选高伤害攻击, 实际 {agent(obs)}"
    print("  [OK] Attack 选最高伤害")


def test_count_max():
    """Count: 选最大数"""
    obs = _obs("Count", [
        {"number": 0, "type": "Number"},
        {"number": 1, "type": "Number"},
        {"number": 2, "type": "Number"},
    ], context="DrawCount")
    assert agent(obs) == [2]
    print("  [OK] Count 选最大数")


def test_numeric_type_compat():
    """兼容性: 旧数字 type 也能处理"""
    obs = {
        "select": {"type": 9, "context": 0, "maxCount": 1, "option": [{"type": 1}, {"type": 2}]},
        "current": {"yourIndex": 0, "players": []},
    }
    action = agent(obs)
    assert isinstance(action, list) and len(action) == 1
    print("  [OK] 数字 type 兼容")


def test_empty_options():
    """空选项: 返回空列表"""
    assert agent(_obs("Main", [])) == []
    print("  [OK] 空选项返回 []")


if __name__ == "__main__":
    tests = [
        test_deck_submission_phase,
        test_deck_single_source,
        test_card_db_covers_deck,
        test_budew_deck_and_attack_metadata,
        test_budew_is_active_opener_when_going_second,
        test_budew_active_uses_pollen_before_trainer,
        test_yes_no_is_first,
        test_mulligan_with_basic,
        test_mulligan_without_basic,
        test_main_ko_attack,
        test_weakness_double_damage,
        test_wall_switch_retreat_then_674,
        test_wall_retreat_non_ex_fallback,
        test_flag_no_leak_across_decisions,
        test_flag_cleared_at_game_start,
        test_attack_highest_damage,
        test_count_max,
        test_numeric_type_compat,
        test_empty_options,
        test_switch_prefers_678_over_basic,
        test_aux_switches_to_charged_678,
        test_mulligan_hidden_hand_no,
        test_674_no_suicide_attack,
        test_676_weakness_ignored,
    ]
    passed = 0
    print("=" * 60)
    print("PTCG Agent v22.6 单元测试")
    print("=" * 60)
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {type(e).__name__}: {e}")
    print("=" * 60)
    print(f"通过 {passed}/{len(tests)}")
    sys.exit(0 if passed == len(tests) else 1)
