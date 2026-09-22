"""Loops shared by steps that rewrite files one by one."""

from collections import Counter

from .ui import note, warn


def extension(text):
    """"MP3" / ".mp3" -> ".mp3"."""
    return "." + text.lower().lstrip(".")


def convert_extensions(args):
    """(from, to) extensions for `convert`, or None if they match."""
    from_ext, to_ext = extension(args.from_ext), extension(args.to_ext)
    if from_ext == to_ext:
        note("from and to formats are the same -- nothing to do.")
        return None
    return from_ext, to_ext


def process_each(paths, action, verb, noun):
    """`action(path)` for each path, printing what it returns and a
    tally. `verb` names the action, e.g. "convert"."""
    done = f"{verb}ed" if not verb.endswith("e") else f"{verb}d"
    counts = Counter()
    for path in paths:
        try:
            result = action(path)
        except Exception as exc:
            warn(f"Failed to {verb} {path}: {exc}")
            counts["error"] += 1
            continue
        print(f"{done.capitalize()}: {result}")
        counts["done"] += 1
    print(f"\n{counts['done']} {noun}(s) {done}, {counts['error']} "
          f"error(s).")
    return counts
