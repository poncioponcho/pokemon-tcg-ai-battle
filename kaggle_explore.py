# -*- coding: utf-8 -*-
"""
Kaggle Notebook 探索脚本
========================
在 Kaggle Notebook（Linux 环境）中运行此脚本，用于：

1. 读取完整 CardPool（通过引擎 API all_card_data()）
2. 搜索 Alakazam / Dudunsparce / Abra / Kadabra 等关键卡 ID
3. 自动构建胡地卡组 alakazam_deck.csv
4. 用 kaggle_environments 跑测试对局

使用方法：
  1. 在 Kaggle 上创建 Notebook，选择比赛数据源（Pokemon TCG AI Battle Challenge）
  2. 把本文件内容粘贴到一个 cell 中运行
  3. 或直接上传本文件到 Notebook，然后 import

注意：本脚本依赖 kaggle_environments 和 libcg.so，只能在 Kaggle Linux 环境运行。
macOS 本地无法加载 libcg.so，会报错。
"""

import json
import os

# ==========================================================================
# 第一步：读取完整卡池（通过引擎 API）
# ==========================================================================

def get_all_cards():
    """使用引擎 API 获取所有卡牌元数据。

    返回 list[dict]，每个 dict 含：
      - id: 卡牌 ID
      - name: 卡名（如 "Abra", "Alakazam"）
      - cardType: 卡类（0=宝可梦, 1=道具, 2=工具, 3=支援者, 4=场馆, 5=基础能量, 6=特殊能量）
      - hp: 宝可梦 HP（非宝可梦为 None）
      - energyType: 能量属性（0=Colorless, 1=Grass, ..., 5=Psychic, ...）
      - evolvesFrom: 进化来源（如果有）
      - attacks: 攻击列表（如果有）
    """
    try:
        # 尝试从 kaggle_environments 导入引擎
        from kaggle_environments.envs.cabt.cg.api import all_card_data
        cards = all_card_data()
        print(f"[成功] 从引擎 API 获取到 {len(cards)} 张卡")
        return cards
    except ImportError:
        pass

    # 备选：尝试直接从 cg 模块导入
    try:
        from cg.api import all_card_data
        cards = all_card_data()
        print(f"[成功] 从 cg.api 获取到 {len(cards)} 张卡")
        return cards
    except ImportError:
        pass

    # 备选：从比赛数据文件读取
    cardpool_path = "/kaggle/input/pokemon-tcg-ai-battle/CardPool.csv"
    if not os.path.exists(cardpool_path):
        # 搜索可能的路径
        for root, dirs, files in os.walk("/kaggle/input/"):
            for f in files:
                if "cardpool" in f.lower() or "card_pool" in f.lower():
                    cardpool_path = os.path.join(root, f)
                    break

    if os.path.exists(cardpool_path):
        import csv
        cards = []
        with open(cardpool_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cards.append({
                    "id": int(row.get("id", 0)),
                    "name": row.get("name", ""),
                    "cardType": int(row.get("cardType", 0)),
                    "hp": int(row.get("hp", 0)) if row.get("hp") else None,
                    "energyType": int(row.get("energyType", 0)) if row.get("energyType") else None,
                })
        print(f"[成功] 从 {cardpool_path} 读取到 {len(cards)} 张卡")
        return cards

    print("[错误] 无法获取卡池数据。请确保已挂载比赛数据源。")
    return []


# ==========================================================================
# 第二步：搜索关键卡（Alakazam 进化链 + Dudunsparce）
# ==========================================================================

def search_cards(cards, keywords):
    """按关键词搜索卡牌（不区分大小写）。

    Args:
        cards: 卡牌列表
        keywords: 关键词列表，如 ["alakazam", "abra", "kadabra"]

    Returns:
        匹配的卡牌列表
    """
    results = []
    for card in cards:
        name = str(card.get("name", "")).lower()
        for kw in keywords:
            if kw.lower() in name:
                results.append(card)
                break
    return results


def find_alakazam_line(cards):
    """搜索胡地进化链：Abra → Kadabra → Alakazam。

    返回 dict:
      {
        "abra": [card, ...],
        "kadabra": [card, ...],
        "alakazam": [card, ...],
      }
    """
    line = {
        "abra": search_cards(cards, ["abra"]),
        "kadabra": search_cards(cards, ["kadabra"]),
        "alakazam": search_cards(cards, ["alakazam"]),
    }

    print("\n=== 胡地进化链搜索结果 ===")
    for stage, found in line.items():
        print(f"\n{stage.upper()} ({len(found)} 张):")
        for c in found:
            cid = c.get("id", "?")
            name = c.get("name", "?")
            hp = c.get("hp", "?")
            etype = c.get("energyType", "?")
            ctype = c.get("cardType", "?")
            print(f"  ID={cid}  name={name}  HP={hp}  energyType={etype}  cardType={ctype}")

            # 打印攻击信息（如果有）
            attacks = c.get("attacks", [])
            if attacks:
                print(f"    攻击:")
                for atk in attacks:
                    aid = atk.get("id", "?")
                    aname = atk.get("name", "?")
                    dmg = atk.get("damage", "?")
                    desc = atk.get("description", "")
                    print(f"      [{aid}] {aname}  伤害={dmg}  {desc}")

    return line


def find_dudunsparce(cards):
    """搜索 Dudunsparce（大钢蛇/双面兽）。"""
    results = search_cards(cards, ["dudunsparce", "dunsparce"])
    print("\n=== Dudunsparce 搜索结果 ===")
    for c in results:
        print(f"  ID={c.get('id')}  name={c.get('name')}  HP={c.get('hp')}")
    return results


def find_energy_cards(cards):
    """搜索基础能量卡。"""
    energies = [c for c in cards if c.get("cardType") == 5]  # BASIC_ENERGY
    print(f"\n=== 基础能量卡 ({len(energies)} 张) ===")
    for c in energies:
        etype = c.get("energyType", "?")
        etype_name = {
            0: "Colorless", 1: "Grass", 2: "Fire", 3: "Water",
            4: "Lightning", 5: "Psychic", 6: "Fighting",
            7: "Darkness", 8: "Metal", 9: "Dragon",
        }.get(etype, "?")
        print(f"  ID={c.get('id')}  name={c.get('name')}  type={etype_name}")
    return energies


def find_supporter_cards(cards):
    """搜索支援者卡（抽牌/检索类）。"""
    supporters = [c for c in cards if c.get("cardType") == 3]  # SUPPORTER
    print(f"\n=== 支援者卡 ({len(supporters)} 张) ===")
    for c in supporters[:20]:  # 只打印前 20 张
        print(f"  ID={c.get('id')}  name={c.get('name')}")
    if len(supporters) > 20:
        print(f"  ... 还有 {len(supporters) - 20} 张")
    return supporters


# ==========================================================================
# 第三步：构建胡地卡组
# ==========================================================================

def build_alakazam_deck(cards, alakazam_line):
    """构建胡地卡组（60 张）。

    策略：
      - Abra x4（基础形态，开局可上场）
      - Kadabra x3（一阶进化）
      - Alakazam x3（二阶进化，主力）
      - Dudunsparce x2（如果有，备用打手）
      - Psychic 能量 x12（胡地需要 Psychic 能量）
      - Colorless 能量 x4
      - 支援者卡 x8（抽牌/检索）
      - 道具卡 x4（检索/回复）
      - 工具卡 x4
      - 剩余用其他卡补足

    总计 60 张。同卡最多 4 张（基础能量除外）。
    """
    deck = []
    max_copy = 4

    # ---- 胡地进化链 ----
    abra = alakazam_line.get("abra", [])
    kadabra = alakazam_line.get("kadabra", [])
    alakazam = alakazam_line.get("alakazam", [])

    if abra:
        deck.extend([abra[0]["id"]] * min(4, max_copy))  # Abra x4
    if kadabra:
        deck.extend([kadabra[0]["id"]] * min(3, max_copy))  # Kadabra x3
    if alakazam:
        deck.extend([alakazam[0]["id"]] * min(3, max_copy))  # Alakazam x3

    # ---- Dudunsparce（如果有）----
    dudunsparce = find_dudunsparce(cards)
    if dudunsparce:
        deck.extend([dudunsparce[0]["id"]] * min(2, max_copy))

    # ---- 基础能量 ----
    energies = find_energy_cards(cards)
    psychic_energy = [e for e in energies if e.get("energyType") == 5]  # PSYCHIC
    colorless_energy = [e for e in energies if e.get("energyType") == 0]  # COLORLESS

    if psychic_energy:
        deck.extend([psychic_energy[0]["id"]] * 12)  # Psychic x12
    elif energies:
        deck.extend([energies[0]["id"]] * 12)  # 退而求其次

    if colorless_energy:
        deck.extend([colorless_energy[0]["id"]] * 4)  # Colorless x4

    # ---- 支援者卡 ----
    supporters = find_supporter_cards(cards)
    for s in supporters[:8]:
        need = max_copy
        current_count = deck.count(s["id"])
        take = min(1, max_copy - current_count)
        deck.extend([s["id"]] * take)
        if len(deck) >= 52:
            break

    # ---- 补足到 60 张 ----
    # 用基础能量或已有卡补足
    if len(deck) < 60:
        fill_card = psychic_energy[0]["id"] if psychic_energy else (energies[0]["id"] if energies else (abra[0]["id"] if abra else 5))
        while len(deck) < 60:
            deck.append(fill_card)
    elif len(deck) > 60:
        deck = deck[:60]

    return deck


def save_deck(deck, path="alakazam_deck.csv"):
    """保存卡组到 CSV 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        for cid in deck:
            f.write(f"{cid}\n")
    print(f"\n[完成] 卡组已保存到 {path}（{len(deck)} 张）")

    # 统计
    from collections import Counter
    cnt = Counter(deck)
    print("[牌组统计] 卡ID:数量 =>", dict(cnt))


# ==========================================================================
# 第四步：测试对局（用 kaggle_environments）
# ==========================================================================

def run_test_battle(deck, agent_func=None, num_games=3):
    """用 kaggle_environments 跑测试对局。

    Args:
        deck: 60 张卡的列表
        agent_func: agent 函数（默认用随机 agent）
        num_games: 对局数
    """
    try:
        from kaggle_environments import make
    except ImportError:
        print("[跳过] kaggle_environments 未安装，无法跑测试对局")
        return

    if agent_func is None:
        import random
        def agent_func(obs, config=None):
            if obs.get("select") is None:
                return deck
            select = obs["select"]
            n = len(select["option"])
            if n == 0:
                return []
            # [审计-L5] maxCount 可能大于选项数, 需夹取防止 random.sample 抛 ValueError
            return random.sample(range(n), min(select["maxCount"], n))

    wins = 0
    losses = 0
    draws = 0

    for i in range(num_games):
        env = make("cabt", configuration={"decks": [deck, deck]})
        env.run([agent_func, agent_func])

        # 检查结果
        for s in env.steps[-1]:
            reward = s.reward
            if reward > 0:
                wins += 1
            elif reward < 0:
                losses += 1
            else:
                draws += 1

        print(f"  对局 {i+1}/{num_games} 完成")

    print(f"\n=== 测试结果 ({num_games} 场) ===")
    print(f"  胜: {wins}  负: {losses}  平: {draws}")

    # 保存可视化
    try:
        html = env.render(mode="html")
        with open("battle_replay.html", "w") as f:
            f.write(html)
        print("  回放已保存到 battle_replay.html")
    except Exception as e:
        print(f"  无法保存回放: {e}")


# ==========================================================================
# 第五步：导出 CardPool.csv（供本地使用）
# ==========================================================================

def export_cardpool(cards, path="CardPool_full.csv"):
    """导出完整卡池到 CSV（供本地使用）。"""
    import csv
    if not cards:
        print("[跳过] 卡池为空")
        return

    # 收集所有字段
    fieldnames = set()
    for c in cards:
        fieldnames.update(c.keys())
    fieldnames = sorted(fieldnames)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in cards:
            writer.writerow(c)

    print(f"[完成] 完整卡池已导出到 {path}（{len(cards)} 张卡）")


# ==========================================================================
# 主函数：一键执行全部探索步骤
# ==========================================================================

def main():
    print("=" * 60)
    print("Pokemon TCG AI Battle Challenge —— Kaggle 探索脚本")
    print("=" * 60)

    # Step 1: 获取卡池
    print("\n>>> Step 1: 获取完整卡池...")
    cards = get_all_cards()

    # Step 2: 搜索关键卡
    print("\n>>> Step 2: 搜索胡地进化链...")
    alakazam_line = find_alakazam_line(cards)

    print("\n>>> Step 2b: 搜索基础能量卡...")
    energies = find_energy_cards(cards)

    print("\n>>> Step 2c: 搜索支援者卡...")
    supporters = find_supporter_cards(cards)

    # Step 3: 构建卡组
    print("\n>>> Step 3: 构建胡地卡组...")
    deck = build_alakazam_deck(cards, alakazam_line)
    save_deck(deck, "alakazam_deck.csv")

    # Step 4: 导出卡池
    print("\n>>> Step 4: 导出完整卡池...")
    export_cardpool(cards, "CardPool_full.csv")

    # Step 5: 测试对局
    print("\n>>> Step 5: 运行测试对局...")
    run_test_battle(deck, num_games=3)

    print("\n" + "=" * 60)
    print("探索完成！")
    print(f"  - 完整卡池: CardPool_full.csv")
    print(f"  - 胡地卡组: alakazam_deck.csv")
    print(f"  - 对局回放: battle_replay.html")
    print("=" * 60)


if __name__ == "__main__":
    main()
