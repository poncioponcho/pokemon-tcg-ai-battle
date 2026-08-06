"""Build dataset manifest.csv: episode -> team/rank/score/winner/decisions."""
import json, csv, os, glob

RAW = 'inference/leaderboard_replay/raw'
MANIFEST = 'inference/leaderboard_replay/manifest.jsonl'
SCAN = 'inference/leaderboard_replay/raw_scan_results.json'
OUT = 'inference/dataset/manifest.csv'

episode_capture = {}
for line in open(MANIFEST):
    m = json.loads(line)
    for e in m['episodes']:
        episode_id = str(e['episode_id'])
        raw_rank = m.get('rank_at_capture', m.get('rank'))
        raw_score = m.get('score_at_capture', m.get('leaderboard_score'))
        try:
            raw_score = float(raw_score)
        except (TypeError, ValueError):
            raw_score = ''
        candidate = {
            'team_id': m.get('team_id', ''),
            'team_name': m.get('team_name', ''),
            'rank_at_capture': raw_rank if raw_rank is not None else '',
            'score_at_capture': raw_score,
            'captured_at': m.get('captured_at', m.get('date', '')),
            'submission_id': m.get('best_submission_id', ''),
        }
        previous = episode_capture.get(episode_id)
        if previous is None or str(candidate['captured_at']) < str(previous['captured_at']):
            # Pick the earliest capture timestamp, never the best historical rank.
            episode_capture[episode_id] = candidate

scan = {os.path.basename(r['path']).split('-')[1]: r for r in json.load(open(SCAN))}

rows = []
for f in sorted(glob.glob(f'{RAW}/episode-*-replay.json')):
    ep = os.path.basename(f).split('-')[1]
    r = scan.get(ep)
    captured = episode_capture.get(ep, {})
    rows.append({
        'episode_id': ep,
        'file': os.path.basename(f),
        'n_steps': r['n_steps'] if r else '',
        'n_decisions': r['n_sel'] if r else '',
        'winner': r['winner'] if r else '',
        'rewards': json.dumps(r['rewards']) if r else '',
        'team_id': captured.get('team_id', ''),
        'team_name': captured.get('team_name', ''),
        'rank_at_capture': captured.get('rank_at_capture', ''),
        'score_at_capture': captured.get('score_at_capture', ''),
        'captured_at': captured.get('captured_at', ''),
        'submission_id': captured.get('submission_id', ''),
    })

with open(OUT, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

covered = sum(1 for r in rows if r['team_id'])
print(f'{len(rows)} episodes -> {OUT}; with team mapping: {covered}')
