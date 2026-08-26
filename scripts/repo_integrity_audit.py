#!/usr/bin/env python3
"""Read-only repository-wide integrity and parse audit.

This deliberately separates hard failures from advisory warnings.  It walks
every regular file outside ``.git`` and applies format-aware checks where a
safe parser is available.  It never imports project Python modules or
unpickles model files.
"""

from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tokenize
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {
    ".css", ".html", ".htm", ".ini", ".js", ".jsx", ".md", ".mdc",
    ".py", ".pyi", ".rst", ".sh", ".sql", ".toml", ".ts", ".tsx",
    ".txt", ".xml", ".yaml", ".yml",
}
JSON_SUFFIXES = {".json", ".ipynb"}
ARCHIVE_SUFFIXES = {".zip", ".npz", ".whl", ".docx", ".xlsx", ".pptx"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
CONFLICT_RE = re.compile(r"^(<{7}|={7}|>{7})(?: |$)", re.MULTILINE)
LOCAL_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def issue(items: list[dict[str, Any]], severity: str, code: str,
          path: Path, detail: str) -> None:
    items.append({
        "severity": severity,
        "code": code,
        "path": path.as_posix(),
        "detail": detail,
    })


def safe_text(path: Path) -> str:
    if path.suffix.lower() in {".py", ".pyi"}:
        with tokenize.open(path) as handle:
            return handle.read()
    return path.read_text(encoding="utf-8-sig")


def check_python(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        source = safe_text(path)
        ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeError, OSError) as exc:
        issue(issues, "error", "python_parse", path, str(exc))


def check_json(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            value = json.load(handle)
        if path.suffix.lower() == ".ipynb":
            if not isinstance(value, dict) or not isinstance(value.get("cells"), list):
                issue(issues, "error", "notebook_shape", path, "missing cells list")
            elif value.get("nbformat") not in {4}:
                issue(issues, "warning", "notebook_version", path,
                      f"nbformat={value.get('nbformat')!r}")
    except (json.JSONDecodeError, UnicodeError, OSError) as exc:
        issue(issues, "error", "json_parse", path, str(exc))


def check_xml(path: Path, issues: list[dict[str, Any]]) -> None:
    """Parse XML/SVG after rejecting DTD/entity declarations.

    The repository contains downloaded artifacts, so even this read-only audit
    must not expand attacker-controlled entities.  ElementTree is sufficient
    for the remaining plain documents once declarations are rejected.
    """
    try:
        with path.open("rb") as handle:
            prefix = handle.read(1 << 20).upper()
        if b"<!DOCTYPE" in prefix or b"<!ENTITY" in prefix:
            issue(issues, "error", "xml_unsafe_declaration", path,
                  "DTD/entity declarations are not permitted")
            return
        ET.parse(path)  # noqa: S314 - DTD/entity declarations rejected above
    except (ET.ParseError, OSError) as exc:
        issue(issues, "error", "xml_parse", path, str(exc))


def check_jsonl(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    issue(issues, "error", "jsonl_parse", path,
                          f"line {line_no}: {exc}")
                    return
    except (UnicodeError, OSError) as exc:
        issue(issues, "error", "jsonl_read", path, str(exc))


def check_delimited(path: Path, issues: list[dict[str, Any]]) -> None:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        widths: Counter[int] = Counter()
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter, strict=True)
            for row in reader:
                widths[len(row)] += 1
        if len(widths) > 1:
            common_width, common_count = widths.most_common(1)[0]
            unusual = sum(widths.values()) - common_count
            issue(issues, "warning", "delimited_ragged", path,
                  f"widths={dict(widths)}; common={common_width}; unusual={unusual}")
    except (csv.Error, UnicodeError, OSError) as exc:
        issue(issues, "error", "delimited_parse", path, str(exc))


def check_archive(path: Path, issues: list[dict[str, Any]], full: bool) -> None:
    name = path.name.lower()
    try:
        if path.suffix.lower() in ARCHIVE_SUFFIXES:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                bad_paths = [n for n in names if n.startswith("/") or ".." in Path(n).parts]
                if bad_paths:
                    issue(issues, "error", "archive_path_traversal", path,
                          f"unsafe members: {bad_paths[:5]}")
                if len(names) != len(set(names)):
                    issue(issues, "warning", "archive_duplicate_member", path,
                          "duplicate member names")
                if full:
                    bad = archive.testzip()
                    if bad:
                        issue(issues, "error", "archive_crc", path, bad)
        elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
            with tarfile.open(path, "r:*") as archive:
                seen: set[str] = set()
                for member in archive:
                    parts = Path(member.name).parts
                    if member.name.startswith("/") or ".." in parts:
                        issue(issues, "error", "archive_path_traversal", path,
                              f"unsafe member: {member.name}")
                        break
                    if member.name in seen:
                        issue(issues, "warning", "archive_duplicate_member", path,
                              f"duplicate member: {member.name}")
                        break
                    seen.add(member.name)
        elif path.suffix.lower() == ".gz" and full:
            with gzip.open(path, "rb") as handle:
                while handle.read(1024 * 1024):
                    pass
    except (OSError, EOFError, tarfile.TarError, zipfile.BadZipFile) as exc:
        issue(issues, "error", "archive_integrity", path, str(exc))


def check_npy(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        import numpy as np
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        _ = (array.shape, array.dtype, array.nbytes)
    except Exception as exc:  # numpy exposes several format-specific exceptions
        issue(issues, "error", "npy_header", path, repr(exc))


def check_image(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        issue(issues, "error", "image_integrity", path, repr(exc))


def check_pdf(path: Path, head: bytes, tail: bytes,
              issues: list[dict[str, Any]]) -> None:
    if not head.startswith(b"%PDF-"):
        issue(issues, "error", "pdf_header", path, "missing %PDF header")
    if b"%%EOF" not in tail:
        issue(issues, "error", "pdf_eof", path, "missing trailing %%EOF")


def check_zstd(path: Path, issues: list[dict[str, Any]], full: bool) -> None:
    if not full:
        return
    executable = shutil.which("zstd")
    if not executable:
        issue(issues, "warning", "zstd_checker_missing", path, "zstd not installed")
        return
    try:
        proc = subprocess.run(
            [executable, "--test", "--quiet", str(path)],
            capture_output=True, text=True, timeout=600, check=False,
        )
        if proc.returncode:
            issue(issues, "error", "zstd_integrity", path,
                  (proc.stderr or proc.stdout).strip())
    except (OSError, subprocess.SubprocessError) as exc:
        issue(issues, "error", "zstd_integrity", path, str(exc))


def check_shell(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        first = path.open("rb").readline(256).decode("ascii", "ignore")
        shell = "zsh" if "zsh" in first else "bash"
        executable = shutil.which(shell)
        if not executable:
            issue(issues, "warning", "shell_checker_missing", path, shell)
            return
        proc = subprocess.run(
            [executable, "-n", str(path)], capture_output=True, text=True,
            timeout=15, check=False,
        )
        if proc.returncode:
            issue(issues, "error", "shell_syntax", path,
                  (proc.stderr or proc.stdout).strip())
    except (OSError, subprocess.SubprocessError) as exc:
        issue(issues, "error", "shell_check", path, str(exc))


def check_sqlite(path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        uri = f"file:{path.resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            issue(issues, "error", "sqlite_integrity", path, repr(result))
    except sqlite3.Error as exc:
        issue(issues, "error", "sqlite_integrity", path, str(exc))


def check_text(path: Path, root: Path, issues: list[dict[str, Any]],
               max_bytes: int) -> None:
    try:
        if path.stat().st_size > max_bytes:
            issue(issues, "warning", "large_text_partial", path,
                  f"larger than {max_bytes} bytes; structured parser still applied")
            return
        text = safe_text(path)
        if "\x00" in text:
            issue(issues, "error", "nul_in_text", path, "contains NUL byte")
        if CONFLICT_RE.search(text):
            issue(issues, "error", "merge_conflict_marker", path,
                  "contains unresolved conflict marker")
        if path.suffix.lower() == ".md":
            for raw in LOCAL_LINK_RE.findall(text):
                target = raw.strip().strip("<>").split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "data:")):
                    continue
                target = target.split(" ", 1)[0]
                linked = Path(target)
                if linked.is_absolute():
                    try:
                        linked.resolve().relative_to(root)
                    except (OSError, ValueError):
                        continue
                else:
                    linked = path.parent / linked
                if not linked.exists():
                    issue(issues, "warning", "broken_local_link", path, target)
    except (UnicodeError, OSError) as exc:
        issue(issues, "error", "text_read", path, str(exc))


def audit(root: Path, full_archives: bool, max_text_bytes: int) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    suffixes: Counter[str] = Counter()
    directories: Counter[str] = Counter()
    files = 0
    bytes_total = 0
    digest = hashlib.sha256()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        base = Path(dirpath)
        for filename in sorted(filenames):
            path = base / filename
            relative = path.relative_to(root)
            try:
                if path.is_symlink():
                    if not path.exists():
                        issue(issues, "error", "broken_symlink", relative,
                              os.readlink(path))
                    continue
                stat = path.stat()
                if not path.is_file():
                    issue(issues, "warning", "non_regular", relative, "not a regular file")
                    continue
                with path.open("rb") as handle:
                    head = handle.read(4096)
                    if stat.st_size > 4096:
                        handle.seek(max(0, stat.st_size - 4096))
                        tail = handle.read(4096)
                    else:
                        tail = b""
            except OSError as exc:
                issue(issues, "error", "file_read", relative, str(exc))
                continue

            files += 1
            bytes_total += stat.st_size
            suffix = path.suffix.lower() or "<none>"
            suffixes[suffix] += 1
            directories[relative.parts[0] if relative.parts else "."] += 1
            digest.update(relative.as_posix().encode("utf-8", "surrogateescape"))
            digest.update(stat.st_size.to_bytes(8, "little", signed=False))
            digest.update(head)
            digest.update(tail)

            if stat.st_size == 0 and filename not in {"__init__.py", ".gitkeep"}:
                issue(issues, "warning", "empty_file", relative, "zero bytes")
            if head.startswith(b"version https://git-lfs.github.com/spec/v1"):
                issue(issues, "error", "unresolved_lfs_pointer", relative,
                      "Git LFS content is not materialized")

            lowname = filename.lower()
            if suffix in {".py", ".pyi"}:
                check_python(path, issues)
            elif suffix in JSON_SUFFIXES:
                check_json(path, issues)
            elif suffix == ".jsonl":
                check_jsonl(path, issues)
            elif suffix in {".csv", ".tsv"}:
                check_delimited(path, issues)
            elif suffix == ".toml":
                try:
                    with path.open("rb") as handle:
                        tomllib.load(handle)
                except (tomllib.TOMLDecodeError, OSError) as exc:
                    issue(issues, "error", "toml_parse", relative, str(exc))
            elif suffix in {".yaml", ".yml"}:
                try:
                    import yaml  # type: ignore[import-untyped]
                    with path.open(encoding="utf-8-sig") as handle:
                        yaml.safe_load(handle)
                except ImportError:
                    issue(issues, "warning", "yaml_checker_missing", relative,
                          "PyYAML not installed")
                except (UnicodeError, OSError, yaml.YAMLError) as exc:
                    issue(issues, "error", "yaml_parse", relative, str(exc))
            elif suffix in {".xml", ".svg"}:
                check_xml(path, issues)
            elif suffix == ".npy":
                check_npy(path, issues)
            elif suffix in IMAGE_SUFFIXES:
                check_image(path, issues)
            elif suffix == ".pdf":
                check_pdf(path, head, tail, issues)
            elif suffix in {".sqlite", ".sqlite3", ".db"}:
                check_sqlite(path, issues)

            if (suffix in ARCHIVE_SUFFIXES or lowname.endswith(
                    (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"))):
                check_archive(path, issues, full_archives)
            elif suffix == ".gz" and not lowname.endswith(".tar.gz"):
                check_archive(path, issues, full_archives)
            elif suffix == ".zst":
                check_zstd(path, issues, full_archives)
            if suffix == ".sh":
                check_shell(path, issues)
            if suffix in TEXT_SUFFIXES:
                check_text(path, root, issues, max_text_bytes)

    by_severity = Counter(x["severity"] for x in issues)
    by_code = Counter(x["code"] for x in issues)
    return {
        "root": str(root),
        "files": files,
        "bytes": bytes_total,
        "inventory_fingerprint": digest.hexdigest(),
        "suffixes": dict(suffixes.most_common()),
        "top_directories": dict(directories.most_common()),
        "issue_summary": dict(by_severity),
        "issue_codes": dict(by_code.most_common()),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    parser.add_argument("--full-archives", action="store_true",
                        help="decompress zip/gzip members to verify CRC")
    parser.add_argument("--max-text-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args()
    root = args.root.resolve()
    report = audit(root, args.full_archives, args.max_text_bytes)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "root", "files", "bytes", "inventory_fingerprint",
        "issue_summary", "issue_codes",
    )}, ensure_ascii=False, indent=2))
    return 1 if report["issue_summary"].get("error", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
