# -*- coding: utf-8 -*-
"""
卡牌数据分析脚本
================
分析官方卡牌数据 CSV，提取关键信息用于优化 Agent 策略和卡组构建。
"""

import csv
import json
from collections import defaultdict

# 读取卡牌数据
def load_cards(csv_path):
    """读取 EN_Card_Data.csv"""
    cards = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cards.append(row)
    return cards

def analyze_alakazam_line(cards):
    """分析 Alakazam 进化链"""
    print("=" * 60)
    print("Alakazam 进化链分析")
    print("=" * 60)
    
    # 搜索所有 Abra, Kadabra, Alakazam
    abra_cards = [c for c in cards if 'Abra' in c['Card Name'] and 'Kadabra' not in c['Card Name']]
    kadabra_cards = [c for c in cards if 'Kadabra' in c['Card Name']]
    alakazam_cards = [c for c in cards if 'Alakazam' in c['Card Name']]
    
    print(f"\n找到 {len(abra_cards)} 张 Abra, {len(kadabra_cards)} 张 Kadabra, {len(alakazam_cards)} 张 Alakazam")
    
    # 按扩展包分组
    expansions = defaultdict(lambda: {'Abra': [], 'Kadabra': [], 'Alakazam': []})
    
    for c in abra_cards:
        expansions[c['Expansion']]['Abra'].append(c)
    for c in kadabra_cards:
        expansions[c['Expansion']]['Kadabra'].append(c)
    for c in alakazam_cards:
        expansions[c['Expansion']]['Alakazam'].append(c)
    
    print("\n按扩展包分组:")
    for exp, cards_dict in sorted(expansions.items()):
        print(f"\n{exp}:")
        for stage, stage_cards in cards_dict.items():
            for c in stage_cards:
                card_id = c['Card ID']
                name = c['Card Name']
                hp = c['HP']
                stage_type = c.get('Stage (Pokémon)/Type (Energy and Trainer)', '')
                print(f"  {stage}: ID={card_id} {name} HP={hp} ({stage_type})")
                
                # 打印攻击
                if c['Move Name'] and c['Move Name'] != 'n/a':
                    cost = c['Cost'] if c['Cost'] != 'n/a' else '?'
                    damage = c['Damage'] if c['Damage'] != 'n/a' else '?'
                    effect = c['Effect Explanation'][:80] if c['Effect Explanation'] != 'n/a' else ''
                    print(f"    攻击: {c['Move Name']} 费用={cost} 伤害={damage}")
                    if effect:
                        print(f"    效果: {effect}...")

def analyze_dudunsparce(cards):
    """分析 Dudunsparce"""
    print("\n" + "=" * 60)
    print("Dudunsparce 分析")
    print("=" * 60)
    
    dudu_cards = [c for c in cards if 'Dudunsparce' in c['Card Name'] or 'Dunsparce' in c['Card Name']]
    
    for c in dudu_cards:
        card_id = c['Card ID']
        name = c['Card Name']
        hp = c['HP']
        stage_type = c.get('Stage (Pokémon)/Type (Energy and Trainer)', '')
        print(f"\nID={card_id} {name} HP={hp} ({stage_type})")
        
        if c['Move Name'] and c['Move Name'] != 'n/a':
            cost = c['Cost'] if c['Cost'] != 'n/a' else '?'
            damage = c['Damage'] if c['Damage'] != 'n/a' else '?'
            effect = c['Effect Explanation'][:100] if c['Effect Explanation'] != 'n/a' else ''
            print(f"  攻击: {c['Move Name']} 费用={cost} 伤害={damage}")
            if effect:
                print(f"  效果: {effect}...")

def analyze_supporters(cards):
    """分析支援者卡"""
    print("\n" + "=" * 60)
    print("强力支援者卡（抽牌类）")
    print("=" * 60)
    
    supporter_cards = [c for c in cards if c.get('Stage (Pokémon)/Type (Energy and Trainer)') == 'Supporter']
    
    # 搜索抽牌效果
    draw_cards = []
    for c in supporter_cards:
        effect = c.get('Effect Explanation', '')
        if 'Draw' in effect and 'cards' in effect:
            draw_cards.append(c)
    
    print(f"\n找到 {len(draw_cards)} 张抽牌支援者:")
    for c in draw_cards[:15]:
        card_id = c['Card ID']
        name = c['Card Name']
        effect = c['Effect Explanation'][:100]
        print(f"  ID={card_id} {name}: {effect}...")

def analyze_high_damage_attacks(cards):
    """分析高伤害攻击"""
    print("\n" + "=" * 60)
    print("高伤害攻击（>= 100）")
    print("=" * 60)
    
    high_dmg = []
    for c in cards:
        try:
            damage = int(c['Damage']) if c['Damage'] and c['Damage'] != 'n/a' else 0
            if damage >= 100:
                high_dmg.append((damage, c))
        except:
            pass
    
    high_dmg.sort(key=lambda x: x[0], reverse=True)
    
    print(f"\n找到 {len(high_dmg)} 个高伤害攻击:")
    for damage, c in high_dmg[:20]:
        card_id = c['Card ID']
        name = c['Card Name']
        move = c['Move Name']
        cost = c['Cost'] if c['Cost'] != 'n/a' else '?'
        effect = c['Effect Explanation'][:80] if c['Effect Explanation'] != 'n/a' else ''
        print(f"  ID={card_id} {name} - {move}: {damage} 伤害 (费用={cost})")
        if effect:
            print(f"    {effect}...")

def build_optimized_deck(cards):
    """构建优化卡组"""
    print("\n" + "=" * 60)
    print("优化卡组构建")
    print("=" * 60)
    
    # 策略：使用 MEG 进化链（741→742→743），配合抽牌和 Powerful Hand
    deck = []
    
    # 1. MEG Alakazam 进化链
    # Abra (741): HP 50, 攻击 Teleportation Attack（10 + 换位）
    deck.extend([741] * 4)  # 4 张
    
    # Kadabra (742): HP 80, 能力 Psychic Draw（抽 2 卡）, 攻击 Super Psy Bolt（30）
    deck.extend([742] * 3)  # 3 张
    
    # Alakazam (743): HP 140, 能力 Psychic Draw（抽 3 卡）, 攻击 Powerful Hand（2×手牌数）
    deck.extend([743] * 3)  # 3 张
    
    # 2. Dudunsparce (TEF 66): 能力 Run Away Draw（抽 3 卡 + 洗牌回牌库）
    deck.extend([66] * 2)  # 2 张
    # Dunsparce (基础形态，需要搜索 ID)
    # 搜索 Dunsparce
    dunsparce = [c for c in cards if c['Card Name'] == 'Dunsparce']
    if dunsparce:
        deck.extend([int(dunsparce[0]['Card ID'])] * 2)  # 2 张
    
    # 3. Psychic 能量
    # 搜索 Basic Psychic Energy
    psychic_energy = [c for c in cards if 'Basic {P} Energy' in c['Card Name']]
    if psychic_energy:
        deck.extend([int(psychic_energy[0]['Card ID'])] * 12)  # 12 张
    
    # 4. 抽牌支援者
    # Amarys (1207): 抽 4 卡
    deck.extend([1207] * 2)  # 2 张
    # Cheren (1224): 抽 3 卡
    deck.extend([1224] * 2)  # 2 张
    
    # 5. 补足到 60 张
    current_count = len(deck)
    if current_count < 60:
        # 用 Psychic 能量补足
        if psychic_energy:
            while len(deck) < 60:
                deck.append(int(psychic_energy[0]['Card ID']))
    
    # 统计
    from collections import Counter
    cnt = Counter(deck)
    print(f"\n卡组统计 ({len(deck)} 张):")
    for card_id, count in sorted(cnt.items()):
        # 查找卡名
        card = next((c for c in cards if int(c['Card ID']) == card_id), None)
        if card:
            name = card['Card Name']
            print(f"  ID={card_id:4d} {name:30s} x{count}")
    
    return deck

def main():
    csv_path = "pokemon-tcg-ai-battle-challenge-strategy/EN_Card_Data.csv"
    cards = load_cards(csv_path)
    print(f"加载了 {len(cards)} 行卡牌数据\n")
    
    analyze_alakazam_line(cards)
    analyze_dudunsparce(cards)
    analyze_supporters(cards)
    analyze_high_damage_attacks(cards)
    
    deck = build_optimized_deck(cards)
    
    # 保存卡组
    output_path = "optimized_deck.csv"
    with open(output_path, 'w', encoding='utf-8') as f:
        for card_id in deck:
            f.write(f"{card_id}\n")
    print(f"\n卡组已保存到: {output_path}")

if __name__ == "__main__":
    main()
