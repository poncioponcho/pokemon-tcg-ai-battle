"""Evaluate trained NN policy vs current rule agent on real replay observations.

Loads a sample of leaderboard replay decisions, runs both the NN policy
(inference/dataset/agent.py) and the rule agent (main.agent) on the exact
observation dicts, and reports legality, agreement with the actual top-player
action, and per-context breakdowns. Pure evaluation; no data is modified.
"""
import json, os, random, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'inference/dataset'))

import numpy as np
import torch

import main as rule_agent
import agent as nn_agent

RAW = PROJECT_ROOT / 'inference/leaderboard_replay/raw'


def load_obs_actions(limit_episodes=40, seed=42):
    """Yield (obs_dict, actual_action_list, context) from a random episode sample."""
    files = sorted(RAW.glob('episode-*-replay.json'))
    rng = random.Random(seed)
    chosen = rng.sample(files, min(limit_episodes, len(files)))
    for path in chosen:
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        for step in payload.get('steps', []):
            if not isinstance(step, list):
                continue
            for view in step:
                obs = view.get('observation')
                if not isinstance(obs, dict) or obs.get('select') is None:
                    continue
                action = view.get('action')
                if not isinstance(action, list) or not action:
                    continue
                yield obs, action, obs['select'].get('context')


def sanitize(agent_result, n_options):
    result = [int(i) for i in agent_result]
    result = [i for i in result if 0 <= i < n_options]
    return result


def run():
    model = nn_agent.load_model()
    rows = list(load_obs_actions())
    stats = {'n': 0, 'rule_legal': 0, 'nn_legal': 0, 'rule_exact': 0, 'nn_exact': 0,
             'rule_in_actual': 0, 'nn_in_actual': 0}
    per_ctx = {}
    for obs, actual, ctx in rows:
        select = obs['select']
        n_opts = len(select.get('option') or [])
        if n_opts == 0:
            continue
        stats['n'] += 1
        rule_a = sanitize(rule_agent.agent(obs), n_opts)
        nn_a = sanitize(nn_agent.agent(obs, model=model), n_opts)
        actual = [i for i in actual if 0 <= i < n_opts]
        r_legal = bool(rule_a)
        n_legal = bool(nn_a)
        r_exact = r_legal and sorted(rule_a) == sorted(actual)
        n_exact = n_legal and sorted(nn_a) == sorted(actual)
        stats['rule_legal'] += int(r_legal)
        stats['nn_legal'] += int(n_legal)
        stats['rule_exact'] += int(r_exact)
        stats['nn_exact'] += int(n_exact)
        stats['rule_in_actual'] += int(any(i in actual for i in rule_a))
        stats['nn_in_actual'] += int(any(i in actual for i in nn_a))
        entry = per_ctx.setdefault(str(ctx), {'n': 0, 'rule_exact': 0, 'nn_exact': 0,
                                              'rule_in': 0, 'nn_in': 0})
        entry['n'] += 1
        entry['rule_exact'] += int(r_exact)
        entry['nn_exact'] += int(n_exact)
        entry['rule_in'] += int(any(i in actual for i in rule_a))
        entry['nn_in'] += int(any(i in actual for i in nn_a))
    n = stats['n']
    summary = {
        'decisions_evaluated': n,
        'rule_agent': {
            'legal_rate': stats['rule_legal'] / n,
            'exact_match_rate': stats['rule_exact'] / n,
            'any_chosen_in_actual_rate': stats['rule_in_actual'] / n,
        },
        'nn_policy': {
            'legal_rate': stats['nn_legal'] / n,
            'exact_match_rate': stats['nn_exact'] / n,
            'any_chosen_in_actual_rate': stats['nn_in_actual'] / n,
        },
    }
    ctx_report = {}
    for ctx, e in sorted(per_ctx.items(), key=lambda kv: -kv[1]['n']):
        if e['n'] < 50:
            continue
        ctx_report[ctx] = {
            'n': e['n'],
            'rule_exact': e['rule_exact'] / e['n'],
            'nn_exact': e['nn_exact'] / e['n'],
            'rule_in_actual': e['rule_in'] / e['n'],
            'nn_in_actual': e['nn_in'] / e['n'],
        }
    summary['per_context'] = ctx_report
    out = Path(__file__).resolve().parent / 'logs' / 'nn_vs_rule_eval.json'
    out.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    run()
