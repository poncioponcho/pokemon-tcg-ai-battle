"""Streamable Zstandard archive for raw PTCG replay JSON files.

The archive format is newline-delimited JSON compressed with zstd.  Each line
has the shape ``{"episode_id": ..., "file": ..., "replay": ...}``, so a
consumer can scan one replay at a time without extracting the whole archive.
The raw directory remains the fastest source for multiprocessing extraction;
the archive is the durable, compact source for storage and streaming scans.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import zstandard as zstd


SCHEMA = "ptcg-replay-jsonl-zstd-v2"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _episode_id(path: Path) -> str:
    parts = path.name.split("-")
    return parts[1] if len(parts) > 2 and parts[0] == "episode" else path.stem


def _archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_record(writer: Any, path: Path) -> int:
    raw = path.read_bytes()
    # Validate once, then retain the exact source text so extraction preserves
    # catalog SHA-256 values and does not only preserve semantic JSON content.
    json.loads(raw)
    prefix = (
        b'{"episode_id":'
        + json.dumps(_episode_id(path), ensure_ascii=False).encode("utf-8")
        + b',"file":'
        + json.dumps(path.name, ensure_ascii=False).encode("utf-8")
        + b',"raw_json":'
    )
    encoded = json.dumps(raw.decode("utf-8"), ensure_ascii=False).encode("utf-8")
    writer.write(prefix)
    writer.write(encoded)
    writer.write(b"}\n")
    return len(raw)


def _write_record_fields(writer: Any, episode_id: str, file: str, raw_json: str) -> int:
    """Write an archive record from explicit fields (used by merge)."""
    prefix = (
        b'{"episode_id":'
        + json.dumps(episode_id, ensure_ascii=False).encode("utf-8")
        + b',"file":'
        + json.dumps(file, ensure_ascii=False).encode("utf-8")
        + b',"raw_json":'
    )
    encoded = json.dumps(raw_json, ensure_ascii=False).encode("utf-8")
    writer.write(prefix)
    writer.write(encoded)
    writer.write(b"}\n")
    return len(raw_json)


def merge_into_archive(
    archive: str | Path,
    source_dir: str | Path,
    level: int = 5,
    pattern: str = "episode-*-replay.json",
) -> dict[str, Any]:
    """Incrementally merge raw files into an existing archive (dedup by episode_id).

    Existing archive records are streamed and preserved verbatim; episodes from
    ``source_dir`` that are not already present are appended.  The file is
    replaced atomically, so a crash never corrupts the canonical archive.
    """
    archive = Path(archive)
    source_dir = Path(source_dir)
    archive.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{archive.name}.", suffix=".partial", dir=archive.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)

    seen: dict[str, str] = {}
    total_bytes = 0
    n_existing = 0
    n_added = 0
    n_skipped = 0
    t0 = time.time()
    try:
        compressor = zstd.ZstdCompressor(level=level, threads=-1)
        with temp_path.open("wb") as target:
            with compressor.stream_writer(target) as writer:
                if archive.exists():
                    for row in iter_records(archive):
                        ep = str(row["episode_id"])
                        if ep in seen:
                            continue
                        seen[ep] = str(row.get("file", ""))
                        total_bytes += _write_record_fields(
                            writer, ep, seen[ep], str(row.get("raw_json", "")))
                        n_existing += 1
                for path in sorted(source_dir.glob(pattern)):
                    # [fix 08-09] 统一走 _episode_id(): 原为裸 split("-")[1],
                    # 非标准文件名(无连字符)会 IndexError, 且与已有归档的 id
                    # 提取口径不一致会导致 dedup 漏判
                    ep = _episode_id(path)
                    if ep in seen:
                        n_skipped += 1
                        continue
                    try:
                        raw = path.read_text(encoding="utf-8")
                        json.loads(raw)
                    except Exception as exc:
                        print(f"  [SKIP] {path.name}: {exc}")
                        continue
                    seen[ep] = path.name
                    total_bytes += _write_record_fields(writer, ep, path.name, raw)
                    n_added += 1
        os.replace(temp_path, archive)
    finally:
        temp_path.unlink(missing_ok=True)

    manifest = {
        "schema": SCHEMA,
        "created_at": _utc_now(),
        "operation": "merge",
        "archive": str(archive),
        "source_dir": str(source_dir),
        "records": len(seen),
        "existing_records": n_existing,
        "added_records": n_added,
        "skipped_duplicates": n_skipped,
        "raw_json_bytes": total_bytes,
        "compressed_bytes": archive.stat().st_size,
        "compression_ratio": round(total_bytes / archive.stat().st_size, 3),
        "archive_sha256": _archive_sha256(archive),
        "seconds": round(time.time() - t0, 1),
    }
    manifest_path = archive.with_suffix(archive.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def pack(
    raw_dir: str | Path,
    output: str | Path,
    level: int = 5,
    pattern: str = "episode-*-replay.json",
) -> dict[str, Any]:
    """Pack raw replay files into one streamable ``.jsonl.zst`` archive."""
    raw_dir = Path(raw_dir)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(raw_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no replay files found in {raw_dir}")

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".partial", dir=output.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)
    count = 0
    raw_bytes = 0
    try:
        compressor = zstd.ZstdCompressor(level=level, threads=-1)
        with temp_path.open("wb") as target:
            with compressor.stream_writer(target) as writer:
                for path in files:
                    raw_bytes += _write_record(writer, path)
                    count += 1
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)

    compressed_bytes = output.stat().st_size
    manifest = {
        "schema": SCHEMA,
        "created_at": _utc_now(),
        "source_dir": str(raw_dir),
        "source_pattern": pattern,
        "archive": str(output),
        "records": count,
        "raw_json_bytes": raw_bytes,
        "compressed_bytes": compressed_bytes,
        "compression_ratio": round(raw_bytes / compressed_bytes, 3)
        if compressed_bytes
        else None,
        "archive_sha256": _archive_sha256(output),
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def iter_records(archive: str | Path) -> Iterator[dict[str, Any]]:
    """Yield archive wrapper records one line at a time."""
    archive = Path(archive)
    decompressor = zstd.ZstdDecompressor()
    with archive.open("rb") as source:
        with decompressor.stream_reader(source) as stream:
            text = stream  # bytes are decoded per line to avoid a huge buffer.
            buffer = b""
            while chunk := text.read(1024 * 1024):
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    yield json.loads(line)
            if buffer.strip():
                yield json.loads(buffer)


def iter_replays(archive: str | Path) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield ``(episode_id, filename, replay)`` one compressed record at a time."""
    for row in iter_records(archive):
        if "raw_json" in row:
            replay = json.loads(row["raw_json"])
        else:  # Backward-compatible reader for v1 semantic archives.
            replay = row["replay"]
        yield str(row["episode_id"]), str(row["file"]), replay


def scan(archive: str | Path, limit: int = 0) -> dict[str, Any]:
    count = 0
    total_steps = 0
    for episode_id, _, replay in iter_replays(archive):
        if not isinstance(replay, dict):
            raise ValueError(f"episode {episode_id} payload is not an object")
        total_steps += len(replay.get("steps") or [])
        count += 1
        if limit and count >= limit:
            break
    return {"records": count, "steps": total_steps, "limited": bool(limit)}


def scan_raw(
    raw_dir: str | Path,
    pattern: str = "episode-*-replay.json",
) -> dict[str, Any]:
    """Full raw-directory integrity scan without retaining replay payloads."""
    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.glob(pattern))
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    invalid: list[dict[str, str]] = []
    total_bytes = 0
    total_steps = 0
    total_decisions = 0
    for path in files:
        episode_id = _episode_id(path)
        if episode_id in seen:
            duplicate_ids.append(episode_id)
        seen.add(episode_id)
        total_bytes += path.stat().st_size
        try:
            payload = json.loads(path.read_bytes())
            if not isinstance(payload, dict):
                raise ValueError("replay root is not an object")
            steps = payload.get("steps") or []
            if not isinstance(steps, list):
                raise ValueError("steps is not a list")
            total_steps += len(steps)
            for step in steps:
                views = step if isinstance(step, list) else [step]
                for view in views:
                    if not isinstance(view, dict):
                        continue
                    observation = view.get("observation") or {}
                    select = observation.get("select") if isinstance(observation, dict) else None
                    action = view.get("action") or []
                    options = select.get("option") if isinstance(select, dict) else None
                    if isinstance(select, dict) and isinstance(options, list) and isinstance(action, list):
                        if action and all(isinstance(value, int) and 0 <= value < len(options) for value in action):
                            total_decisions += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            invalid.append({"file": path.name, "error": str(exc)[:200]})
    return {
        "source": str(raw_dir),
        "pattern": pattern,
        "records": len(files),
        "unique_episode_ids": len(seen),
        "duplicate_episode_ids": sorted(set(duplicate_ids)),
        "invalid_files": invalid,
        "raw_json_bytes": total_bytes,
        "steps": total_steps,
        "valid_decisions": total_decisions,
        "ok": not duplicate_ids and not invalid,
    }


def verify_archive(archive: str | Path) -> dict[str, Any]:
    """Full stream validation: JSON shape, duplicate IDs, and step counts."""
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    invalid: list[dict[str, str]] = []
    records = 0
    steps = 0
    try:
        for episode_id, _, replay in iter_replays(archive):
            if episode_id in seen:
                duplicate_ids.append(episode_id)
            seen.add(episode_id)
            if not isinstance(replay, dict):
                invalid.append({"episode_id": episode_id, "error": "root is not an object"})
                continue
            replay_steps = replay.get("steps") or []
            if not isinstance(replay_steps, list):
                invalid.append({"episode_id": episode_id, "error": "steps is not a list"})
                continue
            records += 1
            steps += len(replay_steps)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        invalid.append({"episode_id": "<archive>", "error": str(exc)[:200]})
    return {
        "source": str(archive),
        "records": records,
        "unique_episode_ids": len(seen),
        "duplicate_episode_ids": sorted(set(duplicate_ids)),
        "invalid_records": invalid,
        "steps": steps,
        "ok": not duplicate_ids and not invalid,
    }


def finalize(
    raw_dir: str | Path,
    output: str | Path,
    *,
    level: int = 5,
    pattern: str = "episode-*-replay.json",
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Scan raw, repack it, scan archive, and require ID/count equality."""
    raw_report = scan_raw(raw_dir, pattern)
    if not raw_report["ok"]:
        raise ValueError(f"raw validation failed: {raw_report}")
    archive_manifest = pack(raw_dir, output, level=level, pattern=pattern)
    archive_report = verify_archive(output)
    if not archive_report["ok"]:
        raise ValueError(f"archive validation failed: {archive_report}")
    if raw_report["records"] != archive_report["records"]:
        raise ValueError("raw/archive record count mismatch")
    result = {
        "status": "ok",
        "checked_at": _utc_now(),
        "raw": raw_report,
        "archive": archive_report,
        "archive_manifest": archive_manifest,
    }
    report_path = Path(report_path) if report_path else Path(output).with_name("raw_replays.validation.json")
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def extract(archive: str | Path, raw_dir: str | Path, limit: int = 0) -> int:
    """Restore raw files from the stream archive without loading it all."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for row in iter_records(archive):
        filename = str(row["file"])
        if Path(filename).name != filename:
            raise ValueError(f"unsafe archive filename: {filename}")
        path = raw_dir / filename
        if not path.exists():
            if "raw_json" in row:
                path.write_bytes(str(row["raw_json"]).encode("utf-8"))
            else:
                path.write_text(
                    json.dumps(row["replay"], ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
        count += 1
        if limit and count >= limit:
            break
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack/scan/extract streamable replay archives")
    sub = parser.add_subparsers(dest="command", required=True)

    pack_parser = sub.add_parser("pack", help="raw/*.json -> .jsonl.zst")
    pack_parser.add_argument("--raw-dir", required=True)
    pack_parser.add_argument("--output", required=True)
    pack_parser.add_argument("--level", type=int, default=5)
    pack_parser.add_argument("--pattern", default="episode-*-replay.json")

    scan_parser = sub.add_parser("scan", help="stream scan without extraction")
    scan_parser.add_argument("--archive", required=True)
    scan_parser.add_argument("--limit", type=int, default=0)

    extract_parser = sub.add_parser("extract", help="restore raw JSON files")
    extract_parser.add_argument("--archive", required=True)
    extract_parser.add_argument("--raw-dir", required=True)
    extract_parser.add_argument("--limit", type=int, default=0)

    raw_scan_parser = sub.add_parser("verify-raw", help="full raw JSON integrity scan")
    raw_scan_parser.add_argument("--raw-dir", required=True)
    raw_scan_parser.add_argument("--pattern", default="episode-*-replay.json")

    archive_verify_parser = sub.add_parser("verify-archive", help="full archive integrity scan")
    archive_verify_parser.add_argument("--archive", required=True)

    finalize_parser = sub.add_parser("finalize", help="scan raw, repack, and compare archive")
    finalize_parser.add_argument("--raw-dir", required=True)
    finalize_parser.add_argument("--output", required=True)
    finalize_parser.add_argument("--level", type=int, default=5)
    finalize_parser.add_argument("--pattern", default="episode-*-replay.json")
    finalize_parser.add_argument("--report", default=None)

    merge_parser = sub.add_parser(
        "merge", help="incrementally merge raw files into an existing archive (dedup by episode_id)")
    merge_parser.add_argument("--archive", required=True)
    merge_parser.add_argument("--raw-dir", required=True)
    merge_parser.add_argument("--level", type=int, default=5)
    merge_parser.add_argument("--pattern", default="episode-*-replay.json")

    args = parser.parse_args()
    if args.command == "pack":
        print(json.dumps(
            pack(args.raw_dir, args.output, args.level, args.pattern),
            ensure_ascii=False,
            indent=2,
        ))
    elif args.command == "scan":
        print(json.dumps(scan(args.archive, args.limit), ensure_ascii=False, indent=2))
    elif args.command == "verify-raw":
        print(json.dumps(scan_raw(args.raw_dir, args.pattern), ensure_ascii=False, indent=2))
    elif args.command == "verify-archive":
        print(json.dumps(verify_archive(args.archive), ensure_ascii=False, indent=2))
    elif args.command == "finalize":
        print(json.dumps(
            finalize(
                args.raw_dir,
                args.output,
                level=args.level,
                pattern=args.pattern,
                report_path=args.report,
            ),
            ensure_ascii=False,
            indent=2,
        ))
    elif args.command == "merge":
        print(json.dumps(
            merge_into_archive(args.archive, args.raw_dir, level=args.level, pattern=args.pattern),
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(json.dumps({"records": extract(args.archive, args.raw_dir, args.limit)}))


if __name__ == "__main__":
    main()
