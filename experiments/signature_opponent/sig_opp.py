"""sig_opp.py — 签名对手变体（N0 工程件①，2026-08-13 Kimi 自建，用户指派）

= config A pristine（experiments/runs/_configA/main_configA_pristine.py 逐字节为底）
+ 签名旋钮（模块常量，harness 覆写）
+ 自观测 watcher（签名量测，spec §3.1 事件语义逐字复用的 obs 侧实现）。

口径回链（spec §3.2 obs 侧映射的落地实现，experiments/pilot_investigation/signature_caliber_spec.md）：
  watcher 直接消费 agent 每次被调拿到的 obs['logs']（与 replay 同一日志流），
  事件语义与 §3.1 八条逐字一致：新鲜窗口 / type8 自愿 vs Boss gust 剔除 /
  type11 serial→area 追踪器（4=active 5=bench，未定位计入分母）/ 首 KO·丢奖界（任一方）/
  Boss=type4 cardId==1182 / 单局打标。能量定位机制与 replay watcher 同源（同样只见过
  type6/7 移动事件的 serial 可定位）→ E1 直接与 §2 冻结带（6.2-10.9%）可比，无需折算。
  量测对象=本模块自身（对手侧）；5→4 不进 R 轴（规则3）。

旋钮（runbook §1 网格，experiments/pilot_investigation/n1_knob_scan_runbook.md）：
  SIG_RETREAT_ON          retreat 轴总开关（False ≡ config A 行为地板）
  SIG_RETREAT_PRIZE_SCOPE ③ prize 保护范围：3=只保3奖身 / 2=2奖身起保
  SIG_RETREAT_BUFFER      ⑤ KO 射程 buffer：对手能量 +1+buf 回合前瞻（越大越早撤）
  SIG_NRG_ACTIVE_PENALTY  能量 active 灌注罚分：0/200/400/800/1600
挂载点 = 探针验证过的两处（submission_baseline 的 _pivot_save_active 五条件 +
  _score_attach 的 nrg_bench 钩子），参数化后机械行为已被闸验证（invalid 0 / parity 过）。

deck 注意：本模块 my_deck 从不使用——harness 始终显式传 meta 牌组给 play()
（lesson #127：DECK_PATH 相对 cwd 会捡根 deck.csv，但那是死代码，勿依赖勿删）。
"""
from __future__ import annotations

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

# ---- 签名旋钮（harness 覆写；默认值 = R-00 保守档） ----
SIG_RETREAT_ON = False            # 总开关：False ≡ config A 地板（BASE 格）
SIG_RETREAT_PRIZE_SCOPE = 3       # ③ 保护范围：3=只保3奖身，2=2奖身起保
SIG_RETREAT_BUFFER = 0            # ⑤ KO 射程 buffer：0/+1/+2
SIG_NRG_ACTIVE_PENALTY = 0        # 能量 active 罚分：0/200/400/800/1600


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


DECK_PATH = "deck.csv"
if not os.path.exists(DECK_PATH):
    DECK_PATH = "/kaggle_simulations/agent/deck.csv"
with open(DECK_PATH, "r", encoding="utf-8") as f:
    my_deck = [int(line) for line in f.read().splitlines() if line.strip()]


all_card = all_card_data()
card_table = {card.cardId: card for card in all_card}
attack_table = {atk.attackId: atk for atk in all_attack()}  # [签名旋钮⑤] 对手威胁建模用


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
        """[签名旋钮 retreat 轴] 防守性 prize-denial pivot 判定（五条件全与）。
        移植自探针验证过的 submission_baseline._pivot_save_active，③⑤ 参数化：
        ③ SIG_RETREAT_PRIZE_SCOPE（3=只保3奖身 / 2=2奖身起保，④ 替死鬼同 scope 更便宜）
        ⑤ SIG_RETREAT_BUFFER（对手能量前瞻 +1+buf 回合，越大越早撤 → R2 越高）"""
        # ① 有 KO 计划 (本回合能 KO 对方) → 拿奖品优先, 不撤
        if plan.attacker >= 0 and plan.remain_hp <= 0:
            return False
        # ② post-KO 锚: 任一方已丢奖品才启用, setup 期零污染
        if len(self.me.prize) >= 6 and len(self.opponent.prize) >= 6:
            return False
        if not self.me.active or self.me.active[0] is None:
            return False
        my_active = self.me.active[0]
        # ③ prize-value-aware（旋钮 scope）
        if prize_count(my_active) < SIG_RETREAT_PRIZE_SCOPE:
            return False
        # ④ bench 要有比 scope 便宜的替死鬼
        if not any(b is not None and prize_count(b) < SIG_RETREAT_PRIZE_SCOPE for b in self.me.bench):
            return False
        if not self.opponent.active or self.opponent.active[0] is None:
            return False
        # ⑤ KO 射程（旋钮 buffer）: 对手 active 下回合最大伤害 (含弱点×2/抵抗-30) >= 我 HP
        op = self.opponent.active[0]
        op_data = card_table[op.id]
        my_data = card_table[my_active.id]
        op_energy = len(op.energies) + 1 + SIG_RETREAT_BUFFER
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
            if plan.attacker >= 1:
                return 2000
            # [签名旋钮 retreat 轴] 防守性 pivot（压过 ATTACK 1000-1100，低于关键 PLAY）
            if SIG_RETREAT_ON and self._pivot_save_active():
                return 2500
            return -1
        if option.type == OptionType.ATTACK:
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
        # [签名旋钮 nrg 轴] active 非当回合攻击关键 → 罚分转 bench
        # (探针验证过的 nrg_bench 钩子参数化；罚分量级扫 200/400/800/1600)
        if SIG_NRG_ACTIVE_PENALTY > 0 and option.inPlayArea == AreaType.ACTIVE and plan.attacker != 0:
            score -= SIG_NRG_ACTIVE_PENALTY
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


# ================= 签名量测 watcher（spec §3.1 事件语义逐字复用，obs 侧实现） =================
class SigWatcher:
    """消费 obs['logs']（与 replay 同一日志流），按 spec §3.1 八条口径累计本模块（对手侧）签名事件。

    规则映射（逐条）：
      1 新鲜窗口：lg == prev 整步跳过；prev 是 lg 前缀则只处理增量（两种投递形态都正确）。
      2 单侧视角：只统计 playerIndex == me（me = current.yourIndex，逐调用读取）。
      3 换位：type8 = active↔bench swap；对手 pending Boss 配对中的 type8 = gust 受害（sw8_gust，
        非决策）否则自愿（sw8_vol，R 轴）；首次 KO/丢奖前的自愿另记（sw8_vol_pre）。
        换上来的怪下一次 type15 攻击命中 → sw8_atk（R3 监控）。5→4 不进 R 轴（不统计）。
      4 能量：type11；serial→area 追踪器（type6/7 维护 (side,serial)→toArea），
        area 4=active 5=bench，未定位计入分母（nrg_pre/nrg 计数含未定位）。
      5 首 KO/丢奖界：type6/7 中 toArea==3 且 fromArea∈(4,5)（KO）或 fromArea==6 且 toArea==2
        （拿奖），任一方首次即封窗（first_ko_seen）。
      6 Boss：type4 且 cardId==1182 → 对手打出时置 pending_boss。
      7 KO 受害者：R2/E1 不需要，不统计（保持 watcher 最小但口径忠实）。
      8 镜像局：本地 harness 无 TeamNames 镜像问题，不需 flag。
    局界：current.turn 单调、新局回落 → finalize 上一局。
    """

    KEYS = ('t8', 'sw8_gust', 'sw8_vol', 'sw8_vol_pre', 'sw8_atk',
            'nrg', 'nrg_act', 'nrg_bench', 'nrg_pre', 'nrg_pre_act', 'nrg_pre_bench')

    def __init__(self):
        self.games = []
        self._reset_game()

    def _reset_game(self):
        self.prev_logs = None
        self.prev_turn = None
        self.loc = {}
        self.pending_boss = {0: False, 1: False}
        self.pending_vol8 = {0: None, 1: None}
        self.first_ko_seen = False
        self.g = {k: 0 for k in self.KEYS}

    def finalize(self):
        """harness 在批次结束（及新局检测）时调用，封账当前局。"""
        if self.prev_logs is not None or any(self.g.values()):
            self.games.append(self.g)
        self._reset_game()

    def observe(self, obs_dict):
        cur = obs_dict.get('current') or {}
        me = cur.get('yourIndex')
        if me not in (0, 1):
            return
        turn = cur.get('turn')
        if turn is not None and self.prev_turn is not None and turn < self.prev_turn:
            self.finalize()                      # 新局（turn 回落）
        if turn is not None:
            self.prev_turn = turn
        lg = obs_dict.get('logs') or []
        if lg == self.prev_logs:
            return                               # 规则1 新鲜窗口
        if self.prev_logs and lg[: len(self.prev_logs)] == self.prev_logs:
            events = lg[len(self.prev_logs):]    # 累计型投递：只取增量
        else:
            events = lg                          # delta 型投递：全部为新
        self.prev_logs = lg
        for e in events:
            t = e.get('type')
            side = e.get('playerIndex')
            if t in (6, 7):
                fa, ta = e.get('fromArea'), e.get('toArea')
                se = e.get('serial')
                if se is not None and ta is not None:
                    self.loc[(side, se)] = ta    # 规则4 serial 追踪器
                if not self.first_ko_seen and ((ta == 3 and fa in (4, 5)) or (fa == 6 and ta == 2)):
                    self.first_ko_seen = True    # 规则5 首 KO/丢奖界（任一方）
            if side != me:
                if t == 4 and e.get('cardId') == 1182 and side in (0, 1):
                    self.pending_boss[side] = True   # 规则6 对手 Boss 待配对
                continue
            if t == 8:                               # 规则3 换位
                self.g['t8'] += 1
                if self.pending_boss[1 - me]:
                    self.g['sw8_gust'] += 1          # gust 受害（非决策）
                    self.pending_boss[1 - me] = False
                else:
                    self.g['sw8_vol'] += 1           # 自愿换位（R 轴真决策）
                    if not self.first_ko_seen:
                        self.g['sw8_vol_pre'] += 1
                    self.pending_vol8[me] = e.get('cardIdBench')
            elif t == 15:
                if self.pending_vol8[me] is not None:
                    if e.get('cardId') == self.pending_vol8[me]:
                        self.g['sw8_atk'] += 1
                    self.pending_vol8[me] = None
            elif t == 11:                            # 规则4 能量
                self.g['nrg'] += 1
                area = self.loc.get((me, e.get('serialTarget')))
                if area == 4:
                    self.g['nrg_act'] += 1
                elif area == 5:
                    self.g['nrg_bench'] += 1
                if not self.first_ko_seen:
                    self.g['nrg_pre'] += 1
                    if area == 4:
                        self.g['nrg_pre_act'] += 1
                    elif area == 5:
                        self.g['nrg_pre_bench'] += 1


WATCHER = SigWatcher()


def reset_stats():
    """harness 每 (格, 腿) 批次前调用。"""
    WATCHER.games.clear()
    WATCHER._reset_game()


def finalize_stats():
    """harness 每 (格, 腿) 批次后调用（封账最后一局）。"""
    WATCHER.finalize()


def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    global pre_turn
    global ability_used
    global plan

    WATCHER.observe(obs_dict)

    if pre_turn != obs.current.turn:
        pre_turn = obs.current.turn
        ability_used = False
        plan = AttackPlan()

    return LucarioPolicy(obs).choose()
