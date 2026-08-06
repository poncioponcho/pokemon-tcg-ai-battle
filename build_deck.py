# -*- coding: utf-8 -*-
"""
优化卡组构建脚本
================
基于官方卡牌数据 CSV，构建针对 Alakazam + Powerful Hand 策略的优化卡组。

策略核心：
  1. 使用 MEG 进化链：Abra (741) → Kadabra (742) → Alakazam (743)
  2. Kadabra 和 Alakazam 都有 Psychic Draw 能力（进化时抽牌）
  3. Alakazam 的 Powerful Hand 攻击：2×手牌数伤害指示物
  4. 配合抽牌支援者（Amarys/Cheren）和 Dudunsparce 的 Run Away Draw
  5. 保持手牌数量，最大化 Powerful Hand 伤害
"""

import csv
from collections import Counter

def load_cards(csv_path):
    """读取卡牌数据"""
    cards = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cards.append(row)
    return cards

def build_deck(cards):
    """构建优化卡组（60 张）"""
    deck = []
    
    # =========================================================================
    # 1. 宝可梦（20 张）
    # =========================================================================
    
    # Abra (741): 基础形态，HP 50，攻击 Teleportation Attack（10 + 换位）
    # 4 张，保证开局能上手
    deck.extend([741] * 4)
    
    # Kadabra (742): Stage 1，HP 80
    # 能力：Psychic Draw（进化时抽 2 卡）
    # 攻击：Super Psy Bolt（30 伤害）
    # 3 张
    deck.extend([742] * 3)
    
    # Alakazam (743): Stage 2，HP 140（主力）
    # 能力：Psychic Draw（进化时抽 3 卡）
    # 攻击：Powerful Hand（2×手牌数伤害指示物）
    # 3 张
    deck.extend([743] * 3)
    
    # Dunsparce (65): 基础形态，HP 60
    # 2 张，用于进化成 Dudunsparce
    deck.extend([65] * 2)
    
    # Dudunsparce (66): Stage 1，HP 140
    # 能力：Run Away Draw（抽 3 卡 + 洗牌回牌库）
    # 攻击：Land Crush（90 伤害）
    # 2 张
    deck.extend([66] * 2)
    
    # 备用打手：Tatsugiri (122) - 能力 Attract Customers（检索支援者）
    # 或者选择其他 Psychic 属性宝可梦
    # 搜索 Psychic 属性基础宝可梦
    psychic_basics = [c for c in cards 
                      if c['Type'] == '{P}' 
                      and 'Basic Pokémon' in c.get('Stage (Pokémon)/Type (Energy and Trainer)', '')
                      and 'Abra' not in c['Card Name']
                      and 'Dunsparce' not in c['Card Name']]
    
    if psychic_basics:
        # 选择 HP 较高的基础宝可梦
        psychic_basics.sort(key=lambda x: int(x['HP']) if x['HP'] else 0, reverse=True)
        backup_pokemon = psychic_basics[0]
        deck.extend([int(backup_pokemon['Card ID'])] * 2)
        print(f"备用打手: {backup_pokemon['Card Name']} (ID={backup_pokemon['Card ID']}, HP={backup_pokemon['HP']})")
    
    # 其他基础宝可梦（保证开局有足够基础宝可梦）
    # 搜索 HP >= 60 的基础宝可梦
    other_basics = [c for c in cards 
                    if 'Basic Pokémon' in c.get('Stage (Pokémon)/Type (Energy and Trainer)', '')
                    and int(c['HP']) >= 60
                    and c['Card ID'] not in [str(x) for x in deck]]
    
    if other_basics:
        other_basics.sort(key=lambda x: int(x['HP']) if x['HP'] else 0, reverse=True)
        # 选择 2 种不同的基础宝可梦，各 2 张
        for basic in other_basics[:2]:
            deck.extend([int(basic['Card ID'])] * 2)
            print(f"其他基础: {basic['Card Name']} (ID={basic['Card ID']}, HP={basic['HP']})")
    
    pokemon_count = len(deck)
    print(f"\n宝可梦: {pokemon_count} 张")
    
    # =========================================================================
    # 2. 能量（18 张）
    # =========================================================================
    
    # Basic Psychic Energy (5): 15 张
    deck.extend([5] * 15)
    
    # 特殊能量：Telepath Psychic Energy (19)
    # 效果：贴给 Psychic 宝可梦时，从牌库搜索 2 张基础 Psychic 宝可梦放到备战区
    # 3 张
    deck.extend([19] * 3)
    
    energy_count = len(deck) - pokemon_count
    print(f"能量: {energy_count} 张")
    
    # =========================================================================
    # 3. 训练家卡（22 张）
    # =========================================================================
    
    # 抽牌支援者
    # Amarys (1207): 抽 4 卡（回合结束手牌≥5 要弃牌）
    deck.extend([1207] * 2)
    
    # Cheren (1224): 抽 3 卡（简单直接）
    deck.extend([1224] * 2)
    
    # Urbain (1236): 抽 3 卡
    deck.extend([1236] * 2)
    
    # 检索道具
    # Pokégear 3.0 (1122): 查看牌库顶 7 张，检索支援者
    deck.extend([1122] * 2)
    
    # Ultra Ball: 搜索宝可梦（需要找到 ID）
    ultra_ball = [c for c in cards if 'Ultra Ball' in c['Card Name']]
    if ultra_ball:
        deck.extend([int(ultra_ball[0]['Card ID'])] * 2)
    
    # 换位道具
    # Boss's Orders (1182): 换位对方宝可梦
    deck.extend([1182] * 2)
    
    # 其他道具
    # 搜索强力道具
    item_cards = [c for c in cards 
                  if c.get('Stage (Pokémon)/Type (Energy and Trainer)') == 'Item'
                  and c['Card ID'] not in [str(x) for x in deck]]
    
    # 选择一些通用道具
    for item in item_cards[:4]:
        deck.extend([int(item['Card ID'])] * 1)
        print(f"道具: {item['Card Name']} (ID={item['Card ID']})")
    
    trainer_count = len(deck) - pokemon_count - energy_count
    print(f"训练家: {trainer_count} 张")
    
    # =========================================================================
    # 4. 补足到 60 张
    # =========================================================================
    
    if len(deck) < 60:
        # 用 Psychic 能量补足
        while len(deck) < 60:
            deck.append(5)
    elif len(deck) > 60:
        deck = deck[:60]
    
    return deck

def print_deck_summary(deck, cards):
    """打印卡组统计"""
    print("\n" + "=" * 60)
    print("卡组统计")
    print("=" * 60)
    
    cnt = Counter(deck)
    
    # 分类统计
    pokemon_cards = []
    energy_cards = []
    trainer_cards = []
    
    for card_id, count in sorted(cnt.items()):
        card = next((c for c in cards if int(c['Card ID']) == card_id), None)
        if card:
            name = card['Card Name']
            stage = card.get('Stage (Pokémon)/Type (Energy and Trainer)', '')
            
            if 'Pokémon' in stage:
                pokemon_cards.append((card_id, name, count, stage))
            elif 'Energy' in stage:
                energy_cards.append((card_id, name, count, stage))
            else:
                trainer_cards.append((card_id, name, count, stage))
    
    print(f"\n【宝可梦】({sum(x[2] for x in pokemon_cards)} 张)")
    for card_id, name, count, stage in pokemon_cards:
        hp = next((c['HP'] for c in cards if int(c['Card ID']) == card_id), '?')
        print(f"  ID={card_id:4d} {name:30s} x{count}  HP={hp}")
    
    print(f"\n【能量】({sum(x[2] for x in energy_cards)} 张)")
    for card_id, name, count, stage in energy_cards:
        print(f"  ID={card_id:4d} {name:30s} x{count}")
    
    print(f"\n【训练家】({sum(x[2] for x in trainer_cards)} 张)")
    for card_id, name, count, stage in trainer_cards:
        print(f"  ID={card_id:4d} {name:30s} x{count}")
    
    print(f"\n总计: {len(deck)} 张")

def main():
    csv_path = "pokemon-tcg-ai-battle-challenge-strategy/EN_Card_Data.csv"
    cards = load_cards(csv_path)
    
    print("构建优化卡组...")
    deck = build_deck(cards)
    
    print_deck_summary(deck, cards)
    
    # 保存卡组
    output_path = "optimized_deck.csv"
    with open(output_path, 'w', encoding='utf-8') as f:
        for card_id in deck:
            f.write(f"{card_id}\n")
    
    print(f"\n卡组已保存到: {output_path}")
    
    # 验证
    print("\n验证卡组合法性:")
    print(f"  总张数: {len(deck)} (应为 60)")
    
    # 检查同名卡数量
    cnt = Counter(deck)
    for card_id, count in cnt.items():
        if count > 4:
            card = next((c for c in cards if int(c['Card ID']) == card_id), None)
            if card and 'Basic Energy' not in card.get('Stage (Pokémon)/Type (Energy and Trainer)', ''):
                print(f"  警告: {card['Card Name']} (ID={card_id}) 有 {count} 张（超过 4 张限制）")

if __name__ == "__main__":
    main()
