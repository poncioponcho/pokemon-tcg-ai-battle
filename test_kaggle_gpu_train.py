"""Regression tests for the standalone Kaggle training launcher."""

import io
import tarfile

import pytest

from kaggle_gpu_train import untar


def _write_tar(path, member):
    with tarfile.open(path, "w") as archive:
        archive.addfile(member, io.BytesIO(b"ok") if member.isfile() else None)


def test_untar_extracts_regular_file(tmp_path):
    archive_path = tmp_path / "safe.tar"
    member = tarfile.TarInfo("nested/payload.txt")
    member.size = 2
    _write_tar(archive_path, member)

    destination = tmp_path / "output"
    untar(archive_path, destination)

    assert (destination / "nested/payload.txt").read_bytes() == b"ok"


def test_untar_rejects_parent_traversal(tmp_path):
    archive_path = tmp_path / "traversal.tar"
    member = tarfile.TarInfo("../escaped.txt")
    member.size = 2
    _write_tar(archive_path, member)

    with pytest.raises(ValueError, match="escapes destination"):
        untar(archive_path, tmp_path / "output")

    assert not (tmp_path / "escaped.txt").exists()


def test_untar_rejects_links(tmp_path):
    archive_path = tmp_path / "link.tar"
    member = tarfile.TarInfo("link")
    member.type = tarfile.SYMTYPE
    member.linkname = "../escaped.txt"
    _write_tar(archive_path, member)

    with pytest.raises(ValueError, match="unsafe tar member type"):
        untar(archive_path, tmp_path / "output")
