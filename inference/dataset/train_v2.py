"""Train v2: teacher BC -> AWR on GPU, then distill to student.

Pipeline (Kaggle GPU notebook friendly):
  stage teacher: BC epochs then AWR epochs on PolicyTeacher
  stage distill: freeze best teacher, train PolicyStudent with distill loss

Features vs train_bc.py:
- device auto-detection prefers CUDA (train_bc only knows mps/cpu)
- mixed precision (autocast + GradScaler) on CUDA
- full checkpoint with optimizer/AMP-scaler/RNG states -> seamless resume after
  Kaggle 'Save & Run All (Commit)' session restarts (single ~9h session limit)
- best-model tracking on the rolling-canary top1 metric (same as train_bc)

Run locally (smoke):
  python3 train_v2.py --stage all --epochs-bc 1 --epochs-awr 1 --epochs-distill 1 --limit 20000 --device cpu
Run on Kaggle GPU:
  python3 train_v2.py --stage all --device auto --bs 16384 \
      --epochs-bc 8 --epochs-awr 5 --epochs-distill 8 --early-stop-patience 3
"""
from __future__ import annotations

import argparse, json, os, random, time
from pathlib import Path

import numpy as np
import torch

import train_bc  # reuse: batch_from_idx, evaluate, EarlyStopper, DIV, VOCAB, CARD_DIM
from model_v2 import (PolicyTeacher, PolicyStudent, distill_per_sample_loss,
                      ce_per_sample, count_parameters)
from mlops_registry import (EpisodeCatalog, ensure_split_manifest,
                            refresh_rolling_canary)

DATASET_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DATASET_DIR.parents[1]
DATA = str(DATASET_DIR / 'data')
LOG_DIR = str(DATASET_DIR / 'logs')

ST_DIM = 11 * train_bc.CARD_DIM
SC_DIM = 90
O_DIM = 52
K = 64


def resolve_device(requested: str) -> str:
    if requested == 'auto':
        if torch.cuda.is_available():
            return 'cuda'
        if torch.backends.mps.is_available():
            return 'mps'
        return 'cpu'
    if requested == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA requested but unavailable')
    if requested == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('MPS requested but unavailable')
    return requested


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def get_rng() -> dict:
    state = {
        'python': random.getstate(),
        'numpy': np.random.get_state(),
        'torch': torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        state['cuda'] = torch.cuda.get_rng_state_all()
    return state


def set_rng(state: dict) -> None:
    random.setstate(state['python'])
    np.random.set_state(state['numpy'])
    torch.set_rng_state(state['torch'])
    if 'cuda' in state and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state['cuda'])


def load_arrays(data_dir: Path, limit: int = 0):
    arrays = {}
    for name in ('states_u8', 'scalars', 'opts_u8', 'labels', 'masks'):
        p = os.path.join(data_dir, f'{name}.npy')
        arrays[name] = np.load(p, mmap_mode='r')
    meta_arr = np.load(os.path.join(data_dir, 'meta.npy'))
    meta_keys = ('ep', 'persp', 'reward', 'turn', 'ctx', 'nopts', 'rank_at_capture')
    meta = {key: meta_arr[:, i] if i < meta_arr.shape[1] else np.full(len(meta_arr), -1.0)
            for i, key in enumerate(meta_keys)}
    episode_ids = np.asarray(
        np.load(os.path.join(data_dir, 'episode_ids.npy'), allow_pickle=True)).astype(str)
    n = len(meta['ep'])
    if limit:
        n = min(n, limit)
        arrays = {k: v[:n] for k, v in arrays.items()}
        meta = {k: v[:n] for k, v in meta.items()}
        episode_ids = episode_ids[:n]
    return arrays, meta, episode_ids, n


def split_indices(args, episode_ids):
    assignments = ensure_split_manifest(
        episode_ids, args.split_manifest, fixed_test_fraction=0.10)
    catalog = EpisodeCatalog(PROJECT_ROOT / 'inference/leaderboard_replay')
    episode_set = set(episode_ids)
    records = [r for r in catalog.records()
               if str(r.get('episode_id', '')) in episode_set]
    if not records:
        records = [{'episode_id': eid, 'captured_at': str(i)}
                   for i, eid in enumerate(sorted(episode_set))]
    canary_ids = set(refresh_rolling_canary(
        records, assignments, args.canary_manifest, limit=args.canary_episodes))
    fixed_ids = {eid for eid, s in assignments.items() if s == 'fixed_test'}
    train_ids = set(assignments) - fixed_ids - canary_ids
    train_idx = np.where(np.isin(episode_ids, list(train_ids)))[0]
    eval_idx = np.where(np.isin(episode_ids, list(fixed_ids)))[0]
    canary_idx = np.where(np.isin(episode_ids, list(canary_ids)))[0]
    return train_idx, eval_idx, canary_idx


def save_ckpt(path, stage, phase, epoch, model, opt, scaler, args, extra=None):
    payload = {
        'stage': stage, 'phase': phase, 'epoch': epoch,
        'model': model.state_dict(), 'opt': opt.state_dict(),
        'scaler': scaler.state_dict() if scaler is not None else None,
        'rng': get_rng(), 'args': vars(args),
    }
    if extra:
        payload.update(extra)
    tmp = str(path) + '.partial'
    torch.save(payload, tmp)
    os.replace(tmp, path)


def run_phase(model, opt, scaler, arrays, meta, split, epochs, phase, args, device, logf,
              monitor_idx, ckpt_path, best_path, start_epoch, teacher=None):
    """One training phase (bc/awr/distill) with AMP, canary-best tracking, ckpt."""
    use_amp = device == 'cuda'
    stopper = train_bc.EarlyStopper(patience=args.early_stop_patience, mode='max')
    history = []
    n = len(split)
    if n == 0:
        raise ValueError(f'{phase}: empty train split')
    for ep in range(start_epoch, epochs):
        model.train()
        perm = np.random.permutation(split)
        t0 = time.time(); tot = 0.0; cnt = 0
        for s in range(0, n, args.bs):
            i = perm[s:s + args.bs]
            st, sc, op, lb, mk = [t.to(device, non_blocking=True)
                                  for t in train_bc.batch_from_idx(i, arrays)]
            with torch.autocast(device_type='cuda', enabled=use_amp):
                logits = model(st, sc, op, mk)
                if phase == 'distill':
                    with torch.no_grad():
                        t_logits = teacher(st, sc, op, mk)
                    per = distill_per_sample_loss(logits, t_logits, lb, mk,
                                                  temperature=args.distill_temp,
                                                  alpha=args.distill_alpha)
                else:
                    per = ce_per_sample(logits, lb, mk)
                    if phase == 'awr':
                        r = torch.from_numpy(meta['reward'][i]).to(device)
                        b = r.mean()
                        w = torch.exp((r - b) / args.tau).clamp(max=args.wcap)
                        per = per * w
                loss = per.mean()
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            scaler.step(opt)
            scaler.update()
            tot += loss.item(); cnt += 1
        record = {'epoch': ep + 1, 'phase': phase,
                  'loss': tot / max(cnt, 1), 'seconds': round(time.time() - t0, 2)}
        should_eval = (ep + 1) % max(1, args.eval_every) == 0 or ep + 1 == epochs
        should_stop = False
        if should_eval and monitor_idx is not None and len(monitor_idx):
            monitor, _, _ = train_bc.evaluate(model, arrays, monitor_idx, meta, device)
            record['monitor'] = monitor
            should_stop = stopper.update(monitor['top1'], ep + 1)
            record['monitor_best_top1'] = stopper.best_value
            if stopper.improved and best_path:
                torch.save(model.state_dict(), best_path)
        history.append(record)
        msg = (f'[{phase}] epoch {ep+1}/{epochs} loss {record["loss"]:.4f} '
               f'({record["seconds"]:.0f}s)')
        if 'monitor' in record:
            msg += (f' canary_top1 {record["monitor"]["top1"]:.4f} '
                    f'(best {stopper.best_value:.4f} @ ep{stopper.best_epoch})')
        print(msg, flush=True); logf.write(msg + '\n'); logf.flush()
        save_ckpt(ckpt_path, 'teacher' if phase in ('bc', 'awr') else 'student',
                  phase, ep + 1, model, opt, scaler, args)
        if should_stop:
            print(f'[{phase}] early stop, best epoch {stopper.best_epoch}', flush=True)
            break
    return history, stopper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', default='all', choices=['teacher', 'distill', 'all'])
    ap.add_argument('--data-dir', default=DATA)
    ap.add_argument('--logs-dir', default=LOG_DIR)
    ap.add_argument('--ckpt-path', default=str(DATASET_DIR / 'data' / 'ckpt_v2_last.pt'))
    ap.add_argument('--teacher-best', default=str(DATASET_DIR / 'data' / 'teacher_best.pt'))
    ap.add_argument('--student-best', default=str(DATASET_DIR / 'data' / 'student_best.pt'))
    ap.add_argument('--resume', default='auto', choices=['auto', 'never'],
                    help='auto: resume from --ckpt-path if present')
    ap.add_argument('--device', default='auto', choices=['auto', 'cpu', 'cuda', 'mps'])
    ap.add_argument('--bs', type=int, default=8192)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--weight-decay', type=float, default=1e-4)
    ap.add_argument('--epochs-bc', type=int, default=8)
    ap.add_argument('--epochs-awr', type=int, default=5)
    ap.add_argument('--epochs-distill', type=int, default=8)
    ap.add_argument('--tau', type=float, default=0.5)
    ap.add_argument('--wcap', type=float, default=20.0)
    ap.add_argument('--eval-every', type=int, default=1)
    ap.add_argument('--early-stop-patience', type=int, default=3)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--limit', type=int, default=0, help='debug: cap decision rows')
    ap.add_argument('--teacher-hidden', type=int, default=1024)
    ap.add_argument('--teacher-blocks', type=int, default=2)
    ap.add_argument('--teacher-dropout', type=float, default=0.10)
    ap.add_argument('--student-hidden', type=int, default=384)
    ap.add_argument('--distill-temp', type=float, default=3.0)
    ap.add_argument('--distill-alpha', type=float, default=0.3)
    ap.add_argument('--split-manifest',
                    default=str(DATASET_DIR / 'splits' / 'episode_splits.jsonl'))
    ap.add_argument('--canary-manifest',
                    default=str(DATASET_DIR / 'splits' / 'rolling_canary.json'))
    ap.add_argument('--canary-episodes', type=int, default=100)
    args = ap.parse_args()

    device = resolve_device(args.device)
    seed_all(args.seed)
    print(f'device: {device} | seed: {args.seed}', flush=True)

    data_dir = Path(args.data_dir)
    arrays, meta, episode_ids, n = load_arrays(data_dir, args.limit)
    train_idx, eval_idx, canary_idx = split_indices(args, episode_ids)
    print(f'total {n} decisions | train {len(train_idx)} | '
          f'fixed_test {len(eval_idx)} | canary {len(canary_idx)}', flush=True)

    logs_dir = Path(args.logs_dir); logs_dir.mkdir(parents=True, exist_ok=True)
    logf = open(logs_dir / 'train_v2.log', 'a')
    logf.write(f'\n===== run {time.strftime("%Y-%m-%d %H:%M:%S")} args={vars(args)} =====\n')
    logf.flush()

    div = train_bc.DIV.clone()
    teacher = PolicyTeacher(ST_DIM, SC_DIM, O_DIM, K, hidden=args.teacher_hidden,
                            blocks=args.teacher_blocks, dropout=args.teacher_dropout,
                            div=div).to(device)
    student = PolicyStudent(ST_DIM, SC_DIM, O_DIM, K, hidden=args.student_hidden,
                            div=div).to(device)
    print(f'teacher params: {count_parameters(teacher):,} | '
          f'student params: {count_parameters(student):,}', flush=True)

    # ---- resume state machine ----
    start = {'stage': 'teacher', 'phase': 'bc', 'epoch': 0}
    ckpt_path = Path(args.ckpt_path)
    if args.resume == 'auto' and ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
        if int(ckpt.get('args', {}).get('seed', args.seed)) != args.seed:
            print('[resume] seed mismatch with checkpoint, starting fresh', flush=True)
        else:
            start = {'stage': ckpt['stage'], 'phase': ckpt['phase'],
                     'epoch': int(ckpt['epoch'])}
            target = teacher if ckpt['stage'] == 'teacher' else student
            target.load_state_dict(ckpt['model'])
            set_rng(ckpt['rng'])
            print(f"[resume] {ckpt['stage']}/{ckpt['phase']} from epoch {ckpt['epoch']}",
                  flush=True)

    use_amp = device == 'cuda'
    history = {'teacher_bc': [], 'teacher_awr': [], 'distill': []}

    # ---- stage 1: teacher BC -> AWR ----
    if args.stage in ('teacher', 'all') and start['stage'] == 'teacher':
        opt = torch.optim.Adam(teacher.parameters(), lr=args.lr,
                               weight_decay=args.weight_decay)
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
        if args.resume == 'auto' and ckpt_path.exists() and start['stage'] == 'teacher':
            try:
                ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
                opt.load_state_dict(ckpt['opt'])
                if ckpt.get('scaler'):
                    scaler.load_state_dict(ckpt['scaler'])
            except Exception as e:
                print(f'[resume] optimizer state skipped: {e}', flush=True)
        if start['phase'] == 'bc':
            h, _ = run_phase(teacher, opt, scaler, arrays, meta, train_idx,
                             args.epochs_bc, 'bc', args, device, logf,
                             canary_idx, ckpt_path, args.teacher_best,
                             start_epoch=start['epoch'])
            history['teacher_bc'] = h
            start = {'stage': 'teacher', 'phase': 'awr', 'epoch': 0}
        if start['phase'] == 'awr':
            if Path(args.teacher_best).exists():
                teacher.load_state_dict(torch.load(args.teacher_best, map_location=device))
            h, _ = run_phase(teacher, opt, scaler, arrays, meta, train_idx,
                             args.epochs_awr, 'awr', args, device, logf,
                             canary_idx, ckpt_path, args.teacher_best,
                             start_epoch=start['epoch'])
            history['teacher_awr'] = h
            start = {'stage': 'student', 'phase': 'distill', 'epoch': 0}
        # mark teacher done so a fresh rerun resumes at distill
        save_ckpt(ckpt_path, 'student', 'distill', 0, student,
                  torch.optim.Adam(student.parameters(), lr=args.lr),
                  torch.amp.GradScaler("cuda", enabled=use_amp), args)

    # ---- stage 2: distill student from frozen best teacher ----
    if args.stage in ('distill', 'all') and (
            start['stage'] == 'student' or args.stage == 'distill'):
        if not Path(args.teacher_best).exists():
            raise RuntimeError(f'teacher best not found: {args.teacher_best} '
                               f'(run --stage teacher first)')
        teacher.load_state_dict(torch.load(args.teacher_best, map_location=device))
        teacher.eval()
        for p in teacher.parameters():
            p.requires_grad_(False)
        opt = torch.optim.Adam(student.parameters(), lr=args.lr,
                               weight_decay=args.weight_decay)
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
        start_epoch = 0
        if args.resume == 'auto' and ckpt_path.exists() and start['stage'] == 'student':
            try:
                ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
                if ckpt['stage'] == 'student':
                    start_epoch = int(ckpt['epoch'])
                    opt.load_state_dict(ckpt['opt'])
                    if ckpt.get('scaler'):
                        scaler.load_state_dict(ckpt['scaler'])
            except Exception as e:
                print(f'[resume] student state skipped: {e}', flush=True)
        h, _ = run_phase(student, opt, scaler, arrays, meta, train_idx,
                         args.epochs_distill, 'distill', args, device, logf,
                         canary_idx, ckpt_path, args.student_best,
                         start_epoch=start_epoch, teacher=teacher)
        history['distill'] = h

    # ---- final evaluation ----
    report = {'args': vars(args), 'device': device, 'n_decisions': n}
    if Path(args.teacher_best).exists():
        teacher.load_state_dict(torch.load(args.teacher_best, map_location=device))
        ev_fixed, _, _ = train_bc.evaluate(teacher, arrays, eval_idx, meta, device)
        ev_canary, _, _ = train_bc.evaluate(teacher, arrays, canary_idx, meta, device)
        report['teacher'] = {'fixed_test': ev_fixed, 'canary': ev_canary,
                             'params': sum(p.numel() for p in teacher.parameters())}
    if Path(args.student_best).exists():
        student.load_state_dict(torch.load(args.student_best, map_location=device))
        ev_fixed, _, _ = train_bc.evaluate(student, arrays, eval_idx, meta, device)
        ev_canary, _, _ = train_bc.evaluate(student, arrays, canary_idx, meta, device)
        report['student'] = {'fixed_test': ev_fixed, 'canary': ev_canary,
                             'params': count_parameters(student)}
    report['history'] = history
    out = Path(args.data_dir) / 'train_v2_report.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'history'}, indent=2))
    logf.close()


if __name__ == '__main__':
    main()
