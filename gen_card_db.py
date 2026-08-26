#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_card_db.py — 从官方卡牌 CSV 生成紧凑 _CARD_DB 数据 (开发期工具, 不进提交包)

用法:
    python3 gen_card_db.py card_db_data.py   # 生成数据模块
    python3 gen_card_db.py --inline main.py  # 直接内联进 main.py 的 _GEN_CARD_DATA 占位区

数据源: pokemon-tcg-ai-battle-challenge-strategy/JP_Card_Data_Cleaned.csv (1267 卡)
生成的每条记录格式: cid: (hp, type, weakness, rule, evolves_from, evolves_to, max_dmg)
  - hp: int, 非宝可梦为 0
  - type/weakness: 规范化的日文属性 ("草/炎/水/雷/超/闘/悪/鋼/無/龍"), 未知为 ""
  - rule: "" / "ex" / "mega_ex" (メガシンカex 归一化为 mega_ex)
  - evolves_from: 前阶卡 id, 无则 -1
  - evolves_to:   进化目标卡 id (由 evolves_from 反向推导), 无则 -1
  - max_dmg: 所有招式的基础伤害最大值 (无招式 0)
"""

import csv
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSV = os.path.join(_HERE, "pokemon-tcg-ai-battle-challenge-strategy",
                    "JP_Card_Data_Cleaned.csv")

_STAGE_POKEMON = {"ポケモン/たね", "ポケモン/1進化", "ポケモン/2進化"}
_TYPE_MAP = {
    "草": "草", "炎": "炎", "水": "水", "雷": "雷", "超": "超",
    "闘": "闘", "悪": "悪", "鋼": "鋼", "無": "無",
    "Dragon": "龍",
}


def _parse_dmg(dmg_str: str) -> int:
    """解析 ダメージ 列的基础伤害 (支持 60 / 60× / 60+ / -120 / n/a)。"""
    if not dmg_str or dmg_str.strip().lower() in ("n/a", "na"):
        return 0
    m = re.match(r"^(-?\d+)", dmg_str.strip())
    if not m:
        return 0
    return abs(int(m.group(1)))


def build_card_db() -> dict:
    if not os.path.exists(_CSV):
        # [fix 08-09] 原为裸 open: CSV 缺失时报错不知所云, --inline 会跟着崩
        raise SystemExit(f"[错误] 数据源 CSV 不存在: {_CSV}\n"
                         "请确认 pokemon-tcg-ai-battle-challenge-strategy/ 数据目录在当前项目内。")
    with open(_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # name -> id 反查 (用于进化前)
    name_to_id = {}
    for r in rows:
        cid = r.get("カード ID", "").strip()
        name = r.get("カード名", "").strip()
        if cid.isdigit() and name and name not in name_to_id:
            name_to_id[name] = int(cid)

    # 聚合: id -> (基本信息, 招式伤害列表)
    agg = {}
    for r in rows:
        cid_s = r.get("カード ID", "").strip()
        if not cid_s.isdigit():
            continue
        cid = int(cid_s)
        if cid not in agg:
            agg[cid] = (r, [])
        agg[cid][1].append(r)

    db = {}
    for cid, (first, all_rows) in agg.items():
        stage = first.get("ポケモンの進化の段階/エネルギー・トレーナーズの種類", "").strip()

        # 能量卡
        if stage in ("基本エネルギー", "特殊エネルギー"):
            db[cid] = {"is_energy": True}
            continue
        if stage not in _STAGE_POKEMON:
            continue  # 训练家卡不进 DB

        hp_s = first.get("HP", "").strip()
        hp = int(hp_s) if hp_s.isdigit() else 0

        typ = _TYPE_MAP.get(first.get("タイプ", "").strip(), "")
        weak_s = first.get("弱点", "").strip()
        weak = _TYPE_MAP.get(weak_s, "")

        rule_s = first.get("ルール", "").strip()
        if rule_s == "ex":
            rule = "ex"
        elif rule_s == "メガシンカex":
            rule = "mega_ex"
        else:
            rule = ""

        evo_name = first.get("進化前", "").strip()
        evolves_from = name_to_id.get(evo_name, -1)

        max_dmg = max((_parse_dmg(r.get("ダメージ", "")) for r in all_rows), default=0)

        db[cid] = (hp, typ, weak, rule, evolves_from, -1, max_dmg)

    # 反向映射: 子卡知道父卡 (evolves_from), 这里给父卡补 evolves_to (进化目标)
    evo_children: dict = {}
    for cid, v in db.items():
        if isinstance(v, dict):
            continue
        ef = v[4]
        if ef >= 0:
            evo_children.setdefault(ef, []).append(cid)
    # TODO(known-issue, 2026-08-09 hy3 审计确认): 多分支进化 (如イーブイ) 只保留
    # children[0], 其余分支丢失, 影响 evolve-bonus 打分精度; 消费方 main.py 按
    # 单 cid 使用 evolves_to, 改列表需同步改消费方, 暂记待办不改动行为。
    for parent, children in evo_children.items():
        if parent in db:
            db[parent] = (db[parent][0], db[parent][1], db[parent][2],
                          db[parent][3], db[parent][4], children[0], db[parent][6])

    return db


def _emit_dict(db: dict) -> str:
    lines = [
        "# -*- coding: utf-8 -*-",
        "# 由 gen_card_db.py 从 JP_Card_Data_Cleaned.csv 自动生成, 请勿手改",
        "# 记录格式: cid: (hp, type, weakness, rule, evolves_from, evolves_to, max_dmg)",
        "_GEN_CARD_DATA = {",
    ]
    for cid in sorted(db):
        v = db[cid]
        if isinstance(v, dict):  # 能量卡
            lines.append(f"    {cid}: {{'is_energy': True}},")
        else:
            hp, typ, weak, rule, evo_f, evo_t, dmg = v
            lines.append(
                f"    {cid}: ({hp}, {typ!r}, {weak!r}, {rule!r}, {evo_f}, {evo_t}, {dmg}),")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    db = build_card_db()
    n_energy = sum(1 for v in db.values() if isinstance(v, dict))
    print(f"总卡牌 {len(db)} 张 (能量 {n_energy}, 宝可梦 {len(db) - n_energy})")

    # 校验牌组卡都在 DB 内 (从 deck.csv 读取, 避免 import main 循环依赖)
    deck_ids = []
    deck_csv = os.path.join(_HERE, "deck.csv")
    if os.path.exists(deck_csv):
        deck_ids = [int(l.strip()) for l in open(deck_csv, encoding="utf-8") if l.strip()]
    for cid in set(deck_ids):
        if cid not in db:
            print(f"  [警告] 牌组卡 {cid} 不在 CSV 中!")

    if len(sys.argv) > 1 and sys.argv[1] == "--inline":
        target = sys.argv[2] if len(sys.argv) > 2 else "main.py"
        src = open(target, encoding="utf-8").read()
        marker_start = "# ==== GEN: _GEN_CARD_DATA BEGIN ===="
        marker_end = "# ==== GEN: _GEN_CARD_DATA END ===="
        if marker_start not in src or marker_end not in src:
            print("main.py 缺少生成区标记, 拒绝内联", file=sys.stderr)
            sys.exit(1)
        head, rest = src.split(marker_start, 1)
        _, tail = rest.split(marker_end, 1)
        new = (head + marker_start + "\n" + _emit_dict(db) + marker_end + tail)
        open(target, "w", encoding="utf-8").write(new)
        print(f"已内联 {len(db)} 条记录到 {target}")
    else:
        out = sys.argv[1] if len(sys.argv) > 1 else "card_db_data.py"
        open(out, "w", encoding="utf-8").write(_emit_dict(db))
        print(f"已生成 {out} ({len(db)} 条)")


if __name__ == "__main__":
    main()
