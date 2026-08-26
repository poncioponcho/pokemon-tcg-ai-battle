#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deck_final_verify_v4.py — 1205シアノ FINAL 牌组部署后的独立复验
=================================================================
leg1 mirror : 现 main.py(FINAL deck, tuned 参数) vs main.py.bak-2026-08-09-tune
              (旧默认参数) 配原牌组 deck.csv.bak-2026-08-09。
              门: Wilson ci_lo > 0.5 且 invalid == 0。期望量级 ~0.6+。
leg2 vs_first: 现 main.py(FINAL) vs builtin_agent('first') (SAMPLE_DECK)。
              门: invalid == 0 且 wr 不显著低于旧默认补测值 0.3414。期望 ~0.35。
seed0=9000, n=8000 (对齐 deck_final_verify.jsonl 口径)。
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ['PTCG_NN_MODE'] = 'off'  # 必须先于 load_module

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 9000

FINAL_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
OLD_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv.bak-2026-08-09').read_text().splitlines() if l.strip()]
assert len(FINAL_DECK) == 60 and len(OLD_DECK) == 60

new = ar.load_module(PROJ / 'main.py')
import shutil
# [2026-08-11] 旧 main 副本放独立小目录并配旧牌组 deck.csv:
# _load_deck 按 __file__ 锚定找同目录 deck.csv, 缺了会打 stderr 脏字并回退内联牌组。
tmpd = EXP / 'runs' / '_verify_old_main'
tmpd.mkdir(parents=True, exist_ok=True)
shutil.copyfile(PROJ / 'main.py.bak-2026-08-09-tune', tmpd / 'main.py')
shutil.copyfile(PROJ / 'deck.csv.bak-2026-08-09', tmpd / 'deck.csv')
old = ar.load_module(tmpd / 'main.py')

# [v24.7] 卡池快败校验 (复刻 pack.sh:70-73): 闸前先拦 "卡 ID 不在卡池",
# 防止 ledger line58 式 "闸 PASS 但 pack 卡池拒" —— 白烧模拟还险些烧提交。
unknown = [c for c in set(FINAL_DECK)
           if c not in new._CARD_DB and c not in new._TRAINER_IDS]
if unknown:
    print(f'[card-pool] FAIL: 卡 ID 不在卡池中: {sorted(unknown)}', flush=True)
    with open(EXP / 'runs' / 'deck_final_verify_v4.json', 'w') as f:
        json.dump({'n': n, 'seed0': seed0,
                   'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                   'verdict': 'FAIL', 'gates': {'card_pool': False},
                   'unknown_cards': sorted(unknown)}, f, ensure_ascii=False, indent=2)
    sys.exit(1)
print('[card-pool] OK: FINAL_DECK 全部卡 ID 在卡池', flush=True)

out = {'n': n, 'seed0': seed0, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}

# ---- leg1: mirror (新 FINAL vs 旧默认+原牌组) ----
r = ar.run_arena(new.agent, old.agent, FINAL_DECK, OLD_DECK, n, seed0=seed0)
tot = r['wins'] + r['losses'] + r['draws']
wr = r['wins'] / tot if tot else 0.0
lo = ar.wilson_ci_lo(wr, tot)
out['mirror'] = {'wr': round(wr, 4), 'ci_lo': round(lo, 4), 'invalid': r['invalid'],
                 'avg_turns': r['avg_turns'], 'n': tot}
print(f'[leg1 mirror] wr={wr:.4f} ci_lo={lo:.4f} invalid={r["invalid"]} '
      f'avg_turns={r["avg_turns"]:.1f} (n={tot})', flush=True)
pass1 = lo > 0.5 and r['invalid'] == 0

# ---- leg2: vs_first (新 FINAL vs builtin first) ----
first = ar.builtin_agent('first')
r2 = ar.run_arena(new.agent, first, FINAL_DECK, ar.SAMPLE_DECK, n, seed0=seed0)
tot2 = r2['wins'] + r2['losses'] + r2['draws']
wr2 = r2['wins'] / tot2 if tot2 else 0.0
lo2 = ar.wilson_ci_lo(wr2, tot2)
out['vs_first'] = {'wr': round(wr2, 4), 'ci_lo': round(lo2, 4), 'invalid': r2['invalid'],
                   'avg_turns': r2['avg_turns'], 'n': tot2}
print(f'[leg2 vs_first] wr={wr2:.4f} ci_lo={lo2:.4f} invalid={r2["invalid"]} '
      f'avg_turns={r2["avg_turns"]:.1f} (n={tot2})', flush=True)
pass2 = r2['invalid'] == 0 and wr2 >= 0.3414 - 0.02  # 允许 2pp 噪声带

out['verdict'] = 'PASS' if (pass1 and pass2) else 'FAIL'
out['gates'] = {'mirror': pass1, 'vs_first': pass2}
print(f'verdict: {out["verdict"]} (mirror={pass1}, vs_first={pass2})', flush=True)

with open(EXP / 'runs' / 'deck_final_verify_v4.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
sys.exit(0 if out['verdict'] == 'PASS' else 1)
