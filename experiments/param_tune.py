# -*- coding: utf-8 -*-
"""param_tune.py — 规则参数调权器（坐标下降 + 独立批次 + 双门确认）。

接口（已核实）：
- main.py 暴露 `_PARAMS` dict（v24.0, ~60 参数）与 `_apply_params(d)`（调权器入口，
  原地合并、保留嵌套别名、未知键静默忽略）。
- NN advisor 用环境变量关闭：PTCG_NN_MODE=off（v24.3, main.py:3071），
  必须在 load_module 之前设置——纯规则调权，避免 NN rerank 污染。
- 评测 = ar.run_arena(cand, base, deck, deck, n, seed0=seed0) 先后手平衡镜像。
  seed0 只控制 Python 侧；native shuffle 不可注种，候选间不是
  paired/CRN，不能宣称公共随机数方差缩减。

流程（每轮）：
  1. 从 _PARAMS 自动派生标量参数清单（或读 --manifest 指定子集/范围）
  2. 筛选：当前 incumbent 基础上对每个参数试 default±{1,2}*step（独立 n=screen_n, seed0=1000）
  3. 确认：每个参数的最优扰动 → 独立种子 n=confirm_n, seed0=5000，Wilson 下界>0.5 才接受
  4. 终验：incumbent vs default 镜像 (seed0=9000) + vs first(SAMPLE) + vs 冻结池 v23_2_rules
  5. [vs_first 回归门禁] 终验加 default vs_first 公平对照 (同 n/seed/deck):
     vf_delta = incumbent_vf - default_vf < -0.017 (1.7pp 噪声铁律) 判回归,
     写 param_tune_final(vs_first_regression/vf_delta) + param_tune_rejected_regression
     事件, 挡下自动/人工合入 (peer 2026-08-10 09:26 设计, 只盯 vs_first, mirror 由 lo>0.5 守)
不自动改写 main.py——产出 param_tune_final 事件，由人工/kimi code 合入。

韧性：逐结果落盘 param_tune_ckpt.jsonl（键含 deck 指纹与 incumbent 指纹，牌组或
incumbent 变更自动失效）；单个参数评测异常按 wr=0 沉底不炸池；invalid>0 直接拒绝。
产物：experiments/runs/param_tune.jsonl（事件流）+ param_tune_ckpt.jsonl（断点）。
用法：
  python3 experiments/param_tune.py --self-test            # 管道自检（对称性+扰动偏离）
  python3 experiments/param_tune.py --dump-manifest        # 打印自动派生参数清单
  python3 experiments/param_tune.py --rounds 2 --workers 4 # 正式调权
"""
# [可复现加固 2026-08-10] PYTHONHASHSEED 须在解释器启动前固定, 进程内赋值无效
# → re-exec 守卫 (同 deck_search 模式)。注意: 引擎在 hash 固定后仍有 ±1pp
# 残余熵 (object-id 序等), 自检阈值须留余量。
import os as _os
import sys as _sys
if _os.environ.get('PYTHONHASHSEED') != '0':
    _os.environ['PYTHONHASHSEED'] = '0'
    _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

import argparse
import copy
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

EXP = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/experiments')
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

PROJ = ar.PROJ
RUNS = EXP / 'runs'
RUNS.mkdir(exist_ok=True)
LOG = RUNS / 'param_tune.jsonl'
CKPT = RUNS / 'param_tune_ckpt.jsonl'

OUR_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
SAMPLE = ar.SAMPLE_DECK


def emit(ev):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(ev, ensure_ascii=False) + '\n')
    print(ev.get('msg', ''), flush=True)


# ---------------- 并行 worker ----------------
_W = {}


def _init_worker(main_path):
    os.environ['PTCG_NN_MODE'] = 'off'  # 必须先于 load_module
    cand = ar.load_module(Path(main_path))
    base = ar.load_module(Path(main_path))
    _W['cand'] = cand
    _W['base'] = base
    _W['orig'] = copy.deepcopy(cand._PARAMS)


def _eval_task(task):
    overrides, n, seed0, tag = task
    try:
        cand = _W['cand']
        cand._apply_params(copy.deepcopy(_W['orig']))  # 先复位
        cand._apply_params(overrides)
        r = ar.run_arena(cand.agent, _W['base'].agent, OUR_DECK, OUR_DECK, n, seed0=seed0)
        tot = r['wins'] + r['losses'] + r['draws']
        wr = r['wins'] / tot if tot else 0.0
        return (wr, ar.wilson_ci_lo(wr, tot), r['invalid'], r['avg_turns'], tag, None)
    except Exception as e:  # 单个参数点异常不拖垮整个池
        return (0.0, 0.0, -1, 0.0, tag, repr(e))


# ---------------- 断点续跑 ----------------
def _ckpt_key(phase, rd, fp, tag):
    return f'{phase}|{rd}|{fp}|{tag}'


def _fp(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


def ckpt_load():
    done = {}
    if CKPT.exists():
        for ln in CKPT.read_text(encoding='utf-8').splitlines():
            try:
                ev = json.loads(ln)
                done[_ckpt_key(ev['phase'], ev['round'], ev['fp'], ev['tag'])] = \
                    (ev['wr'], ev['lo'], ev['invalid'], ev['avg_turns'])
            except Exception:
                pass
    return done


def ckpt_add(phase, rd, fp, tag, wr, lo, invalid, avg_turns):
    with open(CKPT, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'phase': phase, 'round': rd, 'fp': fp, 'tag': tag,
                            'wr': wr, 'lo': lo, 'invalid': invalid,
                            'avg_turns': avg_turns}) + '\n')


# ---------------- 参数清单 ----------------
def derive_manifest(mod, only=None):
    """从 _PARAMS 自动派生参数清单；dict 跳过（嵌套键由 --manifest 指定），bool 收翻转。"""
    out = []
    for name, d in sorted(mod._PARAMS.items()):
        if only and name not in only:
            continue
        if isinstance(d, dict) or not isinstance(d, (int, float, bool)):
            continue
        if isinstance(d, bool):
            out.append({'name': name, 'default': d, 'step': None, 'type': 'bool'})
            continue
        step = max(1, round(abs(d) * 0.25)) if isinstance(d, int) \
            else max(0.05, round(abs(d) * 0.25, 3))
        out.append({'name': name, 'default': d, 'step': step,
                    'type': 'int' if isinstance(d, int) else 'float'})
    return out


def perturbations(p):
    if p['type'] == 'bool':
        return [not p['default']]
    d, s = p['default'], p['step']
    cands = []
    for k in (1, -1, 2, -2):
        v = d + k * s
        if p['type'] == 'int':
            v = int(round(v))
        else:
            v = round(v, 4)
        if v != d and v not in cands:
            cands.append(v)
    return cands


# ---------------- 评测编排 ----------------
def par_eval(pool, tasks, ckpt_phase, rd, fp, label):
    """tasks: [(overrides, n, seed0, tag)] → {tag: (wr, lo, invalid, avg_turns)}，带断点续跑。"""
    done = ckpt_load()
    out = {}
    todo = []
    for t in tasks:
        k = _ckpt_key(ckpt_phase, rd, fp, t[3])
        if k in done:
            out[t[3]] = done[k]
        else:
            todo.append(t)
    if out:
        print(f'  resume: {label} 已完成 {len(out)}/{len(tasks)}，跳过', flush=True)
    for res in pool.imap_unordered(_eval_task, todo):
        wr, lo, invalid, avg_turns, tag, err = res
        if err:
            emit({'ev': f'{ckpt_phase}_error', 'round': rd, 'tag': tag, 'error': err,
                  'msg': f'  [warn] {label} {tag} 异常: {err}，按 wr=0 处理'})
        if invalid != 0 and not err:
            emit({'ev': f'{ckpt_phase}_invalid', 'round': rd, 'tag': tag, 'invalid': invalid,
                  'msg': f'  [warn] {label} {tag} 非法动作 invalid={invalid}，拒绝'})
            wr, lo = 0.0, 0.0
        out[tag] = (wr, lo, invalid, avg_turns)
        ckpt_add(ckpt_phase, rd, fp, tag, wr, lo, invalid, avg_turns)
        print(f'  {label} {len(out)}/{len(tasks)} done: {tag} wr={wr:.4f}', flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--main-path', default=str(PROJ / 'main.py'))
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--screen-n', type=int, default=2000)
    ap.add_argument('--confirm-n', type=int, default=8000)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--manifest', default=None, help='JSON: {"params": [{"name","step"?}...]}')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--self-test-n', type=int, default=200)
    ap.add_argument('--dump-manifest', action='store_true')
    args = ap.parse_args()

    # 自检与清单派生都在主进程单实例上完成
    os.environ['PTCG_NN_MODE'] = 'off'
    probe = ar.load_module(Path(args.main_path))
    manifest = derive_manifest(probe)
    if args.manifest:
        spec = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
        only = {p['name'] for p in spec['params']}
        manifest = derive_manifest(probe, only=only)
        for p, s in zip(manifest, spec['params']):
            if 'step' in s:
                p['step'] = s['step']

    if args.dump_manifest:
        print(json.dumps({'params': manifest}, ensure_ascii=False, indent=1))
        return

    deck_fp = _fp(sorted(OUR_DECK))
    main_sha = hashlib.sha256(Path(args.main_path).read_bytes()).hexdigest()[:12]
    emit({'ev': 'start', 'ts': time.time(), 'n_params': len(manifest), 'main_sha': main_sha,
          'msg': f'=== param_tune start: rounds={args.rounds} screen_n={args.screen_n} '
                 f'confirm_n={args.confirm_n} params={len(manifest)} workers={args.workers} '
                 f'deck_fp={deck_fp} main_sha={main_sha} ==='})

    with mp.Pool(args.workers, initializer=_init_worker, initargs=(args.main_path,)) as pool:
        if args.self_test:
            # [2026-08-10 重校准] 旧探针 switch_core_bonus=-10000 按旧牌组(14宝可梦,
            # 含674)校准, 偏离 13.7pp; 现役牌组(8宝可梦, 677/678 单链) switch 决策
            # 权重塌缩, 旧探针偏离仅 ~1pp → 永久 FAIL (ledger#78 预存 bug)。
            # 新探针 play_can_attack_bonus=-10000: 真值 ~3pp (符号不稳但幅度稳,
            # self-test 用 abs)。注意跨进程残余熵 (worker spawn 级, hash 固定不可消)
            # 使实测在 [2.0, 4.5]pp 波动 → 阈值取 0.01 (1pp): 真效应最差实测 2.0pp
            # 有 2× 余量, 断线管道 Δ≈0.000-0.003 有 3× 余量。
            # ckpt fp 补 main_sha: 代码变更后旧自检缓存不再误用 (原键仅 deck_fp)。
            st_fp = _fp({'deck': deck_fp, 'main': main_sha})
            r0 = par_eval(pool, [({}, args.self_test_n, 1000, 'default_vs_default')],
                          'selftest', 0, st_fp, 'selftest')
            wr0 = r0['default_vs_default'][0]
            pert = {'play_can_attack_bonus': -10000}  # 现役牌组实测有稳定效应幅度的探针
            r1 = par_eval(pool, [(pert, args.self_test_n, 1000, 'perturb_can_attack_neg')],
                          'selftest', 0, st_fp, 'selftest')
            wr1 = r1['perturb_can_attack_neg'][0]
            ok_sym = abs(wr0 - 0.5) < 0.15
            ok_dev = abs(wr1 - wr0) > 0.01
            emit({'ev': 'self_test', 'default_wr': round(wr0, 4),
                  'perturbed_wr': round(wr1, 4), 'symmetry_ok': ok_sym, 'deviation_ok': ok_dev,
                  'msg': f'=== SELF-TEST: default vs default wr={wr0:.4f} (对称性 {"OK" if ok_sym else "FAIL"}), '
                         f'play_can_attack_bonus=-10000 wr={wr1:.4f} (扰动偏离 {"OK" if ok_dev else "FAIL"}) ==='})
            return

        incumbent = {}
        for rd in range(1, args.rounds + 1):
            fp = _fp({'deck': deck_fp, 'incumbent': incumbent, 'main': main_sha})
            emit({'ev': 'round_start', 'round': rd, 'incumbent': incumbent,
                  'msg': f'--- round {rd}: {len(manifest)} 参数 × ≤4 扰动，筛选 n={args.screen_n} ---'})

            # 筛选：每个参数的扰动点
            tasks = []
            for p in manifest:
                for v in perturbations(p):
                    ov = dict(incumbent)
                    ov[p['name']] = v
                    tasks.append((ov, args.screen_n, 1000, f"{p['name']}={v}"))
            scr = par_eval(pool, tasks, 'screen', rd, fp, 'screen')
            best_by_param = {}
            for p in manifest:
                cands = [(scr[f"{p['name']}={v}"][0], v) for v in perturbations(p)]
                cands.sort(reverse=True)
                best_by_param[p['name']] = cands[0]
            emit({'ev': 'screen_done', 'round': rd,
                  'msg': f'[round {rd}] 筛选完成，进入确认'})

            # 确认：每个参数最优扰动，独立种子
            ctasks = []
            for p in manifest:
                w0, v = best_by_param[p['name']]
                ov = dict(incumbent)
                ov[p['name']] = v
                ctasks.append((ov, args.confirm_n, 5000, p['name']))
            cfm = par_eval(pool, ctasks, 'confirm', rd, fp, 'confirm')

            accepts = []
            for p in manifest:
                wr, lo, invalid, turns = cfm[p['name']]
                w0, v = best_by_param[p['name']]
                emit({'ev': 'confirm', 'round': rd, 'param': p['name'], 'value': v,
                      'screen_wr': round(w0, 4), 'confirm_wr': round(wr, 4),
                      'ci_lo': round(lo, 4),
                      'msg': f'  confirm {p["name"]}={v}: screen={w0:.3f} confirm={wr:.4f} ci_lo={lo:.4f}'})
                if lo > 0.5:
                    accepts.append((wr, p['name'], v))
            if not accepts:
                emit({'ev': 'stop', 'round': rd,
                      'msg': f'[round {rd}] 无显著改进，停止'})
                break
            accepts.sort(reverse=True)
            for wr, name, v in accepts[:2]:  # 每轮最多接受 2 个，控制交互效应
                incumbent[name] = v
                emit({'ev': 'accept', 'round': rd, 'param': name, 'value': v,
                      'confirm_wr': round(wr, 4),
                      'msg': f'[round {rd}] ✓ 接受 {name}={v} (confirm wr={wr:.4f})'})
                with open(EXP / 'ledger.jsonl', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'ts': time.time(), 'event': 'param_tune_accept',
                                        'round': rd, 'param': name, 'value': v,
                                        'confirm_wr': round(wr, 4)}) + '\n')

        # 终验：incumbent vs default 镜像 + vs first + vs 冻结池
        if incumbent:
            fp = _fp({'deck': deck_fp, 'incumbent': incumbent, 'final': True, 'main': main_sha})
            fin = par_eval(pool, [(incumbent, args.confirm_n, 9000, 'mirror_vs_default')],
                           'final', 99, fp, 'final')
            wr, lo, invalid, turns = fin['mirror_vs_default']
            probe._apply_params(incumbent)  # 后续两个终验对局也必须带 incumbent 参数
            rf = ar.run_arena(probe.agent, ar.builtin_agent('first'), OUR_DECK, SAMPLE,
                              args.confirm_n, seed0=9000)
            nf = rf['wins'] + rf['losses'] + rf['draws']
            inc_vf = rf['wins'] / nf if nf else 0.0
            # [vs_first 回归门禁] default 公平对照 (同 n/seed/deck): 真实 Kaggle 指标
            # 是 vs_first, mirror 只是稳定性代理 — 堵 "mirror 涨 vs_first 跌" 的洞
            # (peer 2026-08-10 09:26 设计)。判据: vf_delta < -0.017 (1.7pp 噪声铁律)
            dflt = ar.load_module(Path(args.main_path))
            rd0 = ar.run_arena(dflt.agent, ar.builtin_agent('first'), OUR_DECK, SAMPLE,
                               args.confirm_n, seed0=9000)
            nd0 = rd0['wins'] + rd0['losses'] + rd0['draws']
            def_vf = rd0['wins'] / nd0 if nd0 else 0.0
            vf_delta = inc_vf - def_vf
            vf_regression = bool(vf_delta < -0.017)
            rp = ar.run_arena(probe.agent, ar.load_opponent('v23_2_rules'),
                              OUR_DECK, OUR_DECK, args.confirm_n, seed0=9000)
            npp = rp['wins'] + rp['losses'] + rp['draws']
            emit({'ev': 'param_tune_final', 'incumbent': incumbent,
                  'mirror_wr': round(wr, 4), 'mirror_ci_lo': round(lo, 4),
                  'vs_first_wr': round(inc_vf, 4),
                  'default_vs_first_wr': round(def_vf, 4),
                  'vf_delta': round(vf_delta, 4),
                  'vs_first_regression': vf_regression,
                  'vs_v23_2_wr': round(rp['wins'] / npp, 4),
                  'msg': f'=== FINAL: incumbent={incumbent} | mirror wr={wr:.4f} '
                         f'(ci_lo={lo:.4f}) | vs first={inc_vf:.4f} '
                         f'(default={def_vf:.4f} delta={vf_delta:+.4f} '
                         f'regression={vf_regression}) | '
                         f'vs v23_2={rp["wins"]/npp:.4f} ==='})
            with open(EXP / 'ledger.jsonl', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'ts': time.time(), 'event': 'param_tune_final',
                                    'incumbent': incumbent, 'mirror_wr': round(wr, 4),
                                    'mirror_ci_lo': round(lo, 4),
                                    'vs_first_wr': round(inc_vf, 4),
                                    'default_vs_first_wr': round(def_vf, 4),
                                    'vf_delta': round(vf_delta, 4),
                                    'vs_first_regression': vf_regression,
                                    'vs_v23_2_wr': round(rp['wins'] / npp, 4)}) + '\n')
            if vf_regression:
                # 回归 → 单独记账, 自动/人工合入须被挡下 (docstring 规定人工/kimi code 合入)
                with open(EXP / 'ledger.jsonl', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'ts': time.time(),
                                        'event': 'param_tune_rejected_regression',
                                        'incumbent': incumbent,
                                        'vs_first_wr': round(inc_vf, 4),
                                        'default_vs_first_wr': round(def_vf, 4),
                                        'vf_delta': round(vf_delta, 4),
                                        'reason': 'vs_first 回归超 1.7pp 噪声铁律, '
                                                  'incumbent 禁止合入 main.py'}) + '\n')
        else:
            emit({'ev': 'param_tune_final', 'incumbent': {},
                  'msg': '=== FINAL: 无参数变更 ==='})


if __name__ == '__main__':
    main()
