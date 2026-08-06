"""Run a small AWR hyperparameter sweep from one fixed BC checkpoint.

Each trial has its own output/log directory and reads the same full tensor
directory. No data is downloaded and no BC retraining is performed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_CONFIGS = [
    {"name": "awr_t02_cap50_lr5e-4", "tau": 0.2, "wcap": 50, "lr": 0.0005, "bs": 2048},
    {"name": "awr_t02_cap100_lr1e-4", "tau": 0.2, "wcap": 100, "lr": 0.0001, "bs": 2048},
    {"name": "awr_t03_cap50_lr5e-4", "tau": 0.3, "wcap": 50, "lr": 0.0005, "bs": 2048},
    {"name": "awr_t05_cap20_lr5e-4", "tau": 0.5, "wcap": 20, "lr": 0.0005, "bs": 4096},
]


def run_trial(args, config, output_root):
    trial_dir = output_root / config['name']
    trial_dir.mkdir(parents=True, exist_ok=True)
    model_output = trial_dir / 'model_awr.pt'
    best_output = trial_dir / 'model_awr.best.pt'
    command = [
        sys.executable, str(Path(args.train_script)),
        '--phase', 'awr',
        '--resume-from', args.bc_model,
        '--data-dir', args.data_dir,
        '--logs-dir', str(trial_dir / 'logs'),
        '--model-output', str(model_output),
        '--best-model-output', str(best_output),
        '--epochs-awr', str(args.epochs),
        '--early-stop-patience', str(args.patience),
        '--early-stop-min-delta', str(args.min_delta),
        '--tau', str(config['tau']),
        '--wcap', str(config['wcap']),
        '--lr', str(config['lr']),
        '--bs', str(config['bs']),
        '--device', args.device,
    ]
    if args.sample_index:
        command.extend(['--sample-index', args.sample_index])
    if args.sample_weights:
        command.extend(['--sample-weights', args.sample_weights])
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=Path(args.train_script).resolve().parents[2],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=args.timeout,
    )
    result = {
        'config': config,
        'returncode': completed.returncode,
        'seconds': round(time.time() - started, 2),
        'output_tail': completed.stdout[-3000:],
    }
    report_path = Path(args.data_dir) / 'eval_report.json'
    if completed.returncode == 0 and report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
        result['fixed_test'] = report.get('fixed_test', {}).get('ev', {})
        result['canary'] = report.get('rolling_canary', {}).get('ev', {})
        result['model'] = str(model_output)
    (trial_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description='AWR parameter sweep from fixed BC')
    parser.add_argument('--data-dir', default=str(root / 'data'))
    parser.add_argument('--bc-model', default=str(root / 'data' / 'model_bc.pt'))
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--train-script', default=str(root / 'train_bc.py'))
    parser.add_argument('--configs', default=None, help='JSON list of trial config objects')
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--patience', type=int, default=5)
    parser.add_argument('--min-delta', type=float, default=0.0001)
    parser.add_argument('--sample-index', default=None)
    parser.add_argument('--sample-weights', default=None)
    parser.add_argument('--device', choices=('auto', 'cpu', 'mps'), default='auto')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    configs = json.loads(Path(args.configs).read_text()) if args.configs else DEFAULT_CONFIGS
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    results = [run_trial(args, config, output_root) for config in configs]
    summary = output_root / 'summary.json'
    summary.write_text(json.dumps({'results': results}, indent=2) + '\n', encoding='utf-8')
    for result in results:
        print(result['config']['name'], result['returncode'], result.get('fixed_test', {}))
    return 0 if all(result['returncode'] == 0 for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
