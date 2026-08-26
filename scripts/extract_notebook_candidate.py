#!/usr/bin/env python3
"""Materialize an auditable main.py/deck.csv pair from a public notebook.

Supported notebook shapes are the fixed forms used by the public PTCG
builders: literal ``%%writefile main.py`` and ``%%writefile deck.csv`` cells,
``%%writefile main.py`` plus either a literal ``deck_text`` or literal ``DECK``
list, or a literal base64 ``PAYLOADS`` dictionary.  Dynamic code execution is
deliberately avoided.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import pathlib
from typing import Any


def assignment_literal(source: str, name: str) -> Any | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        if node.value is None:
            return None
        try:
            return ast.literal_eval(node.value)
        except (TypeError, ValueError):
            return None
    return None


def extract(cells: list[dict[str, Any]]) -> dict[str, bytes]:
    sources = [
        "".join(cell.get("source", []))
        for cell in cells
        if cell.get("cell_type") == "code"
    ]
    for source in sources:
        payloads = assignment_literal(source, "PAYLOADS")
        if isinstance(payloads, dict) and {"main.py", "deck.csv"} <= set(payloads):
            try:
                decoded: dict[str, bytes] = {}
                for raw_name, encoded in payloads.items():
                    name = str(raw_name)
                    if pathlib.PurePath(name).name != name or name in {".", ".."}:
                        raise SystemExit(f"unsafe PAYLOADS member: {name!r}")
                    decoded[name] = base64.b64decode(encoded, validate=True)
                return decoded
            except (TypeError, ValueError) as exc:
                raise SystemExit(f"invalid base64 PAYLOADS: {exc}") from exc

    writefile_payloads: dict[str, bytes] = {}
    deck_bytes = None
    for source in sources:
        lines = source.splitlines(keepends=True)
        if lines and lines[0].strip().startswith("%%writefile"):
            target = lines[0].strip().split(maxsplit=1)[-1]
            if pathlib.PurePath(target).name != target or target in {".", ".."}:
                raise SystemExit(f"unsafe %%writefile member: {target!r}")
            writefile_payloads[target] = "".join(lines[1:]).encode("utf-8")
        deck_text = assignment_literal(source, "deck_text")
        if isinstance(deck_text, str):
            deck_bytes = deck_text.encode("utf-8")
        deck_list = assignment_literal(source, "DECK")
        if (
            deck_bytes is None
            and isinstance(deck_list, (list, tuple))
            and all(isinstance(card, int) for card in deck_list)
        ):
            deck_bytes = ("\n".join(str(card) for card in deck_list) + "\n").encode("utf-8")
    if deck_bytes is None:
        deck_bytes = writefile_payloads.get("deck.csv")
    if "main.py" not in writefile_payloads or deck_bytes is None:
        raise SystemExit("notebook has no supported fixed main.py/deck.csv payload")
    writefile_payloads["deck.csv"] = deck_bytes
    return writefile_payloads


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    notebook = pathlib.Path(args.notebook).resolve()
    payload = json.loads(notebook.read_text(encoding="utf-8"))
    files = extract(payload.get("cells", []))

    try:
        deck = [int(line) for line in files["deck.csv"].decode("utf-8").splitlines()
                if line.strip()]
    except (UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(f"invalid extracted deck.csv: {exc}") from exc
    if len(deck) != 60:
        raise SystemExit(f"extracted deck.csv has {len(deck)} rows, expected 60")

    output = pathlib.Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = output / name
        if target.exists() and target.read_bytes() != data:
            raise SystemExit(f"refusing to overwrite different file: {target}")
        target.write_bytes(data)
    receipt = {
        "notebook": str(notebook),
        "output_dir": str(output),
        "main_sha256": sha256(files["main.py"]),
        "deck_sha256": sha256(files["deck.csv"]),
        "main_bytes": len(files["main.py"]),
        "deck_rows": len(deck),
        "status": "EXTRACTED",
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
