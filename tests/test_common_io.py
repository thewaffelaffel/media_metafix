"""Backups, apply's safety checks, scan errors and ffmpeg failures."""

import tarfile
from argparse import Namespace

import pytest

from common.ffmpeg import run_ffmpeg
from common.files import create_backup, maybe_backup
from common.queue import apply_queue, scan_one_file
from conftest import needs_ffmpeg, write_queue


def make_library(root):
    for rel in ("A/B/1.mkv", "A/B/2.mkv", "Skip/x.mkv", "A/B/junk.tmp"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel)
    (root / ".mmfignore").write_text("Skip/\n*.tmp\n")
    return root


@pytest.mark.parametrize("compress, suffix", [
    (True, ".tar.gz"), (False, ".tar"),
])
def test_create_backup_skips_ignored(tmp_path, compress, suffix):
    root = make_library(tmp_path / "lib")
    backup = create_backup(root, tmp_path / "tmp", compress)
    assert backup.parent == tmp_path / "tmp" / "backups"
    assert backup.name.startswith("lib-")
    assert backup.name.endswith(suffix)
    with tarfile.open(backup) as tar:
        assert sorted(tar.getnames()) == [".mmfignore", "A/B/1.mkv",
                                          "A/B/2.mkv"]
        assert tar.extractfile("A/B/1.mkv").read() == b"A/B/1.mkv"


def test_maybe_backup_honors_no_backup(tmp_path):
    root = make_library(tmp_path / "lib")
    maybe_backup(Namespace(no_backup=True, tmp_dir=tmp_path / "t"), root)
    assert not (tmp_path / "t").exists()
    maybe_backup(Namespace(no_backup=False, tmp_dir=tmp_path / "t"), root)
    assert len(list((tmp_path / "t" / "backups").iterdir())) == 1


def test_apply_queue_skips_ignored_missing_and_failures(tmp_path, capsys):
    root = make_library(tmp_path / "lib")
    queue = write_queue(tmp_path / "q.yml", (
        "A/B/1.mkv: {title: One}\n"
        "A/B/2.mkv: {title: Boom}\n"
        "Skip/x.mkv: {title: X}\n"
        "A/B/gone.mkv: {title: Gone}\n"
    ))
    written = []

    def write_fields(path, fields):
        if fields["title"] == "Boom":
            raise RuntimeError("disk on fire")
        written.append((path.relative_to(root).as_posix(), fields))

    counts = apply_queue(root, queue, write_fields)
    assert written == [("A/B/1.mkv", {"title": "One"})]
    assert (counts["applied"], counts["ignored"], counts["error"]) == \
        (1, 1, 2)
    err = capsys.readouterr().err
    assert "Ignored by .mmfignore, skipping" in err
    assert "File not found" in err
    assert "disk on fire" in err


def test_scan_one_file_outcomes(tmp_path, capsys):
    def crash(_path):
        raise ValueError("bad tags")

    with open(tmp_path / "q.yml", "w", encoding="utf-8") as queue_f:
        assert scan_one_file(queue_f, crash, "x.mkv") == "error"
        assert scan_one_file(queue_f, lambda _p: None, "y.mkv") == "ok"
        assert scan_one_file(
            queue_f, lambda _p: ("z.mkv", {"title": "Z"}, {}), "z.mkv",
        ) == "queued"
    assert "Unexpected error on x.mkv: bad tags" in capsys.readouterr().err
    assert (tmp_path / "q.yml").read_text() == "z.mkv:\n  title: Z\n"


@needs_ffmpeg
def test_run_ffmpeg_failure_removes_partial_output(tmp_path):
    tmp_out = tmp_path / ".partial.mkv"
    tmp_out.write_text("half-written")
    cmd = ["ffmpeg", "-loglevel", "error", "-i",
           str(tmp_path / "missing.mkv"), str(tmp_out)]
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        run_ffmpeg(cmd, tmp_out)
    assert not tmp_out.exists()
