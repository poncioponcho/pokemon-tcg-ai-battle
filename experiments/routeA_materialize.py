#!/usr/bin/env python3
"""Materialize a Route-A candidate only after every preregistered W/L gate."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.candidate_h2h import BASELINE as V22, CandidateAgent, assert_locked_baseline, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


IMPORT_MARKER = "from .strategic_memory import StrategicMemory\n"
RESET_MARKER = """    if select is None:
        _HISTORY = []
        _STRATEGIC_MEMORY.reset()
        return read_deck_csv()
"""
RESET_REPLACEMENT = """    if select is None:
        _HISTORY = []
        _STRATEGIC_MEMORY.reset()
        routeA_reset()
        return read_deck_csv()
"""
ACTION_MARKER = """    action = apply_manual_guards(obs_dict)
    if action is None:
        action = choose(state, options, _HISTORY, _STRATEGIC_MEMORY)
"""
ACTION_REPLACEMENT = """    action = apply_manual_guards(obs_dict)
    if action is None:
        action = choose(state, options, _HISTORY, _STRATEGIC_MEMORY)
        action = routeA_maybe_override(state, options, _HISTORY, action)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", required=True)
    parser.add_argument("--main-gate", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    assert_locked_baseline()
    canary_path = pathlib.Path(args.canary).resolve()
    gate_path = pathlib.Path(args.main_gate).resolve()
    out_dir = pathlib.Path(args.out_dir).resolve()
    canary = json.loads(canary_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if canary.get("verdict") != "PASS_TO_WL_SCREEN":
        raise SystemExit("Route-A canary not promotable")
    if gate.get("verdict") != "PASS_TO_ARCHIVE":
        raise SystemExit("Route-A n=256 main gate not promotable")
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite candidate directory: {out_dir}")
    reservation = reserve_json_output(args.report)
    source_tree = tree_sha256(V22)
    started = time.time()
    shutil.copytree(V22, out_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    policy_dir = out_dir / "policies" / "v22"
    shutil.copy2(ROOT / "experiments" / "routeA_runtime_head.py", policy_dir / "routeA_head.py")
    model_path = policy_dir / "routeA_model.json"
    model_path.write_text(
        json.dumps(canary["trained_model"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    main_path = policy_dir / "main.py"
    main_source = main_path.read_text(encoding="utf-8")
    if main_source.count(IMPORT_MARKER) != 1 or main_source.count(RESET_MARKER) != 1 or main_source.count(ACTION_MARKER) != 1:
        raise SystemExit("exact-v22 main markers changed; refusing Route-A materialization")
    main_source = main_source.replace(
        IMPORT_MARKER,
        IMPORT_MARKER + "from .routeA_head import maybe_override as routeA_maybe_override, reset as routeA_reset\n",
    )
    main_source = main_source.replace(RESET_MARKER, RESET_REPLACEMENT)
    main_source = main_source.replace(ACTION_MARKER, ACTION_REPLACEMENT)
    main_path.write_text(main_source, encoding="utf-8")

    candidate = CandidateAgent(out_dir)
    deck = candidate.deck()
    if len(deck) != 60:
        raise SystemExit("materialized Route-A candidate deck invalid")
    if tree_sha256(V22) != source_tree:
        raise SystemExit("exact-v22 source changed during Route-A materialization")
    report = {
        "created_unix": time.time(),
        "method": "routeA-gated-candidate-materialization-v1",
        "source_tree_sha256": source_tree,
        "source_canary": str(canary_path),
        "source_canary_sha256": sha256(canary_path),
        "source_main_gate": str(gate_path),
        "source_main_gate_sha256": sha256(gate_path),
        "candidate_dir": str(out_dir),
        "candidate_tree_sha256": tree_sha256(out_dir),
        "candidate_main_sha256": sha256(out_dir / "main.py"),
        "candidate_deck_sha256": sha256(out_dir / "deck.csv"),
        "routeA_main_sha256": sha256(main_path),
        "routeA_head_sha256": sha256(policy_dir / "routeA_head.py"),
        "routeA_model_sha256": sha256(model_path),
        "deck_cards": len(deck),
        "source_untouched": True,
        "submitted": False,
        "elapsed_s": round(time.time() - started, 6),
    }
    reservation.write(report)
    print(
        f"Route-A materialized candidate={out_dir} tree={report['candidate_tree_sha256']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
