"""meta_pool_build.py — 冻结精英对手池构建 + 结构 matchup 参考跑分

从 runs/meta_decks_raw.jsonl 取每 archetype 最高 rating 的代表牌组,
写入 experiments/arena_pool/meta/<arch>__rank<R>_<score>.csv,
然后跑参考 matchup: 当前 main.agent + deck.csv vs builtin('first') 驾驶各 meta 牌组。
(参考信号, 不进闸门 —— naive 代理驾驶精英牌组, 只回答"结构上我们被谁克制")

用法: /opt/homebrew/bin/python3 experiments/meta_pool_build.py [n] [seed0]
"""
import json, os, sys
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
EXP = PROJ / 'experiments'
POOL = EXP / 'arena_pool' / 'meta'
POOL.mkdir(parents=True, exist_ok=True)

os.environ['PTCG_NN_MODE'] = 'off'
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 9000

# ---- 选代表牌组 ----
best = {}
seen = set()
for line in open(EXP / 'runs' / 'meta_decks_raw.jsonl'):
    r = json.loads(line)
    for seat in (0, 1):
        if r['rated_seat'] != seat or r['score'] is None:
            continue
        arch = r['arch'][seat]
        team = r['teams'][seat] if seat < len(r['teams']) else '?'
        key = (team, tuple(sorted(r['decks'][seat])))
        if key in seen:
            continue
        seen.add(key)
        if arch not in best or r['score'] > best[arch]['score']:
            best[arch] = {'score': r['score'], 'team': team, 'deck': r['decks'][seat],
                          'rank': r.get('rank'), 'ep': r['ep']}

print(f'archetypes: {len(best)}')
pool = {}
for arch, b in sorted(best.items(), key=lambda x: -x[1]['score']):
    fname = f'{arch}__rank{b["rank"]}_{b["score"]:.0f}.csv'
    with open(POOL / fname, 'w') as f:
        f.write('\n'.join(str(c) for c in b['deck']) + '\n')
    pool[arch] = b['deck']
    print(f'  {arch:12s} rank{b["rank"]:<5} {b["score"]:7.1f} {b["team"][:20]:20s} → {fname}')

# ---- 参考 matchup ----
new = ar.load_module(PROJ / 'main.py')
OUR = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
first = ar.builtin_agent('first')

# 基线: vs SAMPLE_DECK (既有 vs_first 口径)
r = ar.run_arena(new.agent, first, OUR, ar.SAMPLE_DECK, n, seed0=seed0)
tot = r['wins'] + r['losses'] + r['draws']
print(f'\n[baseline SAMPLE_DECK ] wr={r["wins"]/tot:.4f} invalid={r["invalid"]} avg_turns={r["avg_turns"]:.1f}')

results = {}
for arch, deck in pool.items():
    rr = ar.run_arena(new.agent, first, OUR, deck, n, seed0=seed0)
    tot = rr['wins'] + rr['losses'] + rr['draws']
    wr = rr['wins'] / tot
    results[arch] = {'wr': round(wr, 4), 'invalid': rr['invalid'],
                     'avg_turns': round(rr['avg_turns'], 1),
                     'opp_rank': best[arch]['rank'], 'opp_score': best[arch]['score']}
    print(f'[vs {arch:12s}] wr={wr:.4f} invalid={rr["invalid"]} avg_turns={rr["avg_turns"]:.1f}')

out = {'n': n, 'seed0': seed0, 'agent': 'main(deck.csv) vs builtin-first piloting meta decks',
       'baseline_sample': None, 'results': results}
import time
out['ts'] = time.strftime('%Y-%m-%dT%H:%M:%S')
with open(EXP / 'runs' / 'meta_matchup_ref.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('\nwrote runs/meta_matchup_ref.json')
