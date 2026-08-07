# -*- coding: utf-8 -*-
"""reward_calc.py — Hermes Lab Loop L2：奖励计算 + 晋级门禁（确定性，双胜率门禁版）

用法:
  # 追加一条实验记录到 ledger（含 R(e) 与晋级判定）
  python3 reward_calc.py record \
      --experiment exp001 \
      --arena experiments/arena_report-exp001.json \
      --canary 0.312 --fixed 0.35 \
      --smoke-pass true --invalid-actions 0 \
      --quota-used 3.2

  # 只重算某个历史实验（ledger 只追加，可复算验证）
  python3 reward_calc.py recompute --experiment exp001 --from-ledger experiments/ledger.jsonl

设计要点（见 HERMES_LAB_LOOP_DESIGN.md §1 + 附录 B3/C3）：
- 双胜率门禁：vs champion 镜像 ΔWR≥+2% ∧ CI 下界过线 ∧ vs first 不劣化
- R(e) = 100*(WR_mirror - WR_champ_mirror)           # 主项：镜像胜率差
        + 30*(WR_first - WR_champ_first)               # 弱点对局改善加分
        +  5*Δcanary + 2*Δfixed                        # 整形
        - 20*invalid - 10*pack_fail - 5*quota_over     # 罚项
        +  2*ΔLB/100 (仅提交后)                         # 终局
- 晋级: mirror ΔWR≥+2% ∧ CI_lo(mirror) > champ_wr_mirror
        ∧ first WR ≥ champ_wr_first (不劣化)
        ∧ arena_games≥2000 ∧ canary不退化 ∧ 零非法动作
"""
import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
EXP = PROJ / 'experiments'
LEDGER = EXP / 'ledger.jsonl'

# 基线实测值（arena_report-baseline_v232.json, 2026-08-06 8000 局）
BASELINE_MIRROR_WR = 0.5205   # v23.2 镜像胜率（≈50%，deck 随机性）
BASELINE_FIRST_WR = 0.3285    # v23.2 vs first 弱点对局胜率
BASELINE_TOTAL_WR = 0.6280    # 四对手合计总胜率（仅作记录参考）


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def load_champion() -> dict:
    """读当前 champion 状态：优先 experiments/champion.json，兜底纯规则基线。

    champion.json 字段（双胜率门禁版）：
      id, wr_mirror, wr_first, wr_total, canary, fixed, source
    旧字段 wr（总胜率）向后兼容：存在则映射到 wr_total。
    """
    p = EXP / 'champion.json'
    if p.exists():
        c = json.loads(p.read_text(encoding='utf-8'))
        # 向后兼容：旧 champion.json 只有 wr（总胜率），补默认值
        if 'wr_mirror' not in c:
            c['wr_mirror'] = BASELINE_MIRROR_WR
        if 'wr_first' not in c:
            c['wr_first'] = BASELINE_FIRST_WR
        if 'wr_total' not in c:
            c['wr_total'] = c.get('wr', BASELINE_TOTAL_WR)
        if 'canary' not in c:
            c['canary'] = 0.30
        if 'fixed' not in c:
            c['fixed'] = 0.35
        return c
    return {
        'id': 'v23_2_rules',
        'wr_mirror': BASELINE_MIRROR_WR,
        'wr_first': BASELINE_FIRST_WR,
        'wr_total': BASELINE_TOTAL_WR,
        'canary': 0.30,
        'fixed': 0.35,
        'source': 'phase0-baseline',
    }


def wilson_ci_lo(p_hat: float, n: int, z: float = 1.96) -> float:
    """二项分布 Wilson 95% 置信区间下界。"""
    if n <= 0:
        return 0.0
    denom = 1 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - margin)


def load_arena_report(path: Path) -> dict:
    """解析 arena_report.json，提取总胜率 + per_opponent 分对手胜率。"""
    r = json.loads(Path(path).read_text(encoding='utf-8'))
    n = int(r.get('games_total', 0))
    wins = int(r.get('wins', 0))
    wr = wins / n if n else 0.0
    # 提取 per_opponent 分对手胜率
    per_opp = {}
    for entry in r.get('per_opponent', []):
        name = entry.get('opponent', '')
        w = int(entry.get('w', 0))
        l = int(entry.get('l', 0))
        d = int(entry.get('d', 0))
        opp_n = w + l + d
        opp_wr = w / opp_n if opp_n else 0.0
        per_opp[name] = {
            'w': w, 'l': l, 'd': d, 'n': opp_n,
            'wr': opp_wr,
            'invalid': int(entry.get('invalid', 0)),
        }
    return {
        'n': n, 'wins': wins, 'wr': wr,
        'invalid': int(r.get('invalid_actions', 0)),
        'per_opponent': per_opp,
        'raw': r,
    }


def compute_reward(exp: dict, arena: dict, champ: dict,
                   canary: float, fixed: float, smoke_pass: bool,
                   invalid_actions: int, quota_used: float, quota_budget: float,
                   lb_delta: float = 0.0, submitted: bool = False) -> dict:
    """核心：R(e) + 双胜率晋级判定（全确定性）。

    门禁双指标（附录 B3/C3）：
      mirror: vs champion 镜像 ΔWR≥+2% ∧ CI 下界 > champ 点估计
      first:  vs first 弱点对局 WR ≥ champ_first_wr（不劣化）
    R(e) 主项 = 镜像胜率差 ×100 + first 改善 ×30（弱点对局改善高价值加分）。
    """
    per_opp = arena.get('per_opponent', {})

    # === 镜像胜率（主基准） ===
    mirror = per_opp.get('v23_2_rules')
    if mirror is None:
        # 兜底：如果 arena 没跑镜像对手，用总 WR 退化（但不推荐）
        wr_mirror = arena['wr']
        n_mirror = arena['n']
    else:
        wr_mirror = mirror['wr']
        n_mirror = mirror['n']
    champ_wr_mirror = champ.get('wr_mirror', BASELINE_MIRROR_WR)
    dwr_mirror = wr_mirror - champ_wr_mirror
    ci_lo_mirror = wilson_ci_lo(wr_mirror, n_mirror)

    # === first 胜率（弱点对局） ===
    first = per_opp.get('first')
    if first is None:
        wr_first = 0.0
        n_first = 0
    else:
        wr_first = first['wr']
        n_first = first['n']
    champ_wr_first = champ.get('wr_first', BASELINE_FIRST_WR)
    dwr_first = wr_first - champ_wr_first

    # === 总胜率（记录参考） ===
    wr_total = arena['wr']
    champ_wr_total = champ.get('wr_total', champ.get('wr', BASELINE_TOTAL_WR))
    dwr_total = wr_total - champ_wr_total

    # === R(e) 计算 ===
    # 主项：镜像胜率差（核心指标）
    R = 100.0 * dwr_mirror
    # 弱点对局改善加分（first 是已证实坏对局，改善高价值）
    R += 30.0 * max(0.0, dwr_first)  # 只加分不减分（first 劣化由门禁拦截，不双罚）
    # 整形项
    R += 5.0 * (canary - champ.get('canary', 0.30))
    R += 2.0 * (fixed - champ.get('fixed', 0.35))
    # 罚项
    R -= 20.0 if invalid_actions > 0 else 0.0
    R -= 10.0 if not smoke_pass else 0.0
    R -= 5.0 if quota_used > quota_budget else 0.0
    # 终局（仅提交后）
    if submitted:
        R += 2.0 * lb_delta / 100.0

    # ---- 双胜率晋级门禁 ----
    n_total = arena['n']
    gate = {
        'arena_games_ok': n_total >= 2000,
        # 镜像门禁：ΔWR≥+2% 且 CI 下界过线
        'mirror_dwr_ok': dwr_mirror >= 0.02,
        'mirror_ci_ok': ci_lo_mirror > champ_wr_mirror,
        # first 门禁：不劣化（WR ≥ champ 基线）
        'first_ok': wr_first >= champ_wr_first if n_first > 0 else False,
        # 通用门禁
        'canary_ok': canary >= max(0.30, champ.get('canary', 0.30) - 0.01),
        'clean_ok': invalid_actions == 0 and smoke_pass,
    }
    promoted = all(gate.values())

    return {
        'R': round(R, 4),
        # 镜像指标
        'wr_mirror': round(wr_mirror, 4),
        'dwr_mirror': round(dwr_mirror, 4),
        'ci_lo_mirror': round(ci_lo_mirror, 4),
        'champ_wr_mirror': round(champ_wr_mirror, 4),
        # first 指标
        'wr_first': round(wr_first, 4),
        'dwr_first': round(dwr_first, 4),
        'champ_wr_first': round(champ_wr_first, 4),
        # 总指标（参考）
        'wr_total': round(wr_total, 4),
        'dwr_total': round(dwr_total, 4),
        'champ_wr_total': round(champ_wr_total, 4),
        # 判定
        'promoted': promoted,
        'gate': gate,
    }


def cmd_record(args) -> int:
    champ = load_champion()
    # [bugfix] args.arena 可能带 experiments/ 前缀（文档用法）也可能是裸文件名；
    # 直接按原样解析，已带 EXP 前缀或绝对路径时不再叠加 EXP，避免双前缀。
    arena_arg = Path(args.arena)
    if arena_arg.is_absolute() or arena_arg.parent.name == 'experiments' or arena_arg.exists():
        arena_path = arena_arg
    else:
        arena_path = EXP / arena_arg
    arena = load_arena_report(arena_path)
    quota_budget = args.quota_budget
    if not quota_budget:
        try:
            import yaml as _y
            _meta = _y.safe_load((EXP / 'experiments.yaml').read_text(encoding='utf-8'))
            quota_budget = _meta['meta'].get('quota_week_gpu_h', 28.0)
        except Exception:
            quota_budget = 28.0

    result = compute_reward(
        exp=args.experiment, arena=arena, champ=champ,
        canary=args.canary, fixed=args.fixed, smoke_pass=args.smoke_pass,
        invalid_actions=args.invalid_actions,
        quota_used=args.quota_used, quota_budget=quota_budget,
        lb_delta=args.lb_delta, submitted=args.submitted,
    )
    row = {
        'ts': _now_iso(),
        'experiment': args.experiment,
        'arena_games': arena['n'],
        'arena_wr': round(arena['wr'], 4),  # 总胜率（参考）
        'arena_wr_mirror': result['wr_mirror'],
        'arena_wr_first': result['wr_first'],
        'canary': args.canary,
        'fixed': args.fixed,
        'invalid_actions': args.invalid_actions,
        'smoke_pass': args.smoke_pass,
        'quota_used_h': args.quota_used,
        # champion 基线（双胜率）
        'champ_wr_mirror': result['champ_wr_mirror'],
        'champ_wr_first': result['champ_wr_first'],
        'champ_wr_total': result['champ_wr_total'],
        **result,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')

    print(json.dumps(row, ensure_ascii=False, indent=2))
    print()
    if result['promoted']:
        print('PROMOTED: challenger 击败 champion → 更新 champion.json')
        (EXP / 'champion.json').write_text(json.dumps({
            'id': args.experiment,
            'wr_mirror': result['wr_mirror'],
            'wr_first': result['wr_first'],
            'wr_total': result['wr_total'],
            'canary': args.canary,
            'fixed': args.fixed,
            'source': f'ledger@{row["ts"]}',
        }, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        print('REJECTED: 未达双胜率门禁（见 gate 明细）')
    return 0 if result['promoted'] else 2


def cmd_recompute(args) -> int:
    """从 ledger 重算某实验（验证可复算性）。"""
    p = Path(args.from_ledger)
    if not p.exists():
        print(f'ledger 不存在: {p}')
        return 1
    rows = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
    hits = [r for r in rows if r['experiment'] == args.experiment]
    if not hits:
        print(f'未找到 {args.experiment}')
        return 1
    r = hits[-1]
    print(f"实验 {args.experiment}: R={r['R']} promoted={r['promoted']}")
    print(f"  镜像: WR={r.get('wr_mirror', r.get('arena_wr_mirror', '?'))} "
          f"ΔWR={r.get('dwr_mirror', '?')} CI_lo={r.get('ci_lo_mirror', '?')} "
          f"champ={r.get('champ_wr_mirror', '?')}")
    print(f"  first: WR={r.get('wr_first', r.get('arena_wr_first', '?'))} "
          f"ΔWR={r.get('dwr_first', '?')} champ={r.get('champ_wr_first', '?')}")
    print(f"  总: WR={r['arena_wr']} (n={r['arena_games']})")
    print(f"  gate={json.dumps(r['gate'], ensure_ascii=False)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description='Hermes Lab Loop L2: 奖励 + 晋级')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_rec = sub.add_parser('record')
    p_rec.add_argument('--experiment', required=True)
    p_rec.add_argument('--arena', required=True, help='arena_report-<id>.json 相对 experiments/')
    p_rec.add_argument('--canary', type=float, required=True)
    p_rec.add_argument('--fixed', type=float, required=True)
    p_rec.add_argument('--smoke-pass', type=lambda s: s.lower() in ('1', 'true', 'yes'))
    p_rec.add_argument('--invalid-actions', type=int, default=0)
    p_rec.add_argument('--quota-used', type=float, default=0.0)
    p_rec.add_argument('--quota-budget', type=float, default=0.0)
    p_rec.add_argument('--lb-delta', type=float, default=0.0)
    p_rec.add_argument('--submitted', action='store_true')
    p_rec.set_defaults(func=cmd_record)

    p_rc = sub.add_parser('recompute')
    p_rc.add_argument('--experiment', required=True)
    p_rc.add_argument('--from-ledger', default=str(LEDGER))
    p_rc.set_defaults(func=cmd_recompute)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
