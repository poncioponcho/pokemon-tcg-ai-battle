"""attack_distill_probe.py — 攻击选择蒸馏诊断 (peer 08-10 映射第 1 条)

目的: 规则 agent 攻击选择 elite-match 仅 0.118 (ctx7, eval_project 5479 决策) 是最大短板。
本脚本用三方正面对比定位规则与精英/NN 分歧最大的攻击局面:
  - elite: 榜单精英回放里同局面的真实选择 (ground truth)
  - teacher: reports/kerr_teacher_v3/ckpt/teacher_best.pt (ctx7 top1 0.569 实测, 精英行为的平滑近似)
  - rule: 当前 main.py (v24.8, 隔离目录导入, 无 npz advisor 污染)

数据源: inference/leaderboard_replay/archive/all_replays.jsonl.zst (1.7GB 流式, ~24k 局全扫)
      注: official_bulk_2026-07-30 是 Lucario 崛起前的旧 meta (前100局 0 个 677/678), 不可用。
过滤: 只收「决策方场上/手牌有 677/678 (Lucario 线)」的决策 —— 与我们的提交牌型同族,
      精英在异族牌组上的选择对我们不可操作。

产出: experiments/runs/attack_distill_records.jsonl  (每行一条攻击相关决策记录)
用法: nohup /opt/homebrew/bin/python3 experiments/attack_distill_probe.py > experiments/runs/attack_distill_probe.log 2>&1 &
"""
import json, os, shutil, subprocess, sys, tempfile
from collections import Counter

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(PROJ, 'inference/leaderboard_replay/archive/all_replays.jsonl.zst')
OUT = os.path.join(PROJ, 'experiments/runs/attack_distill_records.jsonl')
CKPT = os.path.join(PROJ, 'reports/kerr_teacher_v3/ckpt/teacher_best.pt')
LUCARIO_LINE = {677, 678}
MAX_LUCARIO_EPS = 800          # 收满这么多 Lucario 驾驶局就停
MAX_DECISIONS_PER_EP = 400     # 防爆护栏

# ---- 1. 隔离导入规则 main (无 npz, 避免 advisor AttributeError 污染 Lucario 局面) ----
_iso = tempfile.mkdtemp(prefix='rule_iso_')
shutil.copy(os.path.join(PROJ, 'main.py'), _iso)
shutil.copy(os.path.join(PROJ, 'deck.csv'), _iso)
sys.path.insert(0, _iso)
import main as rule_main  # noqa: E402
assert 'model_student' not in str(getattr(rule_main, '_NN_PATH', '')), 'npz leaked?'

# ---- 2. 加载 NN teacher ----
sys.path.insert(0, os.path.join(PROJ, 'inference/dataset'))
import numpy as np  # noqa: E402
import torch  # noqa: E402
import train_bc  # noqa: E402
from model_v2 import PolicyTeacher  # noqa: E402
from agent import build_state_obs  # noqa: E402

ST_DIM = 11 * int(train_bc.VOCAB['size'])
teacher = PolicyTeacher(ST_DIM, 90, 52, 64)
_sd = torch.load(CKPT, map_location='cpu')
if isinstance(_sd, dict) and 'model' in _sd:
    _sd = _sd['model']
teacher.load_state_dict(_sd)
teacher.eval()


def nn_top1(obs):
    """返回 (top1 选项下标, top2 下标, top1-top2 logit 差) 或 None。"""
    try:
        st, sc, o, mk, n_opts = build_state_obs(obs)
        if n_opts == 0:
            return None
        with torch.no_grad():
            logits = teacher(torch.from_numpy(st).unsqueeze(0),
                               torch.from_numpy(sc).unsqueeze(0),
                               torch.from_numpy(o).unsqueeze(0),
                               torch.from_numpy(mk).unsqueeze(0)).flatten()
        v, idx = torch.topk(logits, min(2, int(mk.sum().item()) or 1))
        idx = idx.tolist(); v = v.tolist()
        gap = (v[0] - v[1]) if len(v) > 1 else 99.0
        return idx[0], (idx[1] if len(idx) > 1 else -1), float(gap)
    except Exception:
        return None


def opt_tag(opts, idx):
    """选项下标 → 可读标签: atk:<attackId> / t<type> / oob"""
    if not isinstance(idx, int) or idx < 0 or idx >= len(opts):
        return 'oob'
    o = opts[idx]
    if isinstance(o, dict) and 'attackId' in o:
        return f"atk:{o['attackId']}"
    if isinstance(o, dict):
        return f"t{o.get('type', '?')}"
    return 't?'


def side_snapshot(p):
    a = (p.get('active') or [{}])
    a = a[0] if isinstance(a[0], dict) else {}
    bench = [c for c in (p.get('bench') or []) if isinstance(c, dict)]
    return {
        'active_id': a.get('id', -1), 'active_hp': a.get('hp', 0),
        'active_maxhp': a.get('maxHp', 0),
        'active_energy': len(a.get('energies') or []),
        'bench_ids': [c.get('id', -1) for c in bench],
        'bench_energy': {str(c.get('id', -1)): len(c.get('energies') or []) for c in bench},
        'n_hand': len(p.get('hand') or []),
        'n_prize': len(p.get('prize') or []),
        'deck_count': p.get('deckCount', 0),
    }


def is_lucario(p):
    ids = {c.get('id') for c in (p.get('active') or []) + (p.get('bench') or []) if isinstance(c, dict)}
    ids |= {c.get('id') for c in (p.get('hand') or []) if isinstance(c, dict)}
    return bool(ids & LUCARIO_LINE)


def main():
    zstd = shutil.which('zstd')
    if zstd is None:
        raise SystemExit('zstd executable not found on PATH')
    proc = subprocess.Popen(  # noqa: S603 - fixed executable and flags
        [zstd, '-dc', ARCHIVE], stdout=subprocess.PIPE,
        text=True, bufsize=1 << 20)
    if proc.stdout is None:
        proc.kill()
        raise RuntimeError('failed to open zstd stdout pipe')
    n_eps = n_luc = n_rec = 0
    rule_faults = 0
    ctx_counter = Counter()
    stopped_early = False
    with open(OUT, 'w') as out:
        for line in proc.stdout:
            n_eps += 1
            if n_eps % 200 == 0:
                print(f'...eps={n_eps} lucario={n_luc} rec={n_rec} faults={rule_faults}', flush=True)
            try:
                ep = json.loads(line)
                rj = ep.get('raw_json')
                if isinstance(rj, str):
                    rj = json.loads(rj)
                steps = rj.get('steps') or []
            except Exception:
                continue
            rewards = rj.get('rewards') if isinstance(rj, dict) else None
            ep_id = ep.get('episode_id')
            ep_had_luc = False
            ep_recs = []
            for step in steps:
                if not isinstance(step, list):
                    continue
                for ent in step[:2]:
                    if not isinstance(ent, dict):
                        continue
                    obs = ent.get('observation')
                    act = ent.get('action')
                    if not isinstance(obs, dict):
                        continue
                    sel = obs.get('select')
                    if not isinstance(sel, dict):
                        continue
                    cur = obs.get('current') or {}
                    ps = cur.get('players') or []
                    if len(ps) < 2:
                        continue
                    yi = cur.get('yourIndex', 0) % len(ps)
                    mine, opp = ps[yi], ps[(yi + 1) % len(ps)]
                    if not is_lucario(mine):
                        continue
                    ep_had_luc = True
                    opts = sel.get('option') or []
                    ctx = sel.get('context')
                    has_atk_opt = any(isinstance(o, dict) and 'attackId' in o for o in opts)
                    # 攻击相关决策: ctx==7 或 选项里带 attackId
                    if ctx != 7 and not has_atk_opt:
                        continue
                    acts = act if isinstance(act, list) else ([act] if act is not None else [])
                    acts = [a for a in acts if isinstance(a, int)]
                    if not acts:
                        continue
                    ctx_counter[str(ctx)] += 1
                    # 三方选择
                    try:
                        r_acts = rule_main.agent(obs)
                        r_acts = [int(i) for i in r_acts if isinstance(i, (int, float))] if r_acts else []
                    except Exception:
                        rule_faults += 1
                        r_acts = ['FAULT']
                    nn = nn_top1(obs)
                    rec = {
                        'ep': ep_id, 'turn': cur.get('turn', 0), 'ctx': ctx,
                        'maxCount': sel.get('maxCount', 1),
                        'n_opts': len(opts),
                        'atk_opts': {str(i): o['attackId'] for i, o in enumerate(opts)
                                     if isinstance(o, dict) and 'attackId' in o},
                        'elite': [opt_tag(opts, a) for a in acts],
                        'rule': [opt_tag(opts, a) for a in r_acts],
                        'nn': (opt_tag(opts, nn[0]) if nn else None),
                        'nn_gap': (round(nn[2], 3) if nn else None),
                        'me': side_snapshot(mine), 'opp': side_snapshot(opp),
                        'energyAttached': bool(cur.get('energyAttached')),
                        'reward': (rewards[yi] if isinstance(rewards, list) and len(rewards) > yi else None),
                    }
                    ep_recs.append(rec)
                    if len(ep_recs) >= MAX_DECISIONS_PER_EP:
                        break
            if ep_had_luc:
                n_luc += 1
                for r in ep_recs:
                    out.write(json.dumps(r, ensure_ascii=False) + '\n')
                n_rec += len(ep_recs)
                if n_luc >= MAX_LUCARIO_EPS:
                    print(f'cap reached: lucario_eps={n_luc}', flush=True)
                    stopped_early = True
                    break
    proc.stdout.close()
    if stopped_early and proc.poll() is None:
        proc.terminate()
    returncode = proc.wait()
    if not stopped_early and returncode != 0:
        raise RuntimeError(f'zstd exited with status {returncode}')
    print(f'DONE eps={n_eps} lucario_eps={n_luc} records={n_rec} rule_faults={rule_faults}', flush=True)
    print('ctx distribution:', dict(ctx_counter.most_common(10)), flush=True)


if __name__ == '__main__':
    main()
