"""Walking a library root, .mmfignore rules, and backups."""

import tarfile
from datetime import datetime
from pathlib import Path

from .ui import missing_package

try:
    import pathspec
except ImportError:
    pathspec = None

MMFIGNORE_FILENAME = ".mmfignore"


def load_mmfignore(root):
    """`root`'s .mmfignore as a pathspec, or None."""
    ignore_path = Path(root) / MMFIGNORE_FILENAME
    if not ignore_path.exists():
        return None
    if pathspec is None:
        missing_package(
            "pathspec", "pathspec",
            f"{ignore_path} is present but its rules can't be applied.",
        )
        return None
    with open(ignore_path, encoding="utf-8") as f:
        return pathspec.PathSpec.from_lines("gitwildmatch", f)


def is_ignored(spec, root, path):
    """True if `path` under `root` matches `spec` (None matches
    nothing)."""
    if spec is None:
        return False
    rel = path.relative_to(root).as_posix()
    if path.is_dir():
        rel += "/"
    return spec.match_file(rel)


def iter_dirs(path):
    return sorted(p for p in path.iterdir() if p.is_dir())


def iter_files(path):
    return sorted(p for p in path.iterdir() if p.is_file())


def iter_kept(spec, root, paths):
    """`paths` minus those `spec` ignores."""
    return (p for p in paths if not is_ignored(spec, root, p))


def iter_non_ignored_files(root, spec):
    """Every non-ignored file under `root`, pruning ignored dirs."""
    root = Path(root)
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in iter_kept(spec, root, sorted(current.iterdir())):
            if entry.is_dir():
                stack.append(entry)
            else:
                yield entry


def create_backup(root, tmp_dir, compress=True):
    """Tar every non-ignored file under `root` into tmp_dir/backups."""
    root = Path(root)
    spec = load_mmfignore(root)
    backups_dir = Path(tmp_dir) / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix, mode = (".tar.gz", "w:gz") if compress else (".tar", "w")
    backup_path = backups_dir / f"{root.name}-{timestamp}{suffix}"
    with tarfile.open(backup_path, mode) as tar:
        for path in iter_non_ignored_files(root, spec):
            tar.add(path, arcname=str(path.relative_to(root)))
    print(f"Backup created: {backup_path}")
    return backup_path


def maybe_backup(args, root, compress=True):
    if not args.no_backup:
        create_backup(root, args.tmp_dir, compress)
