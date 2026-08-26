# -*- coding: utf-8 -*-
"""
deck.csv 生成器
================
从 CardPool.csv 中选取 60 张卡，生成 deck.csv（提交给 Kaggle 的牌组）。

================================================================
【PTCG 卡组规则（标准赛制）】
================================================================
  - 牌组恰好 60 张。
  - 同名卡最多 4 张；基础能量卡（cardType=5 BASIC_ENERGY）不限数量。
  - 实战还需保证有足够基础宝可梦以便开局上场，本生成器做简化处理。

================================================================
【CardPool.csv 格式】
================================================================
本脚本自动识别以下列名（大小写不敏感）：
  - 卡牌 ID 列：id / cardId / card_id
  - 卡名列   ：name / cardName
  - 卡类列   ：cardType / type
    （值为整数，与 cabt 引擎 api.CardType 一致：
       0 宝可梦 / 1 道具 / 2 工具 / 3 支援者 / 4 场馆 /
       5 基础能量 / 6 特殊能量）
若某列缺失，做合理假设（默认按宝可梦处理，同名≤4）。

================================================================
【用法】
================================================================
  python3 gen_deck.py                          # 默认读 CardPool.csv，输出 deck.csv
  python3 gen_deck.py --cardpool X --out deck.csv --seed 42
  python3 gen_deck.py --fallback               # 强制使用内置验证牌组

若 CardPool.csv 不存在，自动回退到内置的"已验证可跑通"牌组。
"""

import argparse
import csv
import os
import random
from collections import Counter

# ---- 卡类常量（与 cabt 引擎 api.CardType 一致）----
CARD_POKEMON = 0          # 宝可梦
CARD_BASIC_ENERGY = 5     # 基础能量（同名可超过 4 张）

# ---- 内置验证牌组（来自 cabt 引擎示例 cabt.py，保证合法、能跑通对局）----
# 该 deck 已被引擎自带测试 test_cabt.py 验证可完成对局，作为保底牌组。
FALLBACK_DECK = [
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5,   # 卡 ID 5（基础能量，可超 4 张）
    9, 9,
    77, 77, 77, 77,
    156, 156, 156, 156,
    157, 157, 157, 157,
    331, 331, 331, 331,
    408, 408, 408, 408,
    474, 474, 474, 474,
    528, 528, 528, 528,
    530, 530, 530, 530,
    532,
    554, 554, 554,
    576, 576, 576, 576,
    585, 585, 585, 585,
    630, 630, 630, 630,
]

# CardPool.csv 列名候选（大小写不敏感匹配）
ID_COLS = ("id", "cardid", "card_id")
NAME_COLS = ("name", "cardname")
TYPE_COLS = ("cardtype", "type")


def _find_col(fieldnames, candidates):
    """在 CSV 表头中查找候选列名（大小写不敏感）。"""
    for fn in fieldnames:
        if fn.strip().lower() in candidates:
            return fn
    return None


def load_cardpool(path):
    """读取 CardPool.csv，返回卡牌字典列表 [{id,name,cardType}, ...]。"""
    cards = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        id_col = _find_col(reader.fieldnames, ID_COLS)
        name_col = _find_col(reader.fieldnames, NAME_COLS)
        type_col = _find_col(reader.fieldnames, TYPE_COLS)
        if id_col is None:
            raise ValueError(f"CardPool.csv 找不到卡牌 ID 列（候选列名：{ID_COLS}）")
        for row in reader:
            try:
                cid = int(row[id_col])
            except (ValueError, TypeError):
                continue  # 跳过无法解析的行
            name = (row.get(name_col, "") or "").strip() or f"Card_{cid}"
            ctype = CARD_POKEMON
            if type_col and row.get(type_col, "").strip() != "":
                try:
                    ctype = int(row[type_col])
                except ValueError:
                    ctype = CARD_POKEMON
            cards.append({"id": cid, "name": name, "cardType": ctype})
    return cards


def build_deck(cards, deck_size=60, max_copy=4, seed=None):
    """从卡池中选 60 张卡。

    策略（简化版，只求合法）：
      - 基础能量卡（cardType==5）不限数量；
      - 其余卡每种最多 max_copy 张；
      - 先尽量放非能量卡，不足部分用基础能量补足；若没有能量卡，则循环取整池补足。
    """
    if seed is not None:
        random.seed(seed)
    if not cards:
        raise ValueError("卡池为空")

    energies = [c for c in cards if c["cardType"] == CARD_BASIC_ENERGY]
    others = [c for c in cards if c["cardType"] != CARD_BASIC_ENERGY]

    deck = []
    random.shuffle(others)
    for c in others:                       # 非能量卡每种尽量满编 max_copy 张
        take = max_copy
        deck.extend([c["id"]] * take)
        if len(deck) >= deck_size:
            break
    deck = deck[:deck_size]                # 截断到 60

    if len(deck) < deck_size:              # 不足用能量补足
        if energies:
            while len(deck) < deck_size:
                deck.append(random.choice(energies)["id"])
        else:                              # 无能量卡，循环用整池补足（仅作 fallback）
            pool = [c["id"] for c in cards]
            while len(deck) < deck_size:
                deck.append(random.choice(pool))
    return deck


def write_deck(deck, path):
    """把牌组写入 deck.csv（每行一个卡牌 ID）。"""
    with open(path, "w", encoding="utf-8") as f:
        for cid in deck:
            f.write(f"{cid}\n")


def main():
    ap = argparse.ArgumentParser(description="从 CardPool.csv 生成 60 张卡的 deck.csv")
    ap.add_argument("--cardpool", default="CardPool.csv", help="卡池 CSV 路径（默认 CardPool.csv）")
    ap.add_argument("--out", default="deck.csv", help="输出 deck.csv 路径（默认 deck.csv）")
    ap.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")
    ap.add_argument("--fallback", action="store_true", help="强制使用内置验证牌组")
    args = ap.parse_args()

    if args.fallback or not os.path.exists(args.cardpool):
        if not args.fallback:
            print(f"[警告] 找不到 {args.cardpool}，回退到内置验证牌组。")
        else:
            print("[信息] 使用 --fallback，采用内置验证牌组。")
        deck = FALLBACK_DECK
    else:
        cards = load_cardpool(args.cardpool)
        print(f"[信息] 从 {args.cardpool} 读取到 {len(cards)} 种卡。")
        deck = build_deck(cards, seed=args.seed)
        if len(deck) != 60:                # 兜底保护
            print(f"[警告] 生成 {len(deck)} 张（应为 60），改用内置验证牌组。")
            deck = FALLBACK_DECK
        else:
            # [fix 08-09] build_deck 洗牌取卡且不区分基础/进化宝可梦
            # (CardPool.csv 无阶段信息): 洗出的牌组可能基础宝可梦不足无法开局,
            # len!=60 兜底抓不到该情况, 显式提醒人工复核
            print("[提醒] 本生成器不区分基础/进化宝可梦：请人工确认牌组含足够"
                  "基础宝可梦再投入使用（hy3 审计 B4-2）。")

    write_deck(deck, args.out)
    cnt = Counter(deck)
    print(f"[完成] 已写入 {args.out}（{len(deck)} 张卡，{len(cnt)} 种）")
    print("[牌组统计] 卡ID:数量 =>", dict(cnt))


if __name__ == "__main__":
    main()
