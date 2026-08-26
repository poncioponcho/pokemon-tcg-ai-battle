from __future__ import annotations

# =====================================================================
# FROZEN ARENA MIRROR — configA_pristine (config A 行为等价 pristine)
# 冻结于 2026-08-13 晚（D0 后），用途：arena 「vs 真实 config A」诚实基准。
# 溯源：submission_baseline/main.py sha256=411d9dff4c146e3b（探针 55468450 态）
#   → 唯一行为修改 FLAG_RETREAT_PIVOT=True→False；三 flag 现全 False。
# 等价声明：本件 = 行为等价 pristine config A（live 55431232/55451759）。
#   非逐字节 459cf97——盘上无逐字节件（已全项目搜索证实），差异仅 = 三处
#   flag 死代码（全 OFF 门控）。依据：文件内注释「FLAG off 时控制流逐点等价
#   原文件」+ ledger#136 pre_submit_checks「三 flag 全门控逐点 diff=pristine
#   +flag 区 ✓」。
# 牌组：_INLINE_DECK 硬编码 == submission_baseline/deck.csv（sha 2a541d7b）
#   逐表硬断言（#127 纪律）；镜像不读外部 deck.csv，与 CWD 解耦。
# 引擎针：libcg.dylib sha256=7a157f045d333f99（submission_baseline/cg 与
#   comp_data 逐字节一致）；live module_version=1.32.6（42/42 replay）；
#   本地二进制无内嵌版本串，以二进制 sha 代版本号。
# =====================================================================

import os
from collections import defaultdict

from cg.api import (
    AreaType,
    Card,
    CardType,
    EnergyType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_attack,
    all_card_data,
    to_observation_class,
)


class C:
    KYOGRE = 721
    SNOVER = 722
    MEGA_ABOMASNOW_EX = 723

    MAKUHITA = 673
    HARIYAMA = 674
    LUNATONE = 675
    SOLROCK = 676
    RIOLU = 677
    MEGA_LUCARIO_EX = 678

    BASIC_FIGHTING_ENERGY = 6
    DUSK_BALL = 1102
    SWITCH = 1123
    PREMIUM_POWER_PRO = 1141
    FIGHTING_GONG = 1142
    POKE_PAD = 1152
    HERO_CAPE = 1159
    BOSS_ORDERS = 1182
    CARMINE = 1192
    LILLIE_DETERMINATION = 1227
    GRAVITY_MOUNTAIN = 1252

    LUMIOSE_CITY = 1267
    LILLIES_PEARL = 1172
    LEGACY_ENERGY = 12


MEGA_BRAVE = 983
LOW_DECK_COUNT = 10

# [dying_674 port 2026-08-12] 674 ワイルドプレス自伤70: HP<=70 时非KO攻击=自杀白送奖品。
# 移植自我方 main.py:2872 BUG-7 语义 (KO豁免: 能KO目标的攻击照打=奖品交易)。
# 三处 guard 均为 "if FLAG_DYING_674 and ..." 纯前置短路, FLAG off 时控制流逐点等价原文件。
FLAG_DYING_674 = False  # 闸 NO-GO (+0.43pp), 探针提交态=OFF
DYING_674_HP = 70
# [nrg_bench 2026-08-12] setup期 active 非当回合攻击关键 → 能量转 bench。
# top_pilot diff 证据: 赢局 pre-first-KO 喂 active 比例 我们28.2% vs Sixth/ミワ 6-11%。
FLAG_NRG_BENCH = False  # 闸 NO-GO (-0.09pp), 探针提交态=OFF
# [retreat_pivot 2026-08-12] 防守性 prize-denial pivot: 3奖身 active 进对手KO射程 → 撤下保命。
# top_pilot diff 证据: 付费 retreat 我们0.42/局 vs Sixth 2.14/Dipam 1.76/ミワ 1.50。
FLAG_RETREAT_PIVOT = False  # [FROZEN MIRROR] pristine 态=OFF（探针 armed 已翻回，见文件头溯源块）
_DYING674 = {'situations': 0, 'blocked': 0, 'attacks': 0}  # 闸用计数, 不影响决策


# [FROZEN MIRROR] 牌组内联硬编码 == submission_baseline/deck.csv (sha 2a541d7b)，
# 逐表硬断言（#127）；不读外部 deck.csv，与 CWD 解耦。原 DECK_PATH 机制已移除。
_INLINE_DECK = (673, 673, 674, 674, 675, 675, 676, 676, 676, 677, 677, 677,
                678, 678, 678, 678, 1102, 1102, 1102, 1102, 1123, 1123,
                1141, 1141, 1141, 1141, 1142, 1142, 1142, 1142, 1152, 1152,
                6, 1159, 1182, 1182, 1192, 1192, 1192, 1192,
                1227, 1227, 1227, 1227,
                6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
                1182, 677, 1252)
my_deck = list(_INLINE_DECK)
assert len(my_deck) == 60, 'FROZEN MIRROR deck 必须 60 张'


all_card = all_card_data()
card_table = {card.cardId: card for card in all_card}
attack_table = {atk.attackId: atk for atk in all_attack()}  # [retreat_pivot] 对手威胁建模用


class AttackPlan:
    def __init__(
        self,
        attacker: int = -1,
        target: int = -1,
        attack_index: int = -1,
        remain_hp: int = -1,
        needs_energy: bool = False,
    ):
        self.attacker = attacker
        self.target = target
        self.attack_index = attack_index
        self.remain_hp = remain_hp
        self.needs_energy = needs_energy


plan = AttackPlan()
pre_turn = -1
ability_used = False


def get_card(obs: Observation, area: AreaType, index: int, player_index: int) -> Pokemon | Card | None:
    player = obs.current.players[player_index]
    match area:
        case AreaType.DECK:
            return obs.select.deck[index]
        case AreaType.HAND:
            return player.hand[index]
        case AreaType.DISCARD:
            return player.discard[index]
        case AreaType.ACTIVE:
            return player.active[index]
        case AreaType.BENCH:
            return player.bench[index]
        case AreaType.PRIZE:
            return player.prize[index]
        case AreaType.STADIUM:
            return obs.current.stadium[index]
        case AreaType.LOOKING:
            return obs.current.looking[index]
        case _:
            return None


def prize_count(pokemon: Pokemon) -> int:
    data = card_table[pokemon.id]
    count = 3 if data.megaEx else 2 if data.ex else 1
    for card in pokemon.energyCards:
        if card.id == C.LEGACY_ENERGY:
            count -= 1
    for card in pokemon.tools:
        if card.id == C.LILLIES_PEARL and "Lillie" in data.name:
            count -= 1
    return max(0, count)


def target_score(pokemon: Pokemon) -> int:
    data = card_table[pokemon.id]
    score = prize_count(pokemon) * 1000
    score += len(pokemon.energies) * 150
    score += len(pokemon.tools) * 100
    if data.stage2:
        score += 250
    elif data.stage1:
        score += 130

    if pokemon.id in {144, 322, 323, 337}:  # low-value support Pokemon
        score -= 200
    if pokemon.id == C.SNOVER:
        score += 950
    elif pokemon.id == C.MEGA_ABOMASNOW_EX:
        score += 250
    if pokemon.id == C.RIOLU:
        score += 800
    elif pokemon.id == C.MEGA_LUCARIO_EX:
        score += 100
    if pokemon.id == 112 and len(pokemon.energies) >= 1:  # Munkidori
        score += 300
    score += pokemon.hp
    return score


class LucarioPolicy:
    def __init__(self, obs: Observation):
        self.obs = obs
        self.state = obs.current
        self.select = obs.select
        self.context = self.select.context
        self.my_index = self.state.yourIndex
        self.op_index = 1 - self.my_index
        self.me = self.state.players[self.my_index]
        self.opponent = self.state.players[self.op_index]
        self.my_prizes_left = len(self.me.prize)

        self.field_counts = defaultdict(int)
        self.hand_counts = defaultdict(int)
        self.discard_counts = defaultdict(int)
        self.has_ready_lucario_line = False
        self.has_ready_hariyama_line = False
        self.can_switch = False
        self.can_gust = False
        self.can_attack = False
        self.can_use_mega_brave = False
        self.stadium_id = self.state.stadium[0].id if self.state.stadium else 0

        self._count_cards()
        self._scan_main_options()

    def choose(self) -> list[int]:
        if not self.select.option or self.select.maxCount == 0:
            return []

        if self.context == SelectContext.MAIN:
            self._plan_attack()

        scores = [self._score_option(option) for option in self.select.option]
        ranked = [i for i, _ in sorted(enumerate(scores), key=lambda item: item[1], reverse=True)]
        self._remember_lunatone_ability(ranked)
        return ranked[: self.select.maxCount]

    def _count_cards(self) -> None:
        for pokemon in self.me.active + self.me.bench:
            if pokemon is None:
                continue
            self.field_counts[pokemon.id] += 1
            if pokemon.id in {C.MAKUHITA, C.HARIYAMA} and len(pokemon.energies) >= 3:
                self.has_ready_hariyama_line = True
            if pokemon.id in {C.RIOLU, C.MEGA_LUCARIO_EX} and len(pokemon.energies) >= 2:
                self.has_ready_lucario_line = True

        for card in self.me.hand:
            self.hand_counts[card.id] += 1
        for card in self.me.discard:
            self.discard_counts[card.id] += 1

    def _scan_main_options(self) -> None:
        if self.context != SelectContext.MAIN:
            return
        for option in self.select.option:
            if option.type == OptionType.PLAY:
                card = get_card(self.obs, AreaType.HAND, option.index, self.my_index)
                if card.id == C.SWITCH:
                    self.can_switch = True
                elif card.id == C.BOSS_ORDERS:
                    self.can_gust = True
            elif option.type == OptionType.EVOLVE:
                card = get_card(self.obs, AreaType.HAND, option.index, self.my_index)
                if card.id == C.HARIYAMA:
                    self.can_gust = True
            elif option.type == OptionType.RETREAT:
                self.can_switch = True
            elif option.type == OptionType.ATTACK:
                self.can_attack = True
                if option.attackId == MEGA_BRAVE:
                    self.can_use_mega_brave = True

    def _my_board(self) -> list[Pokemon | None]:
        return self.me.active + self.me.bench

    def _opponent_board(self) -> list[Pokemon | None]:
        return self.opponent.active + self.opponent.bench

    def _opponent_has(self, ids: set[int]) -> bool:
        return any(pokemon is not None and pokemon.id in ids for pokemon in self._opponent_board())

    def _opponent_is_water_deck(self) -> bool:
        return self._opponent_has({C.KYOGRE, C.SNOVER, C.MEGA_ABOMASNOW_EX})

    def _opponent_is_crustle_wall(self) -> bool:
        return self._opponent_has({344, 345})

    def _pivot_save_active(self) -> bool:
        """[retreat_pivot] 防守性 prize-denial pivot 判定 (五条件全与)。
        证据: top_pilot diff 付费 retreat 我们0.42/局 vs Sixth 2.14 —— 赛中保奖品 pivot 缺失。"""
        # ① 有 KO 计划 (本回合能 KO 对方) → 拿奖品优先, 不撤
        if plan.attacker >= 0 and plan.remain_hp <= 0:
            return False
        # ② post-KO 锚: 任一方已丢奖品才启用, setup 期零污染
        if len(self.me.prize) >= 6 and len(self.opponent.prize) >= 6:
            return False
        if not self.me.active or self.me.active[0] is None:
            return False
        my_active = self.me.active[0]
        # ③ prize-value-aware: 只保 3 奖身 (3奖身花2能=净+1; 2奖身花2-3能不值)
        if prize_count(my_active) < 3:
            return False
        # ④ bench 要有更便宜的替死鬼 (否则 3奖身换3奖身白丢能量)
        if not any(b is not None and prize_count(b) < 3 for b in self.me.bench):
            return False
        if not self.opponent.active or self.opponent.active[0] is None:
            return False
        # ⑤ KO 射程: 对手 active 下回合最大伤害 (含弱点×2/抵抗-30, +1 能buffer) >= 我 HP
        op = self.opponent.active[0]
        op_data = card_table[op.id]
        my_data = card_table[my_active.id]
        op_energy = len(op.energies) + 1
        max_dmg = 0
        for aid in op_data.attacks:
            atk = attack_table.get(aid)
            if atk is None or len(atk.energies) > op_energy:
                continue
            dmg = atk.damage
            if my_data.weakness == op_data.energyType:
                dmg *= 2
            elif my_data.resistance == op_data.energyType:
                dmg -= 30
            max_dmg = max(max_dmg, dmg)
        return max_dmg >= my_active.hp

    def _can_evolve_board_index(self, board_index: int) -> bool:
        for option in self.select.option:
            if option.type != OptionType.EVOLVE:
                continue
            target_index = option.inPlayIndex
            if option.inPlayArea == AreaType.BENCH:
                target_index += 1
            if target_index == board_index:
                return True
        return False

    def _base_attack(self, pokemon: Pokemon, attack_index: int) -> tuple[int, int, int] | None:
        energy_required = 0
        base_damage = 0
        base_score = 0

        if pokemon.id == C.MEGA_LUCARIO_EX:
            if attack_index == 0:
                energy_required = 1
                base_damage = 130
                base_score += 60 * min(3, self.discard_counts[C.BASIC_FIGHTING_ENERGY])
            else:
                energy_required = 2
                base_damage = 270
            if self._opponent_is_water_deck() and len(self.opponent.prize) <= 3:
                base_score -= 500
        elif attack_index == 1:
            return None
        elif pokemon.id == C.HARIYAMA:
            energy_required = 3
            base_damage = 210
        elif pokemon.id == C.MAKUHITA:
            return None
        elif pokemon.id == C.SOLROCK and self.field_counts[C.LUNATONE] >= 1:
            energy_required = 1
            base_damage = 70

        if base_damage <= 0:
            return None
        return energy_required, base_damage, base_score

    def _base_attack_after_evolution(self, pokemon: Pokemon, board_index: int, attack_index: int):
        if pokemon.id == C.MAKUHITA and attack_index == 0 and self._can_evolve_board_index(board_index):
            return 3, 210, -100
        return self._base_attack(pokemon, attack_index)

    def _plan_attack(self) -> None:
        global plan
        best_score = -1
        plan = AttackPlan()

        if self.state.turn < 2:
            return

        for attacker_index, my_pokemon in enumerate(self._my_board()):
            if my_pokemon is None:
                continue
            if my_pokemon.id == C.HARIYAMA and my_pokemon.hp <= DYING_674_HP:
                _DYING674['situations'] += 1
            if attacker_index != 0 and not self.can_switch:
                break

            for attack_index in range(2):
                attack = self._base_attack_after_evolution(my_pokemon, attacker_index, attack_index)
                if attack is None:
                    continue
                energy_required, base_damage, base_score = attack

                energy_count = len(my_pokemon.energies)
                if attack_index == 1 and attacker_index == 0 and energy_count >= 2 and not self.can_use_mega_brave:
                    break

                needs_energy = False
                if energy_count < energy_required:
                    if self.hand_counts[C.BASIC_FIGHTING_ENERGY] >= 1 and not self.state.energyAttached:
                        energy_count += 1
                        needs_energy = energy_count >= energy_required
                    if not needs_energy:
                        continue

                for target_index, op_pokemon in enumerate(self._opponent_board()):
                    if op_pokemon is None:
                        continue
                    if target_index != 0 and not self.can_gust:
                        break
                    if (
                        self._opponent_is_crustle_wall()
                        and my_pokemon.id == C.MEGA_LUCARIO_EX
                        and op_pokemon.id == 345
                    ):
                        continue

                    damage = base_damage
                    op_data = card_table[op_pokemon.id]
                    if op_data.weakness == EnergyType.FIGHTING:
                        damage *= 2
                    elif op_data.resistance == EnergyType.FIGHTING:
                        damage -= 30

                    # [dying_674 ①] target 层 skip (KO豁免): 非KO攻击=自杀, 剔除出打分空间
                    if (FLAG_DYING_674 and my_pokemon.id == C.HARIYAMA
                            and my_pokemon.hp <= DYING_674_HP):
                        if damage < op_pokemon.hp:
                            _DYING674['blocked'] += 1
                            continue

                    score = target_score(op_pokemon)
                    prize = prize_count(op_pokemon) if op_pokemon.hp <= damage else 0
                    if prize == 0:
                        score *= damage / op_pokemon.hp
                    if len(self.opponent.prize) <= prize:
                        score = 50000

                    score += base_score
                    score += 220 if attacker_index == 0 else 0
                    score += 300 if target_index == 0 else 0
                    score += energy_count

                    if score > best_score:
                        best_score = score
                        plan = AttackPlan(
                            attacker=attacker_index,
                            target=target_index,
                            attack_index=attack_index,
                            remain_hp=op_pokemon.hp - damage,
                            needs_energy=needs_energy,
                        )

        # [dying_674 计数] 最终 plan 若是 dying 674 的非KO攻击: ON 应恒 0, OFF 应 >0
        if plan.attacker >= 0 and plan.remain_hp > 0:
            _bd = self._my_board()
            _pm = _bd[plan.attacker] if plan.attacker < len(_bd) else None
            if _pm is not None and _pm.id == C.HARIYAMA and _pm.hp <= DYING_674_HP:
                _DYING674['attacks'] += 1

    def _energy_target_score(self, pokemon: Pokemon, active: bool) -> int:
        energy_count = len(pokemon.energies)
        score = 8000 + (10 if active else 0)

        if pokemon.id in {C.MAKUHITA, C.HARIYAMA}:
            score += 1 if pokemon.id == C.HARIYAMA else 0
            if self._opponent_is_crustle_wall():
                score += 260 if energy_count < 3 else 30
            else:
                score += 100 if energy_count < 3 else 0
                score -= 50 if self.has_ready_hariyama_line else 0
        elif pokemon.id == C.LUNATONE:
            score -= 100
        elif pokemon.id == C.SOLROCK:
            score += 20 if energy_count < 1 else -100
        elif pokemon.id in {C.RIOLU, C.MEGA_LUCARIO_EX}:
            score += 1 if pokemon.id == C.MEGA_LUCARIO_EX else 0
            score += 100 if energy_count < 2 else 0
            score -= 50 if self.has_ready_lucario_line else 0
        return score

    def _score_option(self, option) -> float:
        if option.type == OptionType.NUMBER:
            return option.number
        if option.type == OptionType.YES:
            return 100 if self.context == SelectContext.IS_FIRST else 1
        if option.type == OptionType.NO:
            return 0
        if option.type == OptionType.CARD:
            return self._score_card_choice(option)
        if option.type == OptionType.PLAY:
            return self._score_play(option)
        if option.type == OptionType.ATTACH:
            return self._score_attach(option)
        if option.type == OptionType.EVOLVE:
            return self._score_evolve(option)
        if option.type == OptionType.ABILITY:
            return self._score_ability(option)
        if option.type == OptionType.RETREAT:
            # [dying_674 ③] RETREAT 偏置: 非KO目的别把 bench 上 dying 674 换进场送死
            if plan.attacker >= 1 and FLAG_DYING_674:
                _bd = self._my_board()
                _pm = _bd[plan.attacker] if plan.attacker < len(_bd) else None
                if (_pm is not None and _pm.id == C.HARIYAMA
                        and _pm.hp <= DYING_674_HP and plan.remain_hp > 0):
                    return -1
            if plan.attacker >= 1:
                return 2000
            # [retreat_pivot] 防守性 pivot: 3奖身 active 进对手KO射程 → 撤下保奖品
            if FLAG_RETREAT_PIVOT and self._pivot_save_active():
                return 2500
            return -1
        if option.type == OptionType.ATTACK:
            # [dying_674 ②] ATTACK 门: 现役 dying 674 的非KO攻击不打出 (① 已拦规划层, 此兜陈旧计划)
            if (
                FLAG_DYING_674
                and plan.attacker == 0
                and plan.remain_hp > 0
                and self.me.active
                and self.me.active[0] is not None
                and self.me.active[0].id == C.HARIYAMA
                and self.me.active[0].hp <= DYING_674_HP
            ):
                return -1
            if (
                self._opponent_is_crustle_wall()
                and self.me.active
                and self.opponent.active
                and self.me.active[0].id == C.MEGA_LUCARIO_EX
                and self.opponent.active[0].id == 345
                and plan.target < 0
            ):
                return -1
            return 1100 if (option.attackId == MEGA_BRAVE) == (plan.attack_index == 1) else 1000
        return 0

    def _score_card_choice(self, option) -> float:
        card = get_card(self.obs, option.area, option.index, option.playerIndex)
        if card is None:
            return 0

        if self.context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
            return self._score_active_choice(option, card)
        if self.context == SelectContext.SETUP_ACTIVE_POKEMON:
            return self._score_setup_active(card)
        if self.context == SelectContext.TO_HAND:
            return self._score_to_hand(card)
        if self.context == SelectContext.ATTACH_FROM and isinstance(card, Pokemon):
            return self._energy_target_score(card, option.area == AreaType.ACTIVE)
        return 0

    def _score_active_choice(self, option, card: Pokemon | Card) -> float:
        if not isinstance(card, Pokemon):
            return 0

        if option.playerIndex != self.my_index:
            return 100 if option.index == plan.target - 1 else 0

        score = len(card.energies) * 2
        if option.index == plan.attacker - 1:
            score += 100
        if card.id == C.MEGA_LUCARIO_EX:
            score += 8 if self._opponent_is_water_deck() and len(self.opponent.prize) <= 3 else 20
        elif card.id == C.HARIYAMA and len(card.energies) >= 2:
            score += 45 if self._opponent_is_crustle_wall() else 15
        elif card.id == C.MAKUHITA and len(card.energies) >= 2:
            score += 35 if self._opponent_is_crustle_wall() else 10
        elif card.id == C.SOLROCK:
            score += 5
        elif card.id == C.RIOLU:
            score += 4
        return score

    def _score_setup_active(self, card: Pokemon | Card) -> int:
        if card.id == C.SOLROCK:
            return 2 if self.state.firstPlayer == self.my_index else 4
        if card.id == C.RIOLU:
            return 3
        if card.id == C.MAKUHITA:
            return 1
        return 0

    def _score_to_hand(self, card: Pokemon | Card) -> float:
        score = 200 - self.hand_counts[card.id] * 100
        if card.id == C.MAKUHITA:
            if self._opponent_is_crustle_wall():
                score += 80 if self.field_counts[card.id] < 2 else -20
            else:
                score += -10 if self.field_counts[card.id] >= 1 else 10
        elif card.id == C.HARIYAMA:
            if self._opponent_is_crustle_wall():
                score += 120 if self.field_counts[C.MAKUHITA] >= 1 else -5
            else:
                score += 20 if self.field_counts[C.MAKUHITA] >= 1 else -20
        elif card.id == C.LUNATONE:
            score += -250 if self.field_counts[card.id] >= 1 else 60
        elif card.id == C.SOLROCK:
            score += -250 if self.field_counts[card.id] >= 1 else 50
        elif card.id == C.RIOLU:
            lucario_line = self.field_counts[C.RIOLU] + self.field_counts[C.MEGA_LUCARIO_EX]
            score += -150 if lucario_line >= 2 else -3 if lucario_line >= 1 else 40
        elif card.id == C.MEGA_LUCARIO_EX:
            score += 40 if self.field_counts[C.RIOLU] >= 1 else -15
        elif card.id == C.BASIC_FIGHTING_ENERGY:
            score += 30 if not ability_used or not self.state.energyAttached else -1
        return score

    def _score_play(self, option) -> float:
        card = get_card(self.obs, AreaType.HAND, option.index, self.my_index)
        data = card_table[card.id]
        if data.cardType == CardType.POKEMON:
            return self._score_play_pokemon(card)
        return self._score_play_trainer(card)

    def _score_play_pokemon(self, card: Card) -> float:
        score = 20000
        if card.id in {C.LUNATONE, C.SOLROCK} and self.field_counts[card.id] >= 1:
            return -1
        if card.id == C.RIOLU and self.field_counts[C.RIOLU] + self.field_counts[C.MEGA_LUCARIO_EX] >= 2:
            return -1
        return score

    def _score_play_trainer(self, card: Card) -> float:
        if card.id == C.SWITCH:
            return 6000 if plan.attacker > 0 else -1
        if card.id == C.PREMIUM_POWER_PRO:
            if self.state.supporterPlayed and plan.remain_hp <= 0:
                return -1
            if not self.can_attack:
                can_bridge_draw = (
                    not self.state.supporterPlayed
                    and self.hand_counts[C.CARMINE] > 0
                    and self.hand_counts[C.LILLIE_DETERMINATION] == 0
                    and not self._low_deck()
                )
                return 3050 if can_bridge_draw else -1
            return 5000
        if card.id == C.BOSS_ORDERS:
            return 3200 if plan.target >= 1 else -1
        if card.id == C.CARMINE:
            return -1 if self._low_deck() else 3000
        if card.id == C.LILLIE_DETERMINATION:
            return -1 if self._low_deck() else 3100
        if card.id == C.GRAVITY_MOUNTAIN:
            return self._score_gravity_mountain()
        return 10000

    def _score_gravity_mountain(self) -> float:
        opponent_has_stage2 = any(
            pokemon is not None and card_table[pokemon.id].stage2 for pokemon in self._opponent_board()
        )
        if opponent_has_stage2:
            return 3500
        return 1200 if self.stadium_id else -1

    def _low_deck(self) -> bool:
        return self.me.deckCount <= LOW_DECK_COUNT

    def _score_attach(self, option) -> float:
        card = get_card(self.obs, AreaType.HAND, option.index, self.my_index)
        pokemon = get_card(self.obs, option.inPlayArea, option.inPlayIndex, self.my_index)
        if not isinstance(pokemon, Pokemon):
            return 0

        if card.id == C.HERO_CAPE:
            score = 7000
            if self._opponent_is_water_deck():
                if pokemon.id == C.RIOLU:
                    return 12200
                if pokemon.id == C.MEGA_LUCARIO_EX:
                    return 12800
            if pokemon.id == C.RIOLU:
                score += 100
            elif pokemon.id == C.MEGA_LUCARIO_EX:
                score += 200
            return score

        score = self._energy_target_score(pokemon, option.inPlayArea == AreaType.ACTIVE)
        board_index = option.inPlayIndex if option.inPlayArea == AreaType.ACTIVE else option.inPlayIndex + 1
        if board_index == plan.attacker and plan.needs_energy:
            score += 200
        # [nrg_bench] setup期 active 非当回合攻击关键 → 转 bench
        # (top_pilot diff: 赢局 pre-KO 喂 active 我们28.2% vs Sixth/ミワ 6-11%)
        if FLAG_NRG_BENCH and option.inPlayArea == AreaType.ACTIVE and plan.attacker != 0:
            score -= 200
        return score

    def _score_evolve(self, option) -> float:
        pokemon = get_card(self.obs, option.inPlayArea, option.inPlayIndex, self.my_index)
        if not isinstance(pokemon, Pokemon):
            return 0
        if pokemon.id == C.MAKUHITA and plan.target == 0 and not self._opponent_is_crustle_wall():
            return -1
        return 9000 + len(pokemon.energies)

    def _score_ability(self, option) -> float:
        card = get_card(self.obs, option.area, option.index, self.my_index)
        if card.id == C.LUMIOSE_CITY:
            return 1
        if card.id == C.LUNATONE and self._low_deck():
            return -1
        return 30000

    def _remember_lunatone_ability(self, ranked: list[int]) -> None:
        global ability_used
        if self.context != SelectContext.MAIN or not ranked:
            return
        option = self.select.option[ranked[0]]
        if option.type != OptionType.ABILITY:
            return
        card = get_card(self.obs, option.area, option.index, self.my_index)
        if card is not None and card.id == C.LUNATONE:
            ability_used = True


def agent(obs_dict: dict) -> list[int]:
    # [FROZEN MIRROR patch] 本地 arena 约定：裸 {'select': None} 即请求牌组，
    # 先于 to_observation_class 短路（Kaggle 上 deck 请求 obs 字段齐全，此分支不改变线上行为）。
    if isinstance(obs_dict, dict) and obs_dict.get('select') is None and 'current' not in obs_dict:
        return list(my_deck)
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    global pre_turn
    global ability_used
    global plan

    if pre_turn != obs.current.turn:
        pre_turn = obs.current.turn
        ability_used = False
        plan = AttackPlan()

    return LucarioPolicy(obs).choose()
