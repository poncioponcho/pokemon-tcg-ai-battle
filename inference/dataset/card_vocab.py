"""Frozen card-id vocabulary used by every feature extraction/inference run."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VOCAB_VERSION = "card_vocab_v1"
DEFAULT_PATH = Path(__file__).with_name("card_vocab_v1.json")


def _load_id_scan(path: Path) -> list[int]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return [int(card_id) for card_id in value["ids"].keys()]


def create_vocab(card_ids: list[int], path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    """Create once; existing vocabularies are never silently replaced."""
    path = Path(path)
    if path.exists():
        return load_vocab(path)
    unique_ids = []
    seen = set()
    for card_id in card_ids:
        card_id = int(card_id)
        if card_id not in seen:
            seen.add(card_id)
            unique_ids.append(card_id)
    value = {
        "version": VOCAB_VERSION,
        "unknown_index": 0,
        "card_ids": unique_ids,
        "id_to_index": {str(card_id): index for index, card_id in enumerate(unique_ids, 1)},
        "size": len(unique_ids) + 1,
        "source": "initial id_scan_results order; immutable after creation",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return value


def load_vocab(path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("version") != VOCAB_VERSION:
        raise ValueError(f"Unsupported card vocabulary: {value.get('version')!r}")
    if int(value.get("unknown_index", -1)) != 0:
        raise ValueError("Frozen vocabulary must reserve index 0 for unknown cards")
    if int(value.get("size", 0)) != len(value.get("card_ids", [])) + 1:
        raise ValueError("Card vocabulary size does not match card_ids")
    return value


def load_or_create(
    path: str | Path = DEFAULT_PATH,
    *,
    id_scan_path: str | Path = "inference/leaderboard_replay/id_scan_results.json",
) -> dict[str, Any]:
    path = Path(path)
    if path.exists():
        return load_vocab(path)
    return create_vocab(_load_id_scan(Path(id_scan_path)), path)


def card_index(card_id: Any, vocab: dict[str, Any]) -> int:
    if card_id is None:
        return int(vocab["unknown_index"])
    return int(vocab["id_to_index"].get(str(card_id), vocab["unknown_index"]))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(DEFAULT_PATH))
    parser.add_argument("--id-scan", default="inference/leaderboard_replay/id_scan_results.json")
    args = parser.parse_args()
    value = load_or_create(args.path, id_scan_path=args.id_scan)
    print(json.dumps({"path": args.path, "version": value["version"], "size": value["size"]}))
