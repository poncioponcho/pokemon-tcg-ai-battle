#!/usr/bin/env python3
"""新牌组独立终验 —— 种子集 9000（与 deck_search 筛选 seed0=1000 / 确认 seed0=5000 完全错开）

leg1: rules(final) vs rules(deck.csv 原牌组) 配对镜像 n=8000 seed0=9000
leg2: rules(final) vs first(SAMPLE) n=8000 seed0=9000
通过标准: leg1 mirror 的 Wilson 下界 > 0.5 且两条腿 invalid==0
产物: experiments/runs/deck_final_verify.jsonl
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'experiments'))
import arena_runner as ar  # noqa: E402

N = 8000
SEED0 = 9000


def load_final_deck():
    final = None
    for line in open(ROOT / 'experiments' / 'runs' / 'deck_search.jsonl'):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get('ev') == 'final':
            final = r
    assert final, 'deck_search.jsonl 无 final 事件'
    return final['deck']


def stats(r):
    tot = r['wins'] + r['losses'] + r['draws']
    wr = r['wins'] / tot if tot else 0.0
    return wr, ar.wilson_ci_lo(wr, tot), tot, r.get('invalid', 0)


def main():
    new = load_final_deck()
    # round2 模式: 撤销第三轮置换 (-673+1205)，得到只含 main.py 已知卡的倒数第二版牌组
    if len(sys.argv) > 1 and sys.argv[1] == 'round2':
        new = sorted(c for c in new if c != 1205) + [673]
        tag = 'round2(-235+678,-676+677)'
    else:
        tag = 'final'
    old = sorted(int(l) for l in open(ROOT / 'deck.csv') if l.strip())
    assert len(new) == 60 and len(old) == 60, 'deck 长度异常'
    assert new != old, 'final 牌组与原牌组相同？'
    print(f'=== deck_final_verify[{tag}] start: n={N} seed0={SEED0} ===', flush=True)

    rules = ar.load_opponent('v23_2_rules')
    first = ar.builtin_agent('first')

    t0 = time.time()
    r1 = ar.run_arena(rules, rules, new, old, N, seed0=SEED0)
    wr1, lo1, tot1, inv1 = stats(r1)
    print(f'[leg1 mirror] rules(NEW) vs rules(ORIG) n={tot1} wr={wr1:.4f} '
          f'ci_lo={lo1:.4f} invalid={inv1} ({time.time() - t0:.0f}s)', flush=True)

    t1 = time.time()
    r2 = ar.run_arena(rules, first, new, ar.SAMPLE_DECK, N, seed0=SEED0)
    wr2, lo2, tot2, inv2 = stats(r2)
    print(f'[leg2 vsfirst] rules(NEW) vs first(SAMPLE) n={tot2} wr={wr2:.4f} '
          f'ci_lo={lo2:.4f} invalid={inv2} ({time.time() - t1:.0f}s)', flush=True)

    verdict = 'PASS' if (lo1 > 0.5 and inv1 == 0 and inv2 == 0) else 'FAIL'
    print(f'verdict: {verdict}', flush=True)

    out = {'ev': 'deck_final_verify', 'mode': tag, 'ts': time.time(), 'n': N, 'seed0': SEED0,
           'mirror_wr': round(wr1, 4), 'mirror_ci_lo': round(lo1, 4), 'mirror_invalid': inv1,
           'vs_first_wr': round(wr2, 4), 'vs_first_ci_lo': round(lo2, 4), 'vs_first_invalid': inv2,
           'verdict': verdict, 'deck': new}
    with open(ROOT / 'experiments' / 'runs' / 'deck_final_verify.jsonl', 'a') as f:
        f.write(json.dumps(out, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
