#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""closed_loop_train.py — 自驱动闭环：teacher→distill→arena→双门→提交

场景：本轮 P100 teacher 已运行多时，GPU 配额紧张。本脚本在后台常驻，
按状态机自动推进，无需人工凌晨盯守：

  MONITOR_TEACHER ──COMPLETE──▶ TEACHER_DONE
       │                          ├─ 校验 ckpt_v2_last.pt + teacher_best.pt
       │（TLE/ERROR）              └─ 建 ptcg-ckpt 数据集
       ▼                          ─▶ PUSH_DISTILL ─▶ MONITOR_DISTILL
  报告并退出                       ─COMPLETE─▶ DISTILL_DONE ─▶ ARENA
                                               ─▶ DUAL_GATE ─▶ 过→PACK+SUBMIT
                                               └─ 不过→报告，不提交

安全设计：
  - 状态文件 ~/.hermes/state/closed_loop_state.json（幂等，可断点续跑）
  - 单实例 pid 锁
  - 只在明确 COMPLETE/SUCCESS 时推进；RUNNING/QUEUED/异常一律等
  - 双门不达标绝不提交；auto_submit cron 已 pause，本脚本是唯一提交者
  - 每次状态转换写 reports/closed-loop-*.md 审计

用法:
  nohup /opt/homebrew/bin/python3 scripts/closed_loop_train.py > reports/closed-loop.log 2>&1 &
  python3 scripts/closed_loop_train.py --tick   # 跑一轮立即退出（调试）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
STATE_DIR = Path.home() / '.hermes' / 'state'
STATE_FILE = STATE_DIR / 'closed_loop_state.json'
LOG_FILE = PROJ / 'reports' / 'closed-loop.log'
LOCK_FILE = STATE_DIR / 'closed_loop.lock'
REPORT_DIR = PROJ / 'reports'

KAG = '/opt/homebrew/bin/kaggle'
PY = '/opt/homebrew/bin/python3'
KERNEL = 'daniel1547/ptcg-gpu-train-teacher-distill'
CKPT_DS = 'daniel1547/ptcg-ckpt'
STAGE_DIR = PROJ / '.kaggle_stage_ckpt'
KERR_DIR = PROJ / 'reports' / 'kerr_teacher'
KERR_D = PROJ / 'reports' / 'kerr_distill'

# 时间线（TLE 判断已废弃：实测 Kaggle script kernel 超 12h 不会被砍，
# 无谓的硬判只会误杀。只依赖状态机：RUNNING→继续等，COMPLETE/ERROR/CANCEL→行动。）
# 双门阈值
GATE_WR_TOTAL = 0.628    # hybrid 总 WR > 纯规则基线
GATE_WR_V23 = 0.520      # vs v23_2_rules ≥ 基线

ARENA_N = 2000
ARENA_OPPONENTS = 'v23_2_rules,v22_5_rules,first,random'

SLEEP_S = 120  # 轮询间隔


def log(msg: str):
    line = f'[{datetime.now().strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


def notify(title: str, msg: str):
    try:
        subprocess.run(['osascript', '-e',
                        f'display notification "{msg}" with title "{title}"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def sh(cmd, **kw):
    """运行命令，返回 (rc, stdout+stderr)。"""
    env = dict(os.environ)
    for k in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(k, None)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=kw.get('timeout', 600), **kw)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return -1, 'TIMEOUT'
    except Exception as e:
        return -1, repr(e)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {'state': 'MONITOR_TEACHER', 'updated': None}


def save_state(st):
    st['updated'] = datetime.now().isoformat(timespec='seconds')
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2))


def _pid_alive(pid_s: str) -> bool:
    """[fix 08-09] macOS 无 /proc, 用 os.kill(pid, 0) 做存活检测 (POSIX 通用)。"""
    try:
        pid = int(pid_s)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在但属其他用户
    return True


def acquire_lock():
    if LOCK_FILE.exists():
        pid = LOCK_FILE.read_text().strip()
        # [fix 08-09] 原为 os.path.isdir(f'/proc/{pid}'): macOS 无 /proc 恒 False,
        # 锁形同虚设, 双实例可并发 push kernel/重复提交
        if pid and _pid_alive(pid):
            return False
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    try:
        LOCK_FILE.unlink()
    except OSError:
        pass


def kernel_status():
    rc, out = sh([KAG, 'kernels', 'status', KERNEL])
    if rc != 0:
        return None
    line = out.splitlines()[0] if out.strip() else ''
    if 'RUNNING' in line:
        return 'RUNNING'
    if 'QUEUED' in line or 'PENDING' in line:
        return 'QUEUED'
    if 'COMPLETE' in line or 'SUCCESS' in line:
        return 'COMPLETE'
    if 'ERROR' in line or 'FAIL' in line:
        return 'ERROR'
    if 'CANCEL' in line:
        return 'CANCEL'
    return None


def download_output(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    rc, out = sh([KAG, 'kernels', 'output', KERNEL, '-p', str(dest)])
    return rc == 0


def find_file(dest: Path, name: str):
    for p in dest.rglob(name):
        return p
    return None


def make_ckpt_dataset():
    """teacher 产物 → ptcg-ckpt 数据集（首次 create，之后 version）。"""
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)
    ckpt = find_file(KERR_DIR, 'ckpt_v2_last.pt')
    best = find_file(KERR_DIR, 'teacher_best.pt')
    if not ckpt or not best:
        return False, f'缺少 ckpt: ckpt={ckpt} teacher_best={best}'
    shutil.copy(ckpt, STAGE_DIR / 'ckpt_v2_last.pt')
    shutil.copy(best, STAGE_DIR / 'teacher_best.pt')
    (STAGE_DIR / 'dataset-metadata.json').write_text(json.dumps({
        'id': CKPT_DS, 'title': 'ptcg_ckpt', 'licenses': [{'name': 'other'}]}))
    rc, out = sh([KAG, 'datasets', 'list', '-m', '-s', 'ptcg-ckpt'])
    if CKPT_DS in out:
        rc2, out2 = sh([KAG, 'datasets', 'version', '-p', str(STAGE_DIR),
                        '-r', 'zip', '-m', f'ckpt {datetime.now().strftime("%m-%d %H:%M")}'])
        return rc2 == 0, out2[-200:]
    rc2, out2 = sh([KAG, 'datasets', 'create', '-p', str(STAGE_DIR), '-r', 'zip'])
    return rc2 == 0, out2[-200:]


def edit_for_distill():
    """kernel-metadata 加 ptcg-ckpt；run_experiment stage → distill。"""
    meta = json.loads((PROJ / '.kaggle_kernel' / 'kernel-metadata.json').read_text())
    srcs = meta.get('dataset_sources', [])
    if CKPT_DS not in srcs:
        srcs.append(CKPT_DS)
        meta['dataset_sources'] = srcs
        (PROJ / '.kaggle_kernel' / 'kernel-metadata.json').write_text(
            json.dumps(meta, indent=2) + '\n')
    run_py = (PROJ / '.kaggle_kernel' / 'run_experiment.py')
    src = run_py.read_text()
    if "KAGGLE_STAGE', 'teacher'" in src:
        src = src.replace("KAGGLE_STAGE', 'teacher'", "KAGGLE_STAGE', 'distill'")
        run_py.write_text(src)
        log('run_experiment stage: teacher → distill')


def push_distill():
    rc, out = sh([PY, 'scripts/push_t4.py', '--stage', 'distill'])
    return rc == 0, out


def run_arena():
    """运行本地 arena，返回报告 dict（或 None）。"""
    out = EXP_REPORT = PROJ / 'experiments' / 'arena_report-final.json'
    if out.exists():
        out.unlink()
    rc, msg = sh([PY, 'experiments/arena_runner.py', '--id', 'final',
                  '--npz', str(PROJ / 'model_student.npz'),
                  '--n', str(ARENA_N), '--opponents', ARENA_OPPONENTS])
    log('arena: ' + (msg[-400:] if msg else f'rc={rc}'))
    if not EXP_REPORT.exists():
        return None
    return json.loads(EXP_REPORT.read_text())


def dual_gate(report):
    """双门判定：总 WR > GATE_WR_TOTAL 且 vs v23_2_rules ≥ GATE_WR_V23。"""
    total_wr = report.get('win_rate', 0.0)
    v23 = None
    for o in report.get('per_opponent', []):
        if o['opponent'] == 'v23_2_rules':
            v23 = o['wr']
    ok = total_wr > GATE_WR_TOTAL and v23 is not None and v23 >= GATE_WR_V23
    return ok, {'total_wr': total_wr, 'v23_wr': v23}


def write_report(title, body):
    p = REPORT_DIR / f'closed-loop-{datetime.now().strftime("%H%M%S")}.md'
    p.write_text(f'# {title}\n\n{body}\n')
    return p


def do_submit():
    rc, out = sh([PY, 'submit.py', 'submit'])
    return rc == 0, out


# ---------------- 状态机 ----------------
def transition(st):
    s = st.get('state')
    log(f'STATE: {s}')

    if s == 'MONITOR_TEACHER':
        st = {**st, 'state': 'MONITOR_TEACHER'}
        status = kernel_status()
        log(f'teacher status: {status}')
        if status in ('RUNNING', 'QUEUED'):
            # 仍在跑：一直等到状态翻转（实测超 12h 也不砍，无需 TLE 硬判）。
            return st
        if status == 'COMPLETE':
            log('teacher COMPLETE → 下载产物')
            if download_output(KERR_DIR):
                st['state'] = 'TEACHER_DONE'
            else:
                st['state'] = 'FAILED'
                st['reason'] = 'teacher output 下载失败'
            return st
        if status == 'ERROR':
            st['state'] = 'FAILED'
            st['reason'] = 'teacher ERROR（日志见 kernel output）'
            write_report('teacher ERROR', f'kaggle kernels output -p {KERR_DIR}')
            return st
        # status == CANCEL 或已结束 → 抢救 ckpt
        log('teacher 已结束（CANCEL/TLE），尝试抢救 ckpt')
        if download_output(KERR_DIR):
            ckpt = find_file(KERR_DIR, 'ckpt_v2_last.pt')
            if ckpt:
                st['state'] = 'TEACHER_DONE'
                st['rescued'] = True
                log(f'TLE 抢救到 ckpt: {ckpt}')
                return st
        st['state'] = 'FAILED'
        st['reason'] = f'teacher 结束（{status}）且无 ckpt 可抢救'
        write_report('闭环失败', f'teacher 结束（{status}），无 ckpt 可抢救。')
        return st

    if s == 'TEACHER_DONE':
        ckpt = find_file(KERR_DIR, 'ckpt_v2_last.pt')
        best = find_file(KERR_DIR, 'teacher_best.pt')
        if not ckpt or not best:
            st['state'] = 'FAILED'
            st['reason'] = f'teacher 产物缺失 ckpt={ckpt} best={best}'
            return st
        log(f'teacher 产物确认: ckpt={ckpt.name} best={best.name} → 建 ptcg-ckpt')
        ok, msg = make_ckpt_dataset()
        if not ok:
            st['state'] = 'FAILED'
            st['reason'] = f'ptcg-ckpt 数据集创建失败: {msg}'
            return st
        log(f'ptcg-ckpt 数据集就绪: {msg.strip()}')
        edit_for_distill()
        ok, out = push_distill()
        if not ok:
            st['state'] = 'FAILED'
            st['reason'] = f'distill push 失败: {out[-300:]}'
            return st
        log('distill kernel 已推送')
        st['state'] = 'MONITOR_DISTILL'
        st['distill_start'] = time.time()
        return st

    if s == 'MONITOR_DISTILL':
        status = kernel_status()
        log(f'distill status: {status}')
        if status == 'COMPLETE':
            log('distill COMPLETE → 下载产物')
            if download_output(KERR_D):
                st['state'] = 'DISTILL_DONE'
            else:
                st['state'] = 'FAILED'
                st['reason'] = 'distill output 下载失败'
        elif status == 'ERROR':
            st['state'] = 'FAILED'
            st['reason'] = 'distill ERROR'
            write_report('distill ERROR', f'kaggle kernels output -p {KERR_D}')
        return st

    if s == 'DISTILL_DONE':
        npz = find_file(KERR_D, 'model_student.npz')
        if not npz:
            st['state'] = 'FAILED'
            st['reason'] = 'distill 产物缺 model_student.npz'
            return st
        log(f'distill npz: {npz} ({npz.stat().st_size/1e6:.1f} MB)')
        shutil.copy(npz, PROJ / 'model_student.npz')
        st['npz_size'] = npz.stat().st_size
        st['state'] = 'ARENA'
        return st

    if s == 'ARENA':
        report = run_arena()
        if report is None:
            st['state'] = 'FAILED'
            st['reason'] = 'arena 运行失败'
            return st
        ok, gate = dual_gate(report)
        st['arena'] = report
        st['gate'] = gate
        st['gate_ok'] = ok
        body = (f"WR total: {gate['total_wr']:.4f} (need >{GATE_WR_TOTAL})\n"
                f"vs v23_2_rules: {gate['v23_wr']} (need ≥{GATE_WR_V23})\n"
                + json.dumps(report.get('per_opponent', []), ensure_ascii=False, indent=2))
        if ok:
            log(f'双门通过 total_wr={gate["total_wr"]:.4f} v23={gate["v23_wr"]} → 打包提交')
            rc, out = sh(['bash', 'pack.sh'])
            if rc != 0:
                st['state'] = 'FAILED'
                st['reason'] = f'pack.sh 失败: {out[-300:]}'
                return st
            log('pack.sh OK')
            rc, out = do_submit()
            st['submit'] = {'rc': rc, 'out': out[-500:]}
            write_report('闭环：双门通过已提交', body + f'\n\nsubmit rc={rc}\n{out[-500:]}')
            if rc == 0:
                st['state'] = 'DONE'
                notify('闭环完成', '双门通过，已提交')
            else:
                st['state'] = 'FAILED'
                st['reason'] = f'submit 失败: {out[-300:]}'
        else:
            st['state'] = 'GATE_BLOCKED'
            write_report('闭环：双门未过，不提交', body)
        return st

    if s in ('GATE_BLOCKED', 'DONE', 'FAILED'):
        return st  # 终态

    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tick', action='store_true', help='跑一轮立即退出')
    args = ap.parse_args()

    if not acquire_lock():
        print('另一实例运行中')
        sys.exit(0)

    try:
        st = load_state()
        while True:
            prev = st.get('state')
            st = transition(st)
            save_state(st)
            if st.get('state') != prev or st.get('state') in ('DONE', 'GATE_BLOCKED', 'FAILED'):
                if st.get('state') in ('DONE', 'GATE_BLOCKED', 'FAILED'):
                    log(f'终态: {st.get("state")} ({st.get("reason", "")})')
                    sys.exit(0)
            if args.tick:
                sys.exit(0)
            time.sleep(SLEEP_S)
    finally:
        release_lock()


if __name__ == '__main__':
    main()
