#!/usr/bin/env python3
"""Candidate delivery loop for the last-mile Kaggle race.

The historical ``pack.sh``/``submit.py`` pair is intentionally root-bound:
it refuses an archive unless it contains the current (often unrelated) root
``main.py``.  That is useful for a single incumbent, but it makes independent
strategy families impossible to ship safely.  This tool treats a candidate
directory as the unit of delivery and records immutable hashes beside the
archive.

Typical use:

  python3 scripts/candidate_delivery.py validate --candidate-dir candidates/grimmsnarl_v1
  python3 scripts/candidate_delivery.py pack --candidate-dir candidates/grimmsnarl_v1 \
      --output artifacts/grimmsnarl_v1.tar.gz
  python3 scripts/candidate_delivery.py submit --archive artifacts/grimmsnarl_v1.tar.gz \
      --description 'cross-family grimmsnarl v1'

Only standard-library validation/packaging is required locally.  The submit
subcommand uses the installed ``kagglesdk`` and never prints credentials.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from collections import Counter
from contextlib import contextmanager
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ENGINE = ROOT / "inference/comp_data/sample_submission/sample_submission"
DEFAULT_RECORD = ROOT / "reports/candidate_delivery.jsonl"
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def files_for(candidate: pathlib.Path) -> list[pathlib.Path]:
    if not candidate.is_dir():
        raise SystemExit(f"candidate directory missing: {candidate}")
    files = []
    for path in candidate.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(candidate)
        if any(part in SKIP_PARTS for part in rel.parts) or path.suffix in SKIP_SUFFIXES:
            continue
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe candidate path: {rel}")
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(candidate).as_posix())


def read_deck(candidate: pathlib.Path) -> list[int]:
    deck_path = candidate / "deck.csv"
    if not deck_path.is_file():
        raise SystemExit(f"candidate missing deck.csv: {deck_path}")
    try:
        deck = [int(line.strip()) for line in deck_path.read_text().splitlines() if line.strip()]
    except ValueError as exc:
        raise SystemExit(f"deck.csv contains a non-integer: {exc}") from exc
    if len(deck) != 60:
        raise SystemExit(f"deck.csv must contain exactly 60 cards, got {len(deck)}")
    return deck


def card_legality(candidate: pathlib.Path, deck: list[int]) -> dict[str, Any]:
    """Check IDs/copy limits when the candidate carries the official card CSV."""
    data_path = candidate / "EN_Card_Data.csv"
    if not data_path.is_file():
        data_path = ROOT / "inference/comp_data/EN Card Data.csv"
    if not data_path.is_file():
        return {"checked": False, "reason": "card data unavailable"}
    import csv

    with data_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    by_id = {int(row["Card ID"]): row for row in rows if row.get("Card ID")}
    unknown = sorted(set(deck) - set(by_id))
    if unknown:
        raise SystemExit(f"unknown card IDs: {unknown}")
    counts = Counter(deck)
    # Basic energy is exempt from the four-copy rule.  ACE SPEC remains unique.
    over = []
    ace = []
    for cid, count in counts.items():
        row = by_id[cid]
        stage = (row.get("Stage (Pokémon)/Type (Energy and Trainer)") or "").lower()
        rule = (row.get("Rule") or "").upper()
        if "energy" not in stage and count > 4:
            over.append([cid, count])
        if "ACE SPEC" in rule:
            ace.extend([cid] * count)
    if over:
        raise SystemExit(f"non-energy card exceeds four copies: {over}")
    if len(set(ace)) > 1 or len(ace) > 1:
        raise SystemExit(f"ACE SPEC uniqueness violation: {sorted(set(ace))}")
    return {"checked": True, "card_rows": len(rows), "unknown": [], "copy_limit": "PASS"}


def clean_copy(candidate: pathlib.Path) -> pathlib.Path:
    """Copy into a fresh directory so imports cannot see repo-local files."""
    temp = pathlib.Path(tempfile.mkdtemp(prefix="ptcg_candidate_validate_", dir="/private/tmp"))
    for source in files_for(candidate):
        target = temp / source.relative_to(candidate)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return temp


@contextmanager
def candidate_runtime(candidate: pathlib.Path, engine_root: pathlib.Path):
    """Mirror Kaggle's candidate-local cwd/import path for agent execution."""
    old_cwd = pathlib.Path.cwd()
    old_path = list(sys.path)
    sys.path.insert(0, str(candidate))
    sys.path.insert(0, str(engine_root))
    try:
        os.chdir(candidate)
        yield
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path


def load_entrypoint(candidate: pathlib.Path, engine_root: pathlib.Path):
    """Load normal ``agent`` and Kaggle's __file__-less last callable."""
    if not (candidate / "main.py").is_file():
        raise SystemExit("candidate missing main.py")
    with candidate_runtime(candidate, engine_root):
        # A unique module name avoids accidentally reusing a prior candidate.
        spec = importlib.util.spec_from_file_location(
            f"ptcg_candidate_{time.time_ns()}", candidate / "main.py"
        )
        if spec is None or spec.loader is None:
            raise SystemExit("cannot create import spec for main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module_fn = getattr(module, "agent", None)

        # Kaggle's released loader executes source without defining __file__
        # and chooses the last public callable in insertion order.  Always
        # exercise that path: checking it only when ``agent`` is absent misses
        # candidates with an intentionally final wrapper.
        namespace = {"__name__": "__ptcg_fresh_probe__", "__builtins__": __builtins__}
        source = (candidate / "main.py").read_text(encoding="utf-8")
        exec(compile(source, "main.py", "exec"), namespace)
        callables = [
            (key, value) for key, value in namespace.items()
            if not key.startswith("__") and callable(value)
        ]
        if not callables:
            raise SystemExit("main.py exposes no callable entrypoint")
        loader_name, loader_fn = callables[-1]
        if not callable(module_fn):
            module_fn = loader_fn
        return module, module_fn, loader_name, loader_fn, [key for key, _ in callables[-8:]]


def probe_startup(fn, startup_obs: dict[str, Any], expected_deck: list[int],
                  count: int, label: str) -> list[int]:
    startup = fn(startup_obs)
    if not isinstance(startup, list) or len(startup) != 60:
        raise SystemExit(f"{label} startup did not return 60-card deck: {startup!r}")
    try:
        matches = sorted(int(x) for x in startup) == sorted(expected_deck)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{label} startup deck contains invalid values: {exc}") from exc
    if not matches:
        raise SystemExit(f"{label} startup deck differs from deck.csv")
    starts = []
    for _ in range(max(1, count)):
        got = fn(startup_obs)
        starts.append(len(got) if isinstance(got, list) else None)
    if any(x != 60 for x in starts):
        raise SystemExit(f"{label} startup probe failed: {starts}")
    return starts


def validate(args: argparse.Namespace) -> dict[str, Any]:
    candidate = pathlib.Path(args.candidate_dir).resolve()
    deck = read_deck(candidate)
    legality = card_legality(candidate, deck)
    clean = clean_copy(candidate)
    try:
        engine_root = pathlib.Path(args.engine_root).resolve()
        module, module_fn, loader_name, loader_fn, callable_tail = load_entrypoint(
            clean, engine_root
        )
        # The released SDK's Observation dataclass requires ``logs`` even for
        # the initial deck request.  Public agents vary in how much of that
        # empty envelope they inspect, so use the faithful envelope here.
        startup_obs = {"select": None, "logs": [], "current": None,
                       "search_begin_input": None}
        with candidate_runtime(clean, engine_root):
            module_starts = probe_startup(
                module_fn, startup_obs, deck, args.startup_probes, "module agent"
            )
            loader_starts = probe_startup(
                loader_fn, startup_obs, deck, args.startup_probes,
                f"Kaggle last callable {loader_name}",
            )
        main_sha = sha256(candidate / "main.py")
        deck_sha = sha256(candidate / "deck.csv")
        manifest = {
            "candidate_dir": str(candidate),
            "main_sha256": main_sha,
            "deck_sha256": deck_sha,
            "entrypoint": loader_name,
            "module_entrypoint": getattr(module_fn, "__name__", type(module_fn).__name__),
            "callable_tail": callable_tail,
            "deck_count": len(deck),
            "startup_probes": loader_starts,
            "module_startup_probes": module_starts,
            "files": [
                {"path": str(p.relative_to(candidate)), "sha256": sha256(p), "bytes": p.stat().st_size}
                for p in files_for(candidate)
            ],
            "card_legality": legality,
            "status": "PASS",
        }
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return manifest
    finally:
        shutil.rmtree(clean, ignore_errors=True)


def pack(args: argparse.Namespace) -> dict[str, Any]:
    candidate = pathlib.Path(args.candidate_dir).resolve()
    # Reuse all checks before creating an artifact.
    validation = validate(argparse.Namespace(
        candidate_dir=str(candidate), engine_root=args.engine_root, startup_probes=2
    ))
    output = pathlib.Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    tmp.unlink(missing_ok=True)
    candidate_files = files_for(candidate)
    archive_files = {
        source.relative_to(candidate).as_posix(): source
        for source in candidate_files
    }
    if not args.no_cg:
        cg_root = pathlib.Path(args.engine_root).resolve() / "cg"
        if not cg_root.is_dir():
            raise SystemExit(f"official cg runtime missing: {cg_root}")
        for source in files_for(cg_root):
            rel = "cg/" + source.relative_to(cg_root).as_posix()
            # A candidate may intentionally ship a pinned runtime; keep it.
            archive_files.setdefault(rel, source)
    archive_files = dict(sorted(archive_files.items()))
    # ``tarfile.open(..., 'w:gz')`` embeds the current time in the gzip header
    # even when every TarInfo.mtime is zero.  Build the two layers explicitly so
    # byte-identical candidates produce byte-identical archives and audit SHAs.
    with tmp.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tf:
                for rel, source in archive_files.items():
                    info = tarfile.TarInfo(rel)
                    data = source.read_bytes()
                    info.size = len(data)
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mode = 0o644
                    tf.addfile(info, io.BytesIO(data))
    tmp.replace(output)
    archive_sha = sha256(output)
    manifest = {
        "artifact": str(output),
        "archive_sha256": archive_sha,
        "archive_bytes": output.stat().st_size,
        "main_sha256": validation["main_sha256"],
        "deck_sha256": validation["deck_sha256"],
        "entrypoint": validation["entrypoint"],
        "member_count": len(archive_files),
        "members": list(archive_files),
        "includes_cg": not args.no_cg,
        "validation": validation,
        "status": "PACKED",
    }
    sidecar = output.with_suffix(output.suffix + ".manifest.json")
    sidecar.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def submit(args: argparse.Namespace) -> int:
    archive = pathlib.Path(args.archive).resolve()
    if not archive.is_file():
        raise SystemExit(f"archive missing: {archive}")
    if args.manifest and pathlib.Path(args.manifest).is_file():
        manifest = json.loads(pathlib.Path(args.manifest).read_text())
    else:
        manifest = {}
    archive_sha = sha256(archive)
    description = args.description.strip() or f"PTCG candidate archive:{archive_sha[:16]}"
    # Keep the API code local so the root-bound submit.py cannot silently swap
    # the candidate for the dirty root main.py.
    from kagglesdk import KaggleClient, KaggleEnv
    from kagglesdk.competitions.types.competition_api_service import (
        ApiCreateSubmissionRequest,
        ApiStartSubmissionUploadRequest,
    )

    client = KaggleClient(env=KaggleEnv.PROD)
    api = client.competitions.competition_api_client
    req = ApiStartSubmissionUploadRequest()
    req.competition_name = args.competition
    req.content_length = archive.stat().st_size
    req.last_modified_epoch_seconds = int(archive.stat().st_mtime)
    req.file_name = "submission.tar.gz"
    upload = api.start_submission_upload(req)
    blob_token = upload.token
    put = urllib.request.Request(upload.create_url, data=archive.read_bytes(), method="PUT")
    put.add_header("Content-Type", "application/gzip")
    put.add_header("Content-Length", str(archive.stat().st_size))
    with urllib.request.urlopen(put, timeout=180) as response:
        if response.status < 200 or response.status >= 300:
            raise SystemExit(f"upload failed HTTP {response.status}")
    create = ApiCreateSubmissionRequest()
    create.competition_name = args.competition
    create.blob_file_tokens = blob_token
    create.submission_description = description
    result = api.create_submission(create)
    # SDK response fields vary by version; emit only non-secret scalar fields.
    safe = {}
    for key in ("ref", "id", "status", "message", "submission_id"):
        value = getattr(result, key, None)
        if value is not None:
            safe[key] = getattr(value, "name", value)
    record = {
        "ts": time.time(),
        "event": "candidate_submit",
        "competition": args.competition,
        "archive": str(archive),
        "archive_sha256": archive_sha,
        "main_sha256": manifest.get("main_sha256"),
        "deck_sha256": manifest.get("deck_sha256"),
        "description": description,
        "response": safe,
        "status": "UPLOADED",
    }
    record_path = pathlib.Path(args.record).resolve()
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def inspect_submission(args: argparse.Namespace) -> int:
    """Print the server-side status/error for one immutable submission ref."""
    from kagglesdk import KaggleClient, KaggleEnv
    from kagglesdk.competitions.types.competition_api_service import ApiGetSubmissionRequest

    client = KaggleClient(env=KaggleEnv.PROD)
    req = ApiGetSubmissionRequest()
    req.ref = int(args.ref)
    sub = client.competitions.competition_api_client.get_submission(req)
    result = {
        "ref": sub.ref,
        "status": getattr(sub.status, "name", str(sub.status)),
        "public_score": sub.public_score or None,
        "private_score": sub.private_score or None,
        "error_description": sub.error_description or None,
        "description": sub.description,
        "file_name": sub.file_name,
        "total_bytes": sub.total_bytes,
        "date": str(sub.date) if sub.date else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--candidate-dir", required=True)
    common.add_argument("--engine-root", default=str(DEFAULT_ENGINE))
    v = sub.add_parser("validate", parents=[common])
    v.add_argument("--startup-probes", type=int, default=3)
    p = sub.add_parser("pack", parents=[common])
    p.add_argument("--output", required=True)
    p.add_argument("--no-cg", action="store_true",
                   help="omit the official cg runtime (not recommended for competition submission)")
    s = sub.add_parser("submit")
    s.add_argument("--archive", required=True)
    s.add_argument("--manifest", default="")
    s.add_argument("--description", default="")
    s.add_argument("--competition", default="pokemon-tcg-ai-battle")
    s.add_argument("--record", default=str(DEFAULT_RECORD))
    i = sub.add_parser("inspect")
    i.add_argument("--ref", type=int, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        validate(args)
        return 0
    if args.command == "pack":
        pack(args)
        return 0
    if args.command == "submit":
        return submit(args)
    return inspect_submission(args)


if __name__ == "__main__":
    raise SystemExit(main())
