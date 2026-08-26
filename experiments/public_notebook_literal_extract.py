#!/usr/bin/env python3
"""Safely extract literal submission assets from a public Kaggle notebook.

The notebook is never executed.  Only top-level assignments whose right-hand
side is a string literal are accepted, so imports, calls, and generator code in
an untrusted notebook cannot run during extraction.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


ASSETS = {
    "MAIN_SOURCE": "main.py",
    "DECK_SOURCE": "deck.csv",
    "GROUP_SOURCE": "group.txt",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    if isinstance(source, str):
        return source
    raise SystemExit(f"unsupported notebook source type: {type(source).__name__}")


def literal_assets(notebook: Path) -> dict[str, str]:
    payload = json.loads(notebook.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for cell_index, cell in enumerate(payload.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        tree = ast.parse(cell_source(cell), filename=f"{notebook}:cell-{cell_index}")
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            wanted = [name for name in names if name in ASSETS]
            if not wanted:
                continue
            value = node.value
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                raise SystemExit(f"{wanted[0]} is not a plain string literal")
            for name in wanted:
                if name in found:
                    raise SystemExit(f"duplicate asset assignment: {name}")
                found[name] = value.value
    missing = sorted(set(ASSETS) - set(found))
    if missing:
        raise SystemExit(f"missing literal assets: {missing}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    assets = literal_assets(args.notebook.resolve())
    args.output.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "source_notebook": str(args.notebook.resolve()),
        "source_notebook_sha256": sha256(args.notebook.read_bytes()),
        "extraction": "ast-top-level-string-literals-only-v1",
        "files": {},
    }
    for variable, filename in ASSETS.items():
        data = assets[variable].encode("utf-8")
        (args.output / filename).write_bytes(data)
        manifest["files"][filename] = {
            "source_variable": variable,
            "bytes": len(data),
            "sha256": sha256(data),
        }
    (args.output / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
