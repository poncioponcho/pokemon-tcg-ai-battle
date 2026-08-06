"""Extract training tensors from raw replay JSONs -> compact .npy/.npz.

Per decision (obs.select != null):
  state_u8 (11 * frozen_card_vocab_size, uint8): state bag vectors
  scalars (90, float32): hp/turn/flags/select-context/type one-hots
  opts_u8 (K=64, 52, uint8): per-option features
  label (K, uint8 multi-hot), mask (K, uint8)
  meta: ep_idx, perspective, reward(+1/-1), turn, context, num_opts,
        rank_at_capture, captured_team_index, is_captured_team
"""
import csv, json, os, glob, sys, time, argparse
from pathlib import Path
import numpy as np
from multiprocessing import Pool

try:
    from .card_vocab import card_index, load_or_create
    from .replay_archive import iter_replays
    from .quality_subset import captured_team_index
except ImportError:  # Direct script execution.
    from card_vocab import card_index, load_or_create
    from replay_archive import iter_replays  # type: ignore
    from quality_subset import captured_team_index  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW = str(PROJECT_ROOT / 'inference/leaderboard_replay/raw')
ID_SCAN = str(PROJECT_ROOT / 'inference/leaderboard_replay/id_scan_results.json')
MANIFEST = str(PROJECT_ROOT / 'inference/dataset/manifest.csv')
CATALOG = str(PROJECT_ROOT / 'inference/leaderboard_replay/episode_catalog.jsonl')
ARCHIVE_CANDIDATES = (
    PROJECT_ROOT / 'inference/leaderboard_replay/archive-firstarchive/raw_replays.jsonl.zst',
    PROJECT_ROOT / 'inference/leaderboard_replay/archive/raw_replays.jsonl.zst',
)
OUTDIR = str(PROJECT_ROOT / 'inference/dataset/data')
VOCAB_PATH = str(PROJECT_ROOT / 'inference/dataset/card_vocab_v1.json')
K = 64
VOCAB = load_or_create(VOCAB_PATH, id_scan_path=ID_SCAN)
CARD_DIM = int(VOCAB['size'])
N_CTX = 45
N_STYPE = 10
O_DIM = 52

CARD_IDS = [int(i) for i in VOCAB['card_ids']]
ID2IDX = {int(cid): int(index) for cid, index in VOCAB['id_to_index'].items()}

AREA_MAX = 12
STYPE_MAX = 15


def load_capture_metadata(path=MANIFEST):
    result = {}
    if not os.path.exists(path):
        return result
    with open(path, newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            episode_id = str(row.get('episode_id', ''))
            if not episode_id:
                continue
            value = row.get('rank_at_capture', '')
            try:
                rank = float(value)
            except (TypeError, ValueError):
                rank = -1.0
            result[episode_id] = {
                'rank_at_capture': rank,
                'team_name': row.get('team_name', ''),
            }
    catalog_path = Path(CATALOG)
    if catalog_path.exists():
        with catalog_path.open(encoding='utf-8') as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                episode_id = str(row.get('episode_id', ''))
                if episode_id in result:
                    continue
                try:
                    rank = float(row.get('rank_at_capture'))
                except (TypeError, ValueError):
                    rank = -1.0
                result[episode_id] = {
                    'rank_at_capture': rank,
                    'team_name': row.get('team_name', ''),
                }
    return result


CAPTURE_BY_EPISODE = load_capture_metadata()
RANK_BY_EPISODE = {
    episode_id: value['rank_at_capture']
    for episode_id, value in CAPTURE_BY_EPISODE.items()
}


def resolve_archive(path=None):
    if path:
        return Path(path)
    for candidate in ARCHIVE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def raw_directory_usable(raw_dir):
    try:
        files = sorted(Path(raw_dir).glob('episode-*-replay.json'))
        if not files:
            return False
        with files[0].open('rb') as handle:
            handle.read(1)
        return True
    except (OSError, PermissionError):
        return False


def card_vec(ids, out):
    for c in ids:
        if isinstance(c, dict) and c.get('id') is not None:
            idx = card_index(c['id'], VOCAB)
            out[idx] += 1
    return out


def bag(counts, out):
    for idx, c in counts.items():
        if idx < CARD_DIM:
            out[idx] = min(c, 255)


def onehot(v, n, out, start):
    if v is not None and 0 <= int(v) < n:
        out[start + int(v)] = 1


def build_decision(
    ag,
    ep_idx,
    perspective,
    reward,
    decks,
    rank_at_capture=-1.0,
    captured_team_index_value=-1,
):
    obs = ag.get('observation', {})
    sel = obs.get('select') or {}
    cur = obs.get('current')
    st = np.zeros(11 * CARD_DIM, dtype=np.uint8)
    sc = np.zeros(90, dtype=np.float32)
    o = np.zeros((K, O_DIM), dtype=np.uint8)
    label = np.zeros(K, dtype=np.uint8)
    mask = np.zeros(K, dtype=np.uint8)
    opts = sel.get('option') or []
    n_opts = len(opts)
    act = ag.get('action') or []
    if not (isinstance(act, list) and 0 < len(act) <= n_opts and n_opts > 0
            and all(isinstance(a, int) and 0 <= a < n_opts for a in act)):
        return None
    if isinstance(act, list):
        for a in act:
            if isinstance(a, int) and 0 <= a < K:
                label[a] = 1
    for k in range(min(K, n_opts)):
        mask[k] = 1
        op = opts[k] if isinstance(opts[k], dict) else {}
        base = 0
        onehot(op.get('type'), STYPE_MAX + 1, o[k], base); base += STYPE_MAX + 1
        onehot(op.get('area'), AREA_MAX + 1, o[k], base); base += AREA_MAX + 1
        onehot(op.get('inPlayArea'), AREA_MAX + 1, o[k], base); base += AREA_MAX + 1
        for name in ('playerIndex', 'index', 'inPlayIndex', 'attackId',
                     'count', 'number', 'serial', 'energyIndex', 'toolIndex', 'cardId'):
            v = op.get(name)
            if name == 'cardId':
                o[k, base] = min(ID2IDX.get(v, 0), 255) if v is not None else 0
            elif isinstance(v, (int, float)) and 0 <= v <= 255:
                o[k, base] = int(v)
            elif isinstance(v, (int, float)) and v > 255:
                o[k, base] = 255
            base += 1
    if cur is None:
        return st, sc, o, label, mask, (
            ep_idx, perspective, reward, -1, sel.get('context', -1),
            n_opts, rank_at_capture, captured_team_index_value,
            1 if captured_team_index_value >= 0 and perspective == captured_team_index_value else 0
            if captured_team_index_value >= 0 else -1,
        )
    ps = cur.get('players') or []
    if not ps:
        ps = [{'active': [], 'bench': [], 'hand': [], 'discard': [], 'deckCount': 0} for _ in range(2)]
    yi = cur.get('yourIndex', 0)
    mine, opp = ps[yi % len(ps)], ps[(yi + 1) % len(ps)]
    card_vec(mine.get('hand'), st[0:CARD_DIM])
    card_vec(mine.get('discard'), st[CARD_DIM:2 * CARD_DIM])
    card_vec(opp.get('discard'), st[2 * CARD_DIM:3 * CARD_DIM])
    deck0, deck1 = decks
    mine_d = deck0 if yi == 0 else deck1
    opp_d = deck1 if yi == 0 else deck0
    if mine_d:
        cnt = np.bincount([ID2IDX[c] for c in mine_d if c in ID2IDX], minlength=CARD_DIM)
        st[3 * CARD_DIM:4 * CARD_DIM] = cnt[:CARD_DIM]
    # NOTE: st[4D:5D] (对手牌组) 故意留零 —— 推理侧 main.py 看不到对手牌组，
    # 训练填充该槽位会造成 训练泄漏 + 推理分布偏移（实测 49% 训练行非零）。
    # 如需恢复对手牌组信息，必须同时修改 main.py 的 _nn_build_features。
    card_vec(mine.get('active'), st[5 * CARD_DIM:6 * CARD_DIM])
    card_vec(opp.get('active'), st[6 * CARD_DIM:7 * CARD_DIM])
    card_vec(mine.get('bench'), st[7 * CARD_DIM:8 * CARD_DIM])
    card_vec(opp.get('bench'), st[8 * CARD_DIM:9 * CARD_DIM])
    def energy_bag(p, out):
        for pm in (p.get('active') or []) + (p.get('bench') or []):
            if isinstance(pm, dict):
                for e in pm.get('energies') or []:
                    if isinstance(e, int):
                        idx = ID2IDX.get(e, 0)
                        if idx < CARD_DIM: out[idx] += 1
    energy_bag(mine, st[9 * CARD_DIM:10 * CARD_DIM])
    energy_bag(opp, st[10 * CARD_DIM:11 * CARD_DIM])
    m_a = (mine.get('active') or [None])[0]
    o_a = (opp.get('active') or [None])[0]
    m_a = m_a if isinstance(m_a, dict) else None
    o_a = o_a if isinstance(o_a, dict) else None
    def hp(pm): return pm.get('hp', 0), pm.get('maxHp', 1)
    mh, mmh = hp(m_a) if m_a else (0, 1)
    oh, omh = hp(o_a) if o_a else (0, 1)
    sc[0] = mh; sc[1] = mh / mmh; sc[2] = oh; sc[3] = oh / omh
    sc[4] = len(m_a.get('energies', [])) if m_a else 0
    sc[5] = len(o_a.get('energies', [])) if o_a else 0
    sc[6] = len(mine.get('bench', [])); sc[7] = len(opp.get('bench', []))
    sc[8] = len(mine.get('hand', [])); sc[9] = mine.get('deckCount', 0); sc[10] = opp.get('deckCount', 0)
    sc[11] = len(mine.get('prize', [])); sc[12] = len(opp.get('prize', []))
    for i, st_name in enumerate(('asleep', 'burned', 'confused', 'paralyzed', 'poisoned')):
        sc[13 + i] = 1 if mine.get(st_name) else 0
        sc[18 + i] = 1 if opp.get(st_name) else 0
    sc[23] = cur.get('turn', 0); sc[24] = cur.get('turnActionCount', 0)
    for j, fl in enumerate(('energyAttached', 'supporterPlayed', 'stadiumPlayed', 'retreated')):
        sc[25 + j] = 1 if cur.get(fl) else 0
    sc[29] = cur.get('firstPlayer', 0); sc[30] = yi
    onehot(sel.get('context'), N_CTX, sc, 31)
    onehot(sel.get('type'), N_STYPE, sc, 31 + N_CTX)
    sc[31 + N_CTX + N_STYPE] = sel.get('maxCount', 1)
    sc[32 + N_CTX + N_STYPE] = sel.get('minCount', 1)
    sc[33 + N_CTX + N_STYPE] = sel.get('remainDamageCounter', 0)
    sc[34 + N_CTX + N_STYPE] = sel.get('remainEnergyCost', 0)
    ctx = sel.get('context', -1)
    return st, sc, o, label, mask, (
        ep_idx, perspective, reward, cur.get('turn', 0), ctx,
        n_opts, rank_at_capture, captured_team_index_value,
        1 if captured_team_index_value >= 0 and perspective == captured_team_index_value else 0
        if captured_team_index_value >= 0 else -1,
    )


def process_payload(d, episode_id):
    capture_metadata = CAPTURE_BY_EPISODE.get(episode_id, {})
    rank_at_capture = capture_metadata.get('rank_at_capture', -1.0)
    captured_team_name = capture_metadata.get('team_name', '')
    info = d.get('info') if isinstance(d.get('info'), dict) else {}
    team_names = info.get('TeamNames') or info.get('teamNames')
    if not team_names:
        agents = info.get('Agents') or d.get('agents') or []
        team_names = [
            agent.get('Name') if isinstance(agent, dict) else str(agent)
            for agent in agents
        ]
    capture_index = captured_team_index(team_names, captured_team_name)
    decks = [None, None]
    for step in d.get('steps', []):
        if not isinstance(step, list):
            continue
        for ag in step:
            act = ag.get('action')
            if isinstance(act, list) and len(act) == 60 and all(isinstance(x, int) for x in act):
                if ag.get('observation', {}).get('select') is None:
                    if decks[0] is None:
                        decks[0] = act
                    elif decks[1] is None:
                        decks[1] = act
    rewards = d.get('rewards') or [0, 0]
    out = []
    for step in d.get('steps', []):
        if not isinstance(step, list):
            continue
        for ag in step:
            obs = ag.get('observation', {})
            if not isinstance(obs, dict) or obs.get('select') is None:
                continue
            cur = obs.get('current')
            yi = cur.get('yourIndex', 0) if isinstance(cur, dict) else 0
            rw = rewards[yi] if isinstance(rewards, list) and yi < len(rewards) else 0
            r = build_decision(
                ag, 0, yi, 1.0 if rw == 1 else -1.0, decks,
                rank_at_capture=rank_at_capture,
                captured_team_index_value=capture_index,
            )
            if r is not None:
                out.append(r)
    return episode_id, out


def process_one(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return None
    episode_id = Path(path).stem.replace('-replay', '').replace('episode-', '')
    return process_payload(d, episode_id)


def count_payload(d):
    n = 0
    for step in d.get('steps', []):
        if not isinstance(step, list):
            continue
        for ag in step:
            obs = ag.get('observation', {})
            if not isinstance(obs, dict):
                continue
            sel = obs.get('select')
            if not isinstance(sel, dict):
                continue
            nopts = len(sel.get('option') or [])
            act = ag.get('action') or []
            if (isinstance(act, list) and 0 < len(act) <= nopts and nopts > 0
                    and all(isinstance(a, int) and 0 <= a < nopts for a in act)):
                n += 1
    return n


def count_one(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return 0
    return count_payload(d)


def archive_records(path, limit=0):
    for index, (episode_id, _, payload) in enumerate(iter_replays(path)):
        if limit and index >= limit:
            break
        yield episode_id, payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw-dir', default=RAW)
    ap.add_argument('--archive', default='',
                    help='streamable .jsonl.zst archive; disables multiprocessing; auto fallback when raw is unavailable')
    ap.add_argument('--out', default=OUTDIR)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    archive = Path(args.archive) if args.archive else None
    if archive is None and not raw_directory_usable(args.raw_dir):
        archive = resolve_archive()
        if archive:
            print(f'raw source unavailable; archive fallback: {archive}')
    if archive is None and not raw_directory_usable(args.raw_dir):
        raise RuntimeError(
            f'raw directory is unavailable and no archive was found; checked {ARCHIVE_CANDIDATES}'
        )
    files = []
    t0 = time.time()
    if archive:
        if not archive.exists():
            raise FileNotFoundError(archive)
        print(f'stream source: {archive}')
        total_n = sum(count_payload(d) for _, d in archive_records(archive, args.limit))
    else:
        files = sorted(glob.glob(f'{args.raw_dir}/episode-*-replay.json'))
        if args.limit:
            files = files[:args.limit]
        with Pool(args.workers) as p:
            counts = p.imap_unordered(count_one, files, chunksize=50)
            total_n = sum(counts)
    print(f'valid decisions: {total_n} in {time.time()-t0:.0f}s')
    mm = {}
    for name, shape, dtype in (
            ('states_u8', (total_n, 11 * CARD_DIM), np.uint8),
            ('scalars', (total_n, 90), np.float32),
            ('opts_u8', (total_n, K, O_DIM), np.uint8),
            ('labels', (total_n, K), np.uint8),
            ('masks', (total_n, K), np.uint8),
    ):
        mm[name] = np.lib.format.open_memmap(f'{args.out}/{name}.npy', mode='w+', dtype=dtype, shape=shape)
    Mt = np.zeros((total_n, 9), dtype=np.float32)
    episode_ids = np.empty(total_n, dtype='<U64')
    offset = 0
    episode_index = 0

    def consume(result):
        nonlocal offset, episode_index
        if not result:
            return
        episode_id, decs = result
        if not decs:
            return
        n = len(decs)
        mm['states_u8'][offset:offset + n] = np.stack([d[0] for d in decs])
        mm['scalars'][offset:offset + n] = np.stack([d[1] for d in decs])
        mm['opts_u8'][offset:offset + n] = np.stack([d[2] for d in decs])
        mm['labels'][offset:offset + n] = np.stack([d[3] for d in decs])
        mm['masks'][offset:offset + n] = np.stack([d[4] for d in decs])
        episode_ids[offset:offset + n] = episode_id
        for j, d in enumerate(decs):
            e, p_, rw, turn, ctx, nop, rank_at_capture, capture_index, is_capture_team = d[5]
            Mt[offset + j] = (
                episode_index, p_, rw, turn, ctx, nop, rank_at_capture,
                capture_index, is_capture_team,
            )
        offset += n
        episode_index += 1

    if archive:
        for episode_id, payload in archive_records(archive, args.limit):
            consume(process_payload(payload, episode_id))
    else:
        with Pool(args.workers) as p:
            for result in p.imap_unordered(process_one, files, chunksize=20):
                consume(result)
    for name in mm:
        mm[name].flush()
    np.save(f'{args.out}/meta.npy', Mt)
    np.save(f'{args.out}/episode_ids.npy', episode_ids)
    with open(f'{args.out}/meta.json', 'w') as f:
        json.dump({
            'n_decisions': total_n,
            'n_episodes': episode_index,
            'state_dim': 11 * CARD_DIM, 'scalar_dim': 90,
            'K': K, 'opt_dim': O_DIM,
            'n_cards': len(CARD_IDS), 'max_card_id': max(CARD_IDS),
            'card_vocab_version': VOCAB['version'],
            'rank_field': 'rank_at_capture',
            'metadata_columns': [
                'episode_index', 'perspective', 'reward', 'turn', 'context',
                'num_options', 'rank_at_capture', 'captured_team_index',
                'is_captured_team',
            ],
            'raw_source': str(args.raw_dir) if archive is None else None,
            'archive_fallback': str(archive) if archive is not None else None,
            'seconds': round(time.time() - t0, 1),
        }, f, indent=1)
    print(f'{total_n} decisions from {episode_index} episodes -> {args.out} in {time.time()-t0:.1f}s')
    print('files:', sorted(os.path.basename(f) for f in glob.glob(f'{args.out}/*.npy')))


if __name__ == '__main__':
    main()
