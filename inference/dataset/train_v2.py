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

import argparse, json, os, random, time, threading, queue
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
    # TODO(08-09 hy3 审计确认): extract.py 写入 9 列 (末两列 captured_team_index/
    # is_capture_team), 此处仅映射 7 列 —— 捕获队加权信号当前是死数据。
    # 疑似 RCA 2026-08-08 (canary top1 与胜率脱节) 后主动 descope, 待主线 B
    # 重训前确认是否有意; 若有需要在此处补 'captured_team_idx','is_capture_team'。
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
    # 仅 split=='train' 进入训练；'excluded'（如规则 replay 剔除）必须显式过滤，
    # 否则 set(assignments) - fixed - canary 会把 excluded 重新捞回训练集。
    train_ids = {eid for eid, s in assignments.items() if s == 'train'} - canary_ids
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


class SegProfiler:
    """Wall-clock segment profiler for the training loop (--profile).

    Attributes
    - prepare : waiting for the next batch from the prefetch queue (data starvation)
    - transfer: .to(device) + dtype conversion
    - compute : forward + backward + optimizer step
    Zero overhead when disabled.
    """

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.prepare = 0.0
        self.transfer = 0.0
        self.compute = 0.0
        self.count = 0
        self._t = None

    def tick(self, seg: str) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        if self._t is not None:
            setattr(self, seg, getattr(self, seg) + (now - self._t))
        self._t = now

    def reset(self) -> None:
        self.prepare = self.transfer = self.compute = self.count = 0.0
        self._t = None

    def summary(self, phase: str, epoch: int) -> str:
        if not self.enabled or self.count == 0:
            return ''
        tot = self.prepare + self.transfer + self.compute
        if tot <= 0:
            return ''
        pct = lambda v: f'{v / tot * 100:5.1f}%'
        return (f'  [profile] ep{epoch} {phase}: '
                f'prepare {pct(self.prepare)} transfer {pct(self.transfer)} '
                f'compute {pct(self.compute)} '
                f'| per-batch prepare {self.prepare / self.count * 1000:.0f}ms '
                f'transfer {self.transfer / self.count * 1000:.0f}ms '
                f'compute {self.compute / self.count * 1000:.0f}ms '
                f'(n={int(self.count)})')


def make_blocked_perm(split, bs, block_mult=8, rng=None):
    """Build an epoch permutation that reads the 8GB mmap sequentially.

    split is the sorted train-index space. Cut it into physically contiguous
    blocks ``[b, b+C)`` (C = block_mult*bs), shuffle *within* each block, then
    concatenate blocks back to back. Every index appears exactly once per epoch
    (same sampling semantics as np.random.permutation) but any window of ``bs``
    consecutive rows stays inside one block -> consecutive pages on disk.

    block_mult=0 -> fall back to legacy global random permutation (baseline).
    """
    n = len(split)
    if block_mult <= 0:
        rng = rng if rng is not None else np.random
        return rng.permutation(split)
    C = int(block_mult) * bs
    sorted_idx = np.sort(np.asarray(split, dtype=np.int64))
    out = np.empty(n, dtype=np.int64)
    rng = rng if rng is not None else np.random
    for b in range(0, n, C):
        blk = sorted_idx[b:b + C]
        out[b:b + C] = rng.permutation(blk)
    return out


class BatchPrefetcher:
    """Prefetch the next batches on CPU (numpy gather -> pinned torch) while the
    GPU trains the current one. Cuts host->device wait to zero on the training
    loop, which is the dominant stall when data is mmap'd (random access).

    workers: producer threads, each grabbing the next unproduced batch-slot of
    ``perm``. Consecutive slots lie inside one physical block (see
    make_blocked_perm), so each gather is a contiguous mmap read -> page-cache
    friendly on the 8GB states_u8. workers=1 is the legacy single-thread path.
    """

    def __init__(self, perm, n, bs, arrays, meta, phase, device,
                 workers=1, depth=2):
        self.q = queue.Queue(maxsize=depth)
        self._stop = threading.Event()
        self._pin_ok = True
        self._perm, self._n, self._bs = perm, n, bs
        self._arrays, self._meta, self._phase, self._device = arrays, meta, phase, device
        self._workers = max(1, int(workers))
        self._slot = 0
        self._slot_lock = threading.Lock()
        self._err = None
        self._threads = [threading.Thread(target=self._produce, daemon=True)
                         for _ in range(self._workers)]
        for th in self._threads:
            th.start()

    def _pin(self, t):
        if self._pin_ok:
            try:
                return t.pin_memory()
            except Exception:
                self._pin_ok = False
        return t

    def _next_slot(self):
        with self._slot_lock:
            s = self._slot
            self._slot += self._bs
            return s

    def _produce(self):
        try:
            while True:
                if self._stop.is_set():
                    return
                s = self._next_slot()
                if s >= self._n:
                    return
                i = self._perm[s:s + self._bs]
                st, sc, op, lb, mk = train_bc.batch_from_idx(i, self._arrays,
                                                             to_float=False)
                st = self._pin(st); sc = self._pin(sc); op = self._pin(op)
                lb = self._pin(lb); mk = self._pin(mk)
                reward = None
                if self._phase == 'awr':
                    reward = self._pin(torch.from_numpy(self._meta['reward'][i]))
                self.q.put((st, sc, op, lb, mk, reward))
        except Exception as e:
            self._err = e

    def __iter__(self):
        n_batches = (self._n + self._bs - 1) // self._bs
        consumed = 0
        while consumed < n_batches:
            if self._err is not None:
                raise RuntimeError(f'prefetch failed: {self._err}')
            item = self.q.get()
            if isinstance(item, tuple) and item and item[0] == 'ERR':
                raise RuntimeError(f'prefetch failed: {item[1]}')
            consumed += 1
            yield item

    def close(self):
        self._stop.set()


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
        perm = make_blocked_perm(split, args.bs,
                                 block_mult=getattr(args, 'prefetch_block', 0))
        t0 = time.time(); tot = 0.0; cnt = 0
        prefetch = None
        prof = SegProfiler(getattr(args, 'profile', False))
        try:
            prefetch = BatchPrefetcher(perm, n, args.bs, arrays, meta, phase, device,
                                       workers=getattr(args, 'prefetch_workers', 1),
                                       depth=getattr(args, 'prefetch_depth', 2))
            for st_cpu, sc_cpu, op_cpu, lb_cpu, mk_cpu, reward_cpu in prefetch:
                prof.tick('prepare')
                st = st_cpu.to(device, non_blocking=True).float()
                sc = sc_cpu.to(device, non_blocking=True)
                op = op_cpu.to(device, non_blocking=True).float()
                lb = lb_cpu.to(device, non_blocking=True)
                mk = mk_cpu.to(device, non_blocking=True)
                prof.tick('transfer')
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
                            r = reward_cpu.to(device, non_blocking=True)
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
                prof.tick('compute')
                tot += loss.item(); cnt += 1
                prof.count += 1
        finally:
            if prefetch is not None:
                prefetch.close()
        if prof.enabled:
            print(prof.summary(phase, ep + 1), flush=True)
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
        # [2026-08-08] distill 每 epoch 落一份 student 快照（ckpt 选拔压力改为
        # 本地 arena：canary top1 与实战胜率已实测脱节，见 RCA 2026-08-08）。
        if phase == 'distill' and best_path:
            torch.save(model.state_dict(),
                       Path(best_path).with_name(f'student_ep{ep + 1}.pt'))
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
    ap.add_argument('--sample-index', default='',
                    help='[主线B 08-09] 质量过滤样本索引 .npy (quality_subset 产出, '
                         '胜方视角): BC 与 distill 阶段只在此子集上训练; AWR 阶段'
                         '仍用全量 train split (保留 reward ±1 对比, 否则 AWR 退化为 BC)')
    ap.add_argument('--profile', action='store_true',
                    help='print per-batch prepare/transfer/compute segment timing')
    ap.add_argument('--prefetch-workers', type=int, default=2,
                    help='BatchPrefetcher producer threads (1=legacy single-thread)')
    ap.add_argument('--prefetch-depth', type=int, default=4,
                    help='BatchPrefetcher queue depth')
    ap.add_argument('--prefetch-block', type=int, default=8,
                    help='physical block size (x bs) for sequential mmap reads; '
                         '0 = legacy global random permutation (baseline)')
    args = ap.parse_args()

    device = resolve_device(args.device)
    seed_all(args.seed)
    print(f'device: {device} | seed: {args.seed}', flush=True)

    data_dir = Path(args.data_dir)
    arrays, meta, episode_ids, n = load_arrays(data_dir, args.limit)
    train_idx, eval_idx, canary_idx = split_indices(args, episode_ids)
    print(f'total {n} decisions | train {len(train_idx)} | '
          f'fixed_test {len(eval_idx)} | canary {len(canary_idx)}', flush=True)

    # [主线B 08-09] 质量过滤: BC/distill 限胜方子集 (首次把 quality_subset 接入 train_v2;
    # 旧 run 全量双方决策训练, 败方/低质量动作混入 BC 标签)
    bc_idx = train_idx
    if args.sample_index:
        _si = np.asarray(np.load(args.sample_index), dtype=np.int64)
        bc_idx = train_bc.restrict_split_to_samples(train_idx, _si)
        print(f'sample filter: bc/distill {len(bc_idx)} / train {len(train_idx)} '
              f'(winner-only) | awr 仍用全量 train', flush=True)
        if len(bc_idx) == 0:
            raise SystemExit('sample filter 后 BC 子集为空 — 检查 sample-index 与数据是否同源')

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
            try:
                target.load_state_dict(ckpt['model'])
            except RuntimeError as e:
                # [2026-08-08 容错] 架构变更（如 student_hidden 384→768）时 ckpt 权重
                # 形状不匹配 → load_state_dict 崩。此时放弃恢复该 stage 权重，
                # 从该 stage epoch 0 重新训练（teacher 架构未变可正常恢复）。
                print(f'[resume] 架构不匹配（{str(e)[:80]}），'
                      f'跳过 {ckpt["stage"]} 权重恢复，从头训练该 stage', flush=True)
                start = {'stage': ckpt['stage'], 'phase': ckpt['phase'], 'epoch': 0}
                target = None
            if target is not None:
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
            h, _ = run_phase(teacher, opt, scaler, arrays, meta, bc_idx,
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
    elif args.stage in ('teacher',) and start['stage'] != 'teacher':
        # [bugfix] teacher 已完成（ckpt 标记 stage=student）后再跑 --stage teacher
        # 会静默跳过全部训练并退出 0，误以为已重训。显式报错提示。
        raise SystemExit(
            'checkpoint 已标记 stage=student（teacher 已跑完）；'
            '重跑 --stage teacher 不会重新训练。删除 ckpt 后从零重训，'
            '或用 --stage distill 继续蒸馏。')

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
                    # [2026-08-08 容错] student 架构变更（student_hidden 384→768）时，
                    # 旧 ckpt 权重形状不匹配 → 从头蒸馏（epoch 0），不沿用旧 epoch 计数。
                    if 'enc.0.weight' in ckpt['model'] and \
                            ckpt['model']['enc.0.weight'].shape[0] != student.enc[0].weight.shape[0]:
                        print('[resume] student 架构不匹配（hidden 变更），'
                              'distill 从头开始', flush=True)
                        start_epoch = 0
                    else:
                        start_epoch = int(ckpt['epoch'])
                        opt.load_state_dict(ckpt['opt'])
                        if ckpt.get('scaler'):
                            scaler.load_state_dict(ckpt['scaler'])
            except Exception as e:
                print(f'[resume] student state skipped: {e}', flush=True)
        h, _ = run_phase(student, opt, scaler, arrays, meta, bc_idx,
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
