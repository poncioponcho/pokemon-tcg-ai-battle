"""Export the distilled student to a numpy checkpoint for the Kaggle submission.

The submission agent (main.py) runs in a CPU-only environment where we cannot
rely on torch, so the student forward pass is re-implemented in pure numpy.
This script:
  1. loads student_best.pt (produced by train_v2.py --stage distill)
  2. writes model_student.npz (fp16 weights + fp32 div + card vocab LUT + meta)
  3. self-checks: numpy forward vs torch forward on real data rows

Run:
  python3 export_student.py [--student data/student_best.pt] [--out ../../model_student.npz]
"""
from __future__ import annotations

import argparse, json, os, sys
from pathlib import Path

import numpy as np
import torch

DATASET_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DATASET_DIR))

import train_bc
from model_v2 import PolicyStudent

ST_DIM = 11 * train_bc.CARD_DIM
SC_DIM = 90
O_DIM = 52
K = 64


def numpy_forward(w, st, sc, opts, mask):
    """Pure numpy mirror of PolicyStudent.forward. w holds fp32 arrays."""
    # fp16 派生 fp32 权重的大矩阵乘会触发 numpy 良性 BLAS 警告（结果仍有限）。
    with np.errstate(divide='ignore', over='ignore', invalid='ignore'):
        return _numpy_forward_core(w, st, sc, opts, mask)


def _numpy_forward_core(w, st, sc, opts, mask):
    x = np.concatenate([st / w['div'], sc], axis=1)          # (B, ST+SC)
    h = np.maximum(x @ w['enc0'].T + w['enc0b'], 0)
    h = np.maximum(h @ w['enc2'].T + w['enc2b'], 0)
    e = np.maximum(h @ w['enc4'].T + w['enc4b'], 0)          # (B, out)
    be = np.repeat(e[:, None, :], opts.shape[1], axis=1)     # (B, K, out)
    z = np.concatenate([be, opts], axis=2)                   # (B, K, out+O)
    g = np.maximum(z @ w['head0'].T + w['head0b'], 0)
    logits = (g @ w['head2'].T + w['head2b']).squeeze(-1)    # (B, K)
    logits = np.where(mask == 0, -np.inf, logits)
    return logits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--student', default=str(DATASET_DIR / 'data' / 'student_best.pt'))
    ap.add_argument('--out', default=str(DATASET_DIR.parents[1] / 'model_student.npz'))
    ap.add_argument('--check-rows', type=int, default=512)
    args = ap.parse_args()

    student = PolicyStudent(ST_DIM, SC_DIM, O_DIM, K, div=train_bc.DIV.clone())
    state = torch.load(args.student, map_location='cpu')
    # [2026-08-08 shape 推断] 从权重形状推断 hidden/out，避免硬编码默认 384 导致
    # 加载 768 权重时 size mismatch（student_hidden 可调时 export 必须自适应）。
    if 'enc.0.weight' in state:
        hidden = int(state['enc.0.weight'].shape[0])
        out = int(state['enc.4.weight'].shape[0]) if 'enc.4.weight' in state else 192
        student = PolicyStudent(ST_DIM, SC_DIM, O_DIM, K,
                                hidden=hidden, out=out,
                                div=train_bc.DIV.clone())
        print(f'[shape-infer] student hidden={hidden} out={out}', flush=True)
    student.load_state_dict(state)
    student.eval()

    sd = student.state_dict()
    w32 = {
        'enc0': sd['enc.0.weight'].numpy(), 'enc0b': sd['enc.0.bias'].numpy(),
        'enc2': sd['enc.2.weight'].numpy(), 'enc2b': sd['enc.2.bias'].numpy(),
        'enc4': sd['enc.4.weight'].numpy(), 'enc4b': sd['enc.4.bias'].numpy(),
        'head0': sd['head.0.weight'].numpy(), 'head0b': sd['head.0.bias'].numpy(),
        'head2': sd['head.2.weight'].numpy(), 'head2b': sd['head.2.bias'].numpy(),
        'div': sd['div'].numpy(),
    }
    vocab = train_bc.VOCAB
    card_ids = np.asarray([int(c) for c in vocab['card_ids']], dtype=np.int32)
    meta = {
        'format': 'ptcg_student_npz_v1',
        'card_vocab_version': vocab['version'],
        'st_dim': ST_DIM, 'sc_dim': SC_DIM, 'o_dim': O_DIM, 'k': K,
        'hidden': int(sd['enc.0.weight'].shape[0]),
        'out': int(sd['enc.4.weight'].shape[0]),
        'source': os.path.basename(args.student),
    }
    arrays = {k: v.astype(np.float16) for k, v in w32.items() if k != 'div'}
    arrays['div'] = w32['div'].astype(np.float32)
    arrays['card_ids'] = card_ids
    arrays['meta_json'] = np.frombuffer(json.dumps(meta).encode('utf-8'), dtype=np.uint8)
    np.savez_compressed(args.out, **arrays)
    size_kb = os.path.getsize(args.out) / 1024
    print(f'wrote {args.out} ({size_kb:.0f} KiB) meta={meta}')

    # ---- self-check: numpy forward (fp16->fp32) vs torch forward ----
    data_dir = DATASET_DIR / 'data'
    rows = min(args.check_rows, len(np.load(data_dir / 'labels.npy', mmap_mode='r')))
    st = torch.from_numpy(np.asarray(
        np.load(data_dir / 'states_u8.npy', mmap_mode='r')[:rows])).float()
    sc = torch.from_numpy(np.asarray(
        np.load(data_dir / 'scalars.npy', mmap_mode='r')[:rows])).float()
    op = torch.from_numpy(np.asarray(
        np.load(data_dir / 'opts_u8.npy', mmap_mode='r')[:rows])).float()
    mk = torch.from_numpy(np.asarray(
        np.load(data_dir / 'masks.npy', mmap_mode='r')[:rows]))
    with torch.no_grad():
        ref = student(st, sc, op, mk).numpy()
    w = {k: arrays[k].astype(np.float32) for k in
         ('enc0', 'enc0b', 'enc2', 'enc2b', 'enc4', 'enc4b', 'head0', 'head0b', 'head2', 'head2b')}
    w['div'] = arrays['div']
    got = numpy_forward(w, st.numpy(), sc.numpy(), op.numpy(), mk.numpy())
    finite = np.isfinite(ref)
    diff = np.abs(ref[finite] - got[finite]).max()
    top_ref = np.argmax(np.where(finite, ref, -np.inf), axis=1)
    top_got = np.argmax(np.where(finite, got, -np.inf), axis=1)
    agree = float((top_ref == top_got).mean())
    print(f'self-check rows={rows} max_abs_diff={diff:.5f} top1_agreement={agree:.4f}')
    if diff > 0.05 or agree < 0.99:
        raise SystemExit('self-check FAILED: numpy forward diverges from torch')
    print('self-check OK')


if __name__ == '__main__':
    main()
