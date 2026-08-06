"""Full BC (imitation) then AWR (offline RL) training on extracted replay data.

Every invocation retrains from the complete current train split. Incremental
collection is controlled by update_controller.py; this script deliberately has
no newest-batch-only fine-tuning mode.

Phase bc : multi-label cross-entropy over option set (imitate all top-team decisions)
Phase awr: same loss re-weighted by exp((R - b)/tau) where R=+1/-1 episode outcome
           -> advantage-weighted regression, biases policy toward winning play.

Run:  python3 train_bc.py --phase all --epochs-bc 4 --epochs-awr 3
"""
import argparse, json, os, time, math
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    from .card_vocab import load_or_create
    from .mlops_registry import (
        EpisodeCatalog,
        ensure_split_manifest,
        mark_baseline_ready,
        refresh_rolling_canary,
    )
except ImportError:  # Direct script execution.
    from card_vocab import load_or_create
    from mlops_registry import (  # type: ignore
        EpisodeCatalog,
        ensure_split_manifest,
        mark_baseline_ready,
        refresh_rolling_canary,
    )

DATASET_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DATASET_DIR.parents[1]
DATA = str(DATASET_DIR / 'data')
LOG_DIR = str(DATASET_DIR / 'logs')
K = 64
VOCAB = load_or_create(
    DATASET_DIR / 'card_vocab_v1.json',
    id_scan_path=PROJECT_ROOT / 'inference/leaderboard_replay/id_scan_results.json',
)
CARD_DIM = int(VOCAB['size'])
ST_DIM = 11 * CARD_DIM
SC_DIM = 90
O_DIM = 52
DIV = torch.tensor(
    np.concatenate([
        np.full(CARD_DIM, 60.0), np.full(CARD_DIM, 60.0), np.full(CARD_DIM, 60.0),
        np.full(CARD_DIM, 60.0), np.full(CARD_DIM, 60.0), np.full(CARD_DIM, 1.0),
        np.full(CARD_DIM, 1.0), np.full(CARD_DIM, 5.0), np.full(CARD_DIM, 5.0),
        np.full(CARD_DIM, 20.0), np.full(CARD_DIM, 20.0),
    ]), dtype=torch.float32)


class EarlyStopper:
    """Track a validation metric and stop after patience bad epochs."""

    def __init__(self, patience=0, mode='max', min_delta=0.0):
        if mode not in ('max', 'min'):
            raise ValueError(f'unsupported early-stop mode: {mode}')
        self.patience = max(0, int(patience))
        self.mode = mode
        self.min_delta = float(min_delta)
        self.best_value = None
        self.best_epoch = None
        self.bad_epochs = 0
        self.improved = False

    def update(self, value, epoch):
        value = float(value)
        if self.best_value is None:
            improved = True
        elif self.mode == 'max':
            improved = value > self.best_value + self.min_delta
        else:
            improved = value < self.best_value - self.min_delta
        self.improved = improved
        if improved:
            self.best_value = value
            self.best_epoch = epoch
            self.bad_epochs = 0
            return False
        self.bad_epochs += 1
        return bool(self.patience and self.bad_epochs >= self.patience)


def load_checkpoint_into_model(model, path, device='cpu'):
    """Load either a raw model state dict or a saved training checkpoint."""
    payload = torch.load(path, map_location=device)
    if isinstance(payload, dict) and 'model' in payload:
        model.load_state_dict(payload['model'])
        return {
            'format': 'checkpoint',
            'epoch': int(payload.get('epoch', 0)),
            'phase': payload.get('phase'),
        }
    if isinstance(payload, dict):
        model.load_state_dict(payload)
        return {'format': 'state_dict', 'epoch': 0, 'phase': None}
    raise ValueError(f'unsupported checkpoint payload: {type(payload).__name__}')


class Policy(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc = nn.Sequential(
            nn.Linear(ST_DIM + SC_DIM, 256), nn.ReLU(),
            nn.Linear(256, 256), nn.ReLU(),
            nn.Linear(256, 128), nn.ReLU(),
        )
        self.head = nn.Sequential(
            nn.Linear(128 + O_DIM, 128), nn.ReLU(),
            nn.Linear(128, 1),
        )

    def forward(self, st, sc, opts, mask):
        x = torch.cat([st / DIV.to(st.device), sc], 1)
        e = self.enc(x)
        be = e.unsqueeze(1).expand(-1, K, -1)
        h = self.head(torch.cat([be, opts], 2)).squeeze(2)
        return h.masked_fill(mask == 0, float('-inf'))


def batch_from_idx(idx, arrays):
    st = torch.from_numpy(arrays['states_u8'][idx]).float()
    sc = torch.from_numpy(arrays['scalars'][idx]).float()
    op = torch.from_numpy(arrays['opts_u8'][idx]).float()
    lb = torch.from_numpy(arrays['labels'][idx])
    mk = torch.from_numpy(arrays['masks'][idx])
    return st, sc, op, lb, mk


def restrict_split_to_samples(split, sample_indices):
    """Intersect a stable episode split with an externally prepared sample index."""
    return np.intersect1d(
        np.asarray(split, dtype=np.int64),
        np.asarray(sample_indices, dtype=np.int64),
        assume_unique=False,
    )


def ce_loss(logits, labels, mask, weights=None):
    logp = F.log_softmax(logits, 1)
    safe = logp.clone()
    safe[mask == 0] = 0
    sel = labels * mask
    cnt = sel.sum(1).clamp(min=1).float()
    per = -(sel * safe).sum(1) / cnt
    if weights is not None:
        per = per * weights
    return per.mean()


@torch.no_grad()
def evaluate(model, arrays, idx, meta, device, bs=8192):
    if len(idx) == 0:
        return {'recall': 0.0, 'top1': 0.0}, {}, {}
    model.eval()
    hit = 0; n = 0; hit_top = 0
    ctx_hit = {}; ctx_n = {}
    for s in range(0, len(idx), bs):
        i = idx[s:s + bs]
        st, sc, op, lb, mk = [t.to(device) for t in batch_from_idx(i, arrays)]
        logits = model(st, sc, op, mk)
        probs = F.softmax(logits, 1)
        cnt = lb.sum(1).clamp(min=1)
        hit += ((probs * lb).sum(1) / cnt).sum().item()
        top = logits.argmax(1)
        hit_top += (lb[torch.arange(len(i)), top] == 1).sum().item()
        n += len(i)
        ctxs = meta['ctx'][i]
        for ci in np.unique(ctxs):
            sel = ctxs == ci
            if sel.any():
                k = logits[sel].argmax(1)
                ok = lb[sel, k].sum().item()
                ctx_hit[int(ci)] = ctx_hit.get(int(ci), 0) + ok
                ctx_n[int(ci)] = ctx_n.get(int(ci), 0) + int(sel.sum())
    return {'recall': hit / n, 'top1': hit_top / n}, ctx_hit, ctx_n


def train_phase(model, opt, arrays, meta, split, epochs, phase, args, device, logf,
                output_dir=DATA, epoch_start=0, monitor_idx=None,
                early_stop_patience=0, best_output=None, sample_weights=None):
    if len(split) == 0:
        raise ValueError(f'{phase} cannot train with an empty split')
    history = []
    stopper = EarlyStopper(patience=early_stop_patience, mode='max')
    eval_every = max(1, int(args.eval_every))
    n = len(split)
    for ep in range(epoch_start, epochs):
        model.train()
        perm = np.random.permutation(split)
        t0 = time.time(); tot = 0.; cnt = 0
        for s in range(0, n, args.bs):
            i = perm[s:s + args.bs]
            st, sc, op, lb, mk = [t.to(device) for t in batch_from_idx(i, arrays)]
            w = None
            if phase == 'awr':
                r = torch.from_numpy(meta['reward'][i]).to(device)
                b = r.mean()
                w = torch.exp((r - b) / args.tau).clamp(max=args.wcap)
                if sample_weights is not None:
                    w *= torch.from_numpy(sample_weights[i]).float().to(device)
            logits = model(st, sc, op, mk)
            loss = ce_loss(logits, lb, mk, w)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            tot += loss.item(); cnt += 1
        record = {
            'epoch': ep + 1,
            'phase': phase,
            'loss': tot / cnt,
            'seconds': round(time.time() - t0, 2),
        }
        should_eval = monitor_idx is not None and (
            (ep + 1) % eval_every == 0 or ep + 1 == epochs
        )
        should_stop = False
        if should_eval:
            monitor, _, _ = evaluate(model, arrays, monitor_idx, meta, device)
            record['monitor'] = monitor
            should_stop = stopper.update(monitor['top1'], ep + 1)
            record['monitor_best_top1'] = stopper.best_value
            record['monitor_best_epoch'] = stopper.best_epoch
            if stopper.improved and best_output:
                torch.save(model.state_dict(), best_output)
        history.append(record)
        msg = f'[{phase}] epoch {ep+1}/{epochs} loss {record["loss"]:.4f} ({record["seconds"]:.0f}s)'
        if 'monitor' in record:
            msg += f' canary_top1 {record["monitor"]["top1"]:.4f}'
        if should_stop:
            msg += f' early_stop(best_epoch={stopper.best_epoch})'
        print(msg, flush=True); logf.write(msg + '\n'); logf.flush()
        torch.save({'model': model.state_dict(), 'opt': opt.state_dict(),
                    'epoch': ep + 1, 'phase': phase, 'args': vars(args)},
                   os.path.join(output_dir, f'ckpt_{phase}.pt'))
        if should_stop:
            break
    return history, stopper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', default='all', choices=['bc', 'awr', 'all'])
    ap.add_argument('--epochs-bc', type=int, default=4)
    ap.add_argument('--epochs-awr', type=int, default=3)
    ap.add_argument('--bs', type=int, default=4096)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--tau', type=float, default=0.5)
    ap.add_argument('--wcap', type=float, default=20.0)
    ap.add_argument('--eval-every', type=int, default=1)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--data-dir', default=DATA,
                    help='extracted tensor directory; full retraining reads all tensors here')
    ap.add_argument('--logs-dir', default=LOG_DIR)
    ap.add_argument('--device', choices=('auto', 'cpu', 'mps'), default='auto')
    ap.add_argument('--resume-from', default=None,
                    help='raw model state dict or checkpoint, typically model_bc.pt for AWR continuation')
    ap.add_argument('--model-output', default=None,
                    help='output model path; defaults to data/model_bc.pt or data/model_awr.pt')
    ap.add_argument('--best-model-output', default=None,
                    help='best monitored model path; defaults beside model-output')
    ap.add_argument('--sample-index', default=None,
                    help='optional .npy absolute decision-row index for quality filtering')
    ap.add_argument('--sample-weights', default=None,
                    help='optional .npy full-length AWR multiplier array')
    ap.add_argument('--early-stop-patience', type=int, default=0,
                    help='canary top1 bad epochs before stopping; 0 disables stopping')
    ap.add_argument('--early-stop-min-delta', type=float, default=0.0)
    ap.add_argument('--split-manifest', default=str(DATASET_DIR / 'splits' / 'episode_splits.jsonl'))
    ap.add_argument('--canary-manifest', default=str(DATASET_DIR / 'splits' / 'rolling_canary.json'))
    ap.add_argument('--canary-episodes', type=int, default=100)
    ap.add_argument('--mlops-state', default=str(DATASET_DIR / 'mlops_state.json'))
    ap.add_argument('--mark-converged', action='store_true',
                    help='Explicitly enable monitoring after this baseline is verified')
    args = ap.parse_args()
    torch.manual_seed(args.seed); np.random.seed(args.seed)
    if args.device == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('MPS requested but is unavailable')
    device = (
        'mps' if args.device == 'auto' and torch.backends.mps.is_available()
        else 'cpu' if args.device == 'auto' else args.device
    )
    print(f'device: {device}')
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    arrays = {}
    for name in ('states_u8', 'scalars', 'opts_u8', 'labels', 'masks'):
        p = os.path.join(data_dir, f'{name}.npy')
        arrays[name] = np.load(p, mmap_mode='r' if name != 'labels' else 'r')
    meta_arr = np.load(os.path.join(data_dir, 'meta.npy'))
    meta_keys = ('ep', 'persp', 'reward', 'turn', 'ctx', 'nopts', 'rank_at_capture')
    meta = {
        key: meta_arr[:, i] if i < meta_arr.shape[1] else np.full(len(meta_arr), -1.0)
        for i, key in enumerate(meta_keys)
    }
    episode_path = os.path.join(data_dir, 'episode_ids.npy')
    if not os.path.exists(episode_path):
        raise RuntimeError(
            'episode_ids.npy is missing. Re-run extract.py before training so '
            'fixed-test and rolling-canary splits use real immutable episode IDs.'
        )
    episode_ids = np.asarray(np.load(episode_path, allow_pickle=True)).astype(str)
    N = len(meta['ep'])
    if args.limit:
        N = args.limit
    episode_ids = episode_ids[:N]
    dataset_episode_set = set(episode_ids)
    assignments = ensure_split_manifest(
        episode_ids,
        args.split_manifest,
        fixed_test_fraction=0.10,
    )
    catalog = EpisodeCatalog(PROJECT_ROOT / 'inference/leaderboard_replay')
    records = [record for record in catalog.records()
               if str(record.get('episode_id', '')) in dataset_episode_set]
    if not records:
        records = [{'episode_id': episode_id, 'captured_at': str(index)}
                   for index, episode_id in enumerate(sorted(set(episode_ids)))]
    canary_ids = set(refresh_rolling_canary(
        records,
        assignments,
        args.canary_manifest,
        limit=args.canary_episodes,
    ))
    fixed_ids = {episode_id for episode_id, split in assignments.items() if split == 'fixed_test'}
    train_ids = set(assignments) - fixed_ids - canary_ids
    train_idx = np.where(np.isin(episode_ids, list(train_ids)))[0]
    eval_idx = np.where(np.isin(episode_ids, list(fixed_ids)))[0]
    canary_idx = np.where(np.isin(episode_ids, list(canary_ids)))[0]
    sample_indices = None
    sample_weights = None
    if args.sample_index:
        sample_indices = np.asarray(np.load(args.sample_index), dtype=np.int64)
        train_idx = restrict_split_to_samples(train_idx, sample_indices)
    if args.sample_weights:
        sample_weights = np.asarray(np.load(args.sample_weights), dtype=np.float32)
        if len(sample_weights) < N:
            raise ValueError('sample-weights must cover every decision row')
    print(
        f'total {N} decisions | train {len(train_idx)} ({len(train_ids)} eps) | '
        f'fixed_test {len(eval_idx)} ({len(fixed_ids)} eps) | '
        f'canary {len(canary_idx)} ({len(canary_ids)} eps)'
    )
    model = Policy().to(device)
    resume_info = None
    if args.resume_from:
        resume_info = load_checkpoint_into_model(model, args.resume_from, device='cpu')
        print(f'resumed {args.resume_from}: {resume_info}', flush=True)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    if args.model_output:
        model_output = Path(args.model_output)
    elif args.phase == 'bc':
        model_output = data_dir / 'model_bc.pt'
    else:
        model_output = data_dir / 'model_awr.pt'
    best_model_output = Path(args.best_model_output) if args.best_model_output else model_output.with_suffix('.best.pt')
    model_output.parent.mkdir(parents=True, exist_ok=True)
    best_model_output.parent.mkdir(parents=True, exist_ok=True)
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    logf = open(logs_dir / 'train.log', 'a')
    logf.write(f'\n===== run {time.strftime("%Y-%m-%d %H:%M:%S")} args={vars(args)} =====\n')
    logf.flush()
    ev, ctx_hit, ctx_n = evaluate(model, arrays, eval_idx, meta, device)
    print('init eval:', ev, flush=True)
    training_history = {
        'args': vars(args),
        'resume': resume_info,
        'bc': [],
        'awr': [],
    }
    if args.phase in ('bc', 'all'):
        bc_best = data_dir / 'best_model_bc.pt'
        bc_history, bc_stopper = train_phase(
            model, opt, arrays, meta, train_idx, args.epochs_bc, 'bc', args, device, logf,
            data_dir, monitor_idx=canary_idx,
            early_stop_patience=args.early_stop_patience,
            best_output=bc_best,
            sample_weights=sample_weights,
        )
        training_history['bc'] = bc_history
        if bc_best.exists():
            load_checkpoint_into_model(model, bc_best, device='cpu')
        bc_output = data_dir / 'model_bc.pt' if args.phase == 'all' else model_output
        torch.save(model.state_dict(), bc_output)
        ev, ctx_hit, ctx_n = evaluate(model, arrays, eval_idx, meta, device)
        print('after BC eval:', ev, flush=True)
        logf.write(f'after BC eval: {ev}\n'); logf.flush()
        json.dump({'ev': ev}, open(os.path.join(data_dir, 'eval_bc.json'), 'w'))
    if args.phase in ('awr', 'all'):
        awr_best = best_model_output if args.phase == 'awr' else data_dir / 'best_model_awr.pt'
        awr_history, awr_stopper = train_phase(
            model, opt, arrays, meta, train_idx, args.epochs_awr, 'awr', args, device, logf,
            data_dir, monitor_idx=canary_idx,
            early_stop_patience=args.early_stop_patience,
            best_output=awr_best,
            sample_weights=sample_weights,
        )
        training_history['awr'] = awr_history
        if awr_best.exists():
            load_checkpoint_into_model(model, awr_best, device='cpu')
        torch.save(model.state_dict(), model_output)
        ev, ctx_hit, ctx_n = evaluate(model, arrays, eval_idx, meta, device)
        print('after AWR eval:', ev, flush=True)
        logf.write(f'after AWR eval: {ev}\n'); logf.flush()
    canary_ev, canary_ctx_hit, canary_ctx_n = evaluate(model, arrays, canary_idx, meta, device)
    with open(os.path.join(data_dir, 'eval_report.json'), 'w') as f:
        json.dump({
            'fixed_test': {'ev': ev, 'ctx_hit': ctx_hit, 'ctx_n': ctx_n},
            'rolling_canary': {
                'ev': canary_ev, 'ctx_hit': canary_ctx_hit, 'ctx_n': canary_ctx_n,
            },
            'split_counts': {
                'train_episodes': len(train_ids),
                'fixed_test_episodes': len(fixed_ids),
                'canary_episodes': len(canary_ids),
            },
            'card_vocab_version': VOCAB['version'],
            'rank_field': 'rank_at_capture',
        }, f, indent=1)
    with open(os.path.join(data_dir, 'training_history.json'), 'w') as f:
        json.dump(training_history, f, indent=1)
    if args.mark_converged:
        mark_baseline_ready(
            args.mlops_state,
            sample_size=len(canary_ids),
            metric_plateau=True,
        )
    with open(os.path.join(data_dir, 'model_meta.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'card_vocab_version': VOCAB['version'],
            'card_vocab_size': CARD_DIM,
            'state_dim': ST_DIM,
            'split_manifest': args.split_manifest,
            'fixed_test_episodes': len(fixed_ids),
            'canary_episodes': len(canary_ids),
            'model_output': str(model_output),
            'best_model_output': str(best_model_output),
            'resume_from': args.resume_from,
            'sample_index': args.sample_index,
            'sample_weights': args.sample_weights,
            'train_decisions': len(train_idx),
        }, f, indent=1)
    logf.close()
    print('done', flush=True)


if __name__ == '__main__':
    main()
