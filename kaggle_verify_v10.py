# -*- coding: utf-8 -*-
"""
⚠️ [已废弃 STALE — 2026-08-09 标记] ⚠️
本脚本验证的是远古 v10 牌组 (111/223/741/742/743 胡地链时代)，
与当前 v24.5 Lucario 牌组 (678 等) 完全无关。运行它只会验证错误牌组，
产生虚假安全感。现役验证请用 experiments/deck_final_verify.py。
保留本文件仅作历史存档，请勿再粘贴到 Kaggle Notebook 使用。

Kaggle Notebook 验证脚本 — 检查 v10 deck 合法性
================================================
在 Kaggle Notebook (Linux) 中运行此脚本：
1. 挂载比赛数据源 (Pokemon TCG AI Battle Challenge)
2. 将此文件内容粘贴到 Notebook cell 中运行
3. 查看输出结果

验证内容：
- all_card_data() 返回的完整卡池中有多少张卡
- 111(スナバァ), 223(シロデスナex), 741/742/743(胡地链) 是否在卡池中
- 用 v10 deck 跑 battle_start 是否报错
"""

import json
import traceback

print("⚠️ 警告: kaggle_verify_v10.py 已废弃 — 验证的是 v10 旧牌组, 与当前 v24.5 无关!"
      " 现役验证请用 experiments/deck_final_verify.py")

# ============================================================
# Step 1: 获取完整卡池
# ============================================================
print("=" * 60)
print("Step 1: 获取完整卡池")
print("=" * 60)

cards = []
try:
    from kaggle_environments.envs.cabt.cg.api import all_card_data
    cards = all_card_data()
    print(f"✓ all_card_data() 返回 {len(cards)} 张卡")
except Exception as e:
    print(f"✗ kaggle_environments 导入失败: {e}")
    try:
        from cg.api import all_card_data
        cards = all_card_data()
        print(f"✓ cg.api.all_card_data() 返回 {len(cards)} 张卡")
    except Exception as e2:
        print(f"✗ cg.api 导入也失败: {e2}")
        # 尝试从比赛数据文件读取
        import os, csv
        cardpool_path = None
        for root, dirs, files in os.walk("/kaggle/input/"):
            for f in files:
                if "cardpool" in f.lower() or "card" in f.lower():
                    cardpool_path = os.path.join(root, f)
                    print(f"  发现文件: {cardpool_path}")
                    break
        if cardpool_path:
            with open(cardpool_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cards.append({"id": int(row.get("id", 0)), "name": row.get("name", "")})
            print(f"✓ 从 {cardpool_path} 读取到 {len(cards)} 张卡")

if not cards:
    print("✗ 无法获取卡池数据！请确保已挂载比赛数据源。")
else:
    # 获取所有卡 ID
    all_ids = set()
    for c in cards:
        cid = c.get("id", c.get("ID", None))
        if cid is not None:
            all_ids.add(int(cid))
    
    print(f"\n完整卡池: {len(all_ids)} 种不同 card_id")
    print(f"ID 范围: {min(all_ids)} ~ {max(all_ids)}")
    
    # ============================================================
    # Step 2: 检查 v10 deck 中的关键卡 ID
    # ============================================================
    print("\n" + "=" * 60)
    print("Step 2: 检查 v10 deck 关键卡 ID")
    print("=" * 60)
    
    check_ids = {
        111: "スナバァ (たね, 超系)",
        223: "シロデスナex (1進化, 超系, HP280, 160dmg)",
        331: "ゼルネアスex (たね, 超系, HP210)",
        554: "タブンネ (たね, 無系, HP100)",
        5:   "基本超エネルギー",
        9:   "特殊エネルギー(ブーメラン?)",
        741: "ケーシィ (胡地链-たね, M1S)",
        742: "ユンゲラー (胡地链-1進化, M1S)",
        743: "フーディン (胡地链-2進化, M1S)",
        245: "フーディン (SV8a, 别版)",
    }
    
    for cid, desc in check_ids.items():
        in_pool = cid in all_ids
        status = "✓ 在卡池中" if in_pool else "✗ 不在卡池中"
        print(f"  ID {cid:>4}: {status} — {desc}")
    
    # ============================================================
    # Step 3: 搜索スナバァ/シロデスナ/フーディン 的卡信息
    # ============================================================
    print("\n" + "=" * 60)
    print("Step 3: 搜索关键卡详细信息")
    print("=" * 60)
    
    search_keywords = ["スナバァ", "シロデスナ", "フーディン", "ケーシィ", "ユンゲラー",
                       "Sandycl", "Sandsla", "Alakazam", "Abra", "Kadabra"]
    
    for c in cards:
        name = str(c.get("name", ""))
        for kw in search_keywords:
            if kw.lower() in name.lower():
                cid = c.get("id", c.get("ID", "?"))
                hp = c.get("hp", "?")
                ctype = c.get("cardType", "?")
                etype = c.get("energyType", "?")
                evolves = c.get("evolvesFrom", c.get("evolves_from", "?"))
                print(f"  ID={cid}  name={name}  HP={hp}  cardType={ctype}  energyType={etype}  evolvesFrom={evolves}")
                
                # 打印攻击信息
                attacks = c.get("attacks", [])
                if attacks:
                    for atk in attacks:
                        aid = atk.get("id", "?")
                        aname = atk.get("name", "?")
                        dmg = atk.get("damage", "?")
                        cost = atk.get("cost", atk.get("energyCost", "?"))
                        desc = atk.get("description", atk.get("text", ""))
                        print(f"    招式[{aid}] {aname}  伤害={dmg}  成本={cost}  {desc[:60]}")
                break
    
    # ============================================================
    # Step 4: 尝试用 v10 deck 跑 battle_start
    # ============================================================
    print("\n" + "=" * 60)
    print("Step 4: 尝试用 v10 deck 跑 battle_start")
    print("=" * 60)
    
    v10_deck = [331]*4 + [111]*4 + [554]*4 + [223]*4 + [5]*40 + [9]*4
    
    print(f"v10 deck: {len(v10_deck)} 张")
    print(f"  不同 ID: {sorted(set(v10_deck))}")
    
    # 检查 deck 中所有 ID 是否在卡池中
    deck_ids = set(v10_deck)
    missing = deck_ids - all_ids
    if missing:
        print(f"\n⚠️  警告: 以下 ID 不在引擎卡池中: {sorted(missing)}")
        print("  如果强行提交, 引擎可能会报错或使用默认卡替换！")
    else:
        print(f"\n✓ 所有 deck ID 都在引擎卡池中")
    
    # 尝试实际跑对局
    print("\n--- 尝试 battle_start ---")
    try:
        from kaggle_environments import make
        
        # 用一个简单的随机 agent
        import random
        def test_agent(obs, config=None):
            if obs.get("select") is None:
                return v10_deck
            select = obs["select"]
            options = select.get("option", [])
            max_count = select.get("maxCount", 1)
            n = len(options)
            if n == 0:
                return []
            if max_count >= n:
                return list(range(n))
            return random.sample(range(n), min(max_count, n))
        
        # 尝试创建对局
        env = make("cabt", configuration={"decks": [v10_deck, v10_deck]})
        env.run([test_agent, test_agent])
        
        # 检查结果
        last_step = env.steps[-1]
        rewards = [s.reward for s in last_step]
        print(f"✓ battle_start 成功！对局完成")
        print(f"  结果: rewards={rewards}")
        print(f"  总步数: {len(env.steps)}")
        
        # 保存回放
        try:
            html = env.render(mode="html")
            with open("/kaggle/working/v10_test_battle.html", "w") as f:
                f.write(html)
            print(f"  回放已保存到 /kaggle/working/v10_test_battle.html")
        except Exception as e:
            print(f"  无法保存回放: {e}")
            
    except Exception as e:
        print(f"✗ battle_start 失败: {e}")
        traceback.print_exc()
        print("\n这通常意味着 deck 中有引擎不认识的卡 ID")
    
    # ============================================================
    # Step 5: 如果 v10 失败，尝试用 CardPool 合法卡组
    # ============================================================
    if missing:
        print("\n" + "=" * 60)
        print("Step 5: 回退方案 — 用 CardPool 合法卡测试")
        print("=" * 60)
        
        # 用原来 v9 的 deck (全部在 CardPool 中)
        v9_deck = [331]*4 + [554]*4 + [532]*4 + [157]*4 + [528]*4 + [77]*4 + [408]*4 + [5]*28 + [9]*4
        print(f"v9 deck: {len(v9_deck)} 张 (全部 CardPool 合法)")
        
        try:
            from kaggle_environments import make
            import random
            def v9_agent(obs, config=None):
                if obs.get("select") is None:
                    return v9_deck
                select = obs["select"]
                options = select.get("option", [])
                max_count = select.get("maxCount", 1)
                n = len(options)
                if n == 0:
                    return []
                if max_count >= n:
                    return list(range(n))
                return random.sample(range(n), max_count)
            
            env = make("cabt", configuration={"decks": [v9_deck, v9_deck]})
            env.run([v9_agent, v9_agent])
            last_step = env.steps[-1]
            rewards = [s.reward for s in last_step]
            print(f"✓ v9 deck battle_start 成功！rewards={rewards}")
            print(f"  结论: 引擎只接受 CardPool 中的 15 张卡")
            print(f"  建议: 回退到 v9 deck, 或在 Kaggle 上搜索超系强力卡")
        except Exception as e:
            print(f"✗ v9 deck 也失败: {e}")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
print("""
下一步建议:
1. 如果 111/223 在卡池中且 battle_start 成功 → 安全提交 v10
2. 如果 111/223 不在卡池中 → 需要在卡池内找替代超系强力卡
3. 如果想用胡地(741/742/743) → 同样需要先验证是否在卡池中
4. 可以用 all_card_data() 搜索所有超系(Psychic)高伤害卡
""")
