"""meta_deck_extract.py — 从回放档案提取当前 meta 精英牌组 (v0 冻结对手池原料)

机制 (credit: 官方 meta 笔记本同款): steps[1][seat].action = 该座位完整 60 卡牌组。
扫描 all_replays.jsonl.zst 前 MAX_LINES 行 (档案新→旧, 覆盖最近 ~2 天 ≈ 当前 meta),
join episode_catalog (rank/score/team), 按签名卡分类 archetype,
每局两队牌组各归因: catalog 的 rating 只归到被抓取队 (team_name 匹配 TeamNames[seat])。

产物: experiments/runs/meta_decks_raw.jsonl  (每行一局: 两座位牌组+胜负+归因rating)
用法: nohup /opt/homebrew/bin/python3 experiments/meta_deck_extract.py > experiments/runs/meta_deck_extract.log 2>&1 &
"""
import json, os, shutil, subprocess, sys
from collections import Counter

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(PROJ, 'inference/leaderboard_replay/archive/all_replays.jsonl.zst')
CATALOG = os.path.join(PROJ, 'inference/leaderboard_replay/episode_catalog.jsonl')
OUT = os.path.join(PROJ, 'experiments/runs/meta_decks_raw.jsonl')
MAX_LINES = 4500

ARCHETYPES = [  # (名字, 签名卡 id 集合)
    ('Lucario', {678}), ('Grimmsnarl', {648}), ('Alakazam', {743}),
    ('Dragapult', {121}), ('Archaludon', {190}), ('Gardevoir', {747}),
    ('Charizard', {790, 928}), ('Gengar', {772}), ('Crustle', {345}),
    ('Cornerstone', {117}), ('Gholdengo', {700, 191}),
]

def classify(deck):
    s = set(deck)
    for name, sig in ARCHETYPES:
        if s & sig:
            return name
    return 'other'

def main():
    cat = {}
    with open(CATALOG) as f:
        for line in f:
            e = json.loads(line)
            cat[str(e['episode_id'])] = e
    zstd = shutil.which('zstd')
    if zstd is None:
        raise SystemExit('zstd executable not found on PATH')
    proc = subprocess.Popen(  # noqa: S603 - fixed executable and flags
        [zstd, '-dc', ARCHIVE], stdout=subprocess.PIPE,
        text=True, bufsize=1 << 20)
    if proc.stdout is None:
        proc.kill()
        raise RuntimeError('failed to open zstd stdout pipe')
    n = kept = 0
    arch_counter = Counter()
    stopped_early = False
    with open(OUT, 'w') as out:
        for line in proc.stdout:
            n += 1
            if n > MAX_LINES:
                stopped_early = True
                break
            if n % 500 == 0:
                print(f'...{n} kept={kept}', flush=True)
            try:
                ep = json.loads(line)
                rj = ep.get('raw_json')
                if isinstance(rj, str):
                    rj = json.loads(rj)
                steps = rj.get('steps') or []
                decks = []
                for seat in range(2):
                    a = steps[1][seat].get('action') if len(steps) > 1 and isinstance(steps[1], list) else None
                    if isinstance(a, list) and len(a) == 60 and all(isinstance(x, int) for x in a):
                        decks.append([int(x) for x in a])
                if len(decks) != 2:
                    continue
                ep_id = str(ep.get('episode_id'))
                teams = (rj.get('info') or {}).get('TeamNames') or []
                rewards = rj.get('rewards')
                c = cat.get(ep_id, {})
                # 归因: catalog rating 归到 team_name 匹配的座位
                rated_seat = None
                ct = c.get('team_name')
                if ct and ct in teams:
                    rated_seat = teams.index(ct)
                rec = {
                    'ep': ep_id, 'captured_at': c.get('captured_at'),
                    'teams': teams, 'rewards': rewards,
                    'decks': decks,
                    'arch': [classify(decks[0]), classify(decks[1])],
                    'rated_seat': rated_seat,
                    'score': (float(c['score_at_capture']) if c.get('score_at_capture') else None),
                    'rank': c.get('rank_at_capture'),
                }
                arch_counter.update(rec['arch'])
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                kept += 1
            except Exception:
                continue
    proc.stdout.close()
    if stopped_early and proc.poll() is None:
        proc.terminate()
    returncode = proc.wait()
    if not stopped_early and returncode != 0:
        raise RuntimeError(f'zstd exited with status {returncode}')
    print(f'DONE scanned={n} kept={kept}', flush=True)
    print('archetypes:', arch_counter.most_common(15), flush=True)

if __name__ == '__main__':
    main()
