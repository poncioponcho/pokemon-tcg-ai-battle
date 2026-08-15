#!/usr/bin/env python3
"""Exclusive reservation and atomic JSON output for long-running experiments."""

from __future__ import annotations

import atexit
import json
import os
import pathlib
import sys
import time
from typing import Any


class JsonOutputReservation:
    """Prevent two processes from silently writing the same report path.

    ``acquire`` creates ``<output>.lock`` with O_EXCL before expensive work.
    ``write`` first creates a process-unique temporary file, then atomically
    replaces the destination.  Existing reports are immutable by default.
    """

    def __init__(self, output: pathlib.Path, *, overwrite: bool = False):
        self.output = output.resolve()
        self.overwrite = bool(overwrite)
        self.lock = self.output.with_name(self.output.name + ".lock")
        self._owned = False
        self._tmp: pathlib.Path | None = None

    def acquire(self) -> "JsonOutputReservation":
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if self.output.exists() and not self.overwrite:
            raise SystemExit(
                f"output already exists: {self.output}; choose a new path or "
                "pass --overwrite-output explicitly"
            )
        metadata = {
            "pid": os.getpid(),
            "started_unix": time.time(),
            "output": str(self.output),
            "argv": sys.argv,
        }
        try:
            fd = os.open(self.lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError as exc:
            owner = ""
            try:
                owner = self.lock.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            raise SystemExit(
                f"output is reserved by another run: {self.lock}"
                + (f" owner={owner}" if owner else "")
                + "; verify that process before removing a stale lock"
            ) from exc
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(metadata, stream, ensure_ascii=False)
            stream.write("\n")
        self._owned = True
        atexit.register(self.release)
        return self

    def write(self, payload: Any) -> None:
        if not self._owned:
            raise RuntimeError("output reservation has not been acquired")
        self._tmp = self.output.with_name(
            f".{self.output.name}.tmp-{os.getpid()}-{time.time_ns()}"
        )
        with self._tmp.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if self.output.exists() and not self.overwrite:
            self._tmp.unlink(missing_ok=True)
            self._tmp = None
            raise SystemExit(
                f"output appeared while the run was active: {self.output}; "
                "refusing to overwrite it"
            )
        os.replace(self._tmp, self.output)
        self._tmp = None
        self.release()

    def release(self) -> None:
        if self._tmp is not None:
            self._tmp.unlink(missing_ok=True)
            self._tmp = None
        if self._owned:
            self.lock.unlink(missing_ok=True)
            self._owned = False


def reserve_json_output(
    output: str | pathlib.Path,
    *,
    overwrite: bool = False,
) -> JsonOutputReservation:
    return JsonOutputReservation(pathlib.Path(output), overwrite=overwrite).acquire()
