"""String matching and filename helpers."""

import difflib
import re

FUZZY_SAME_ENOUGH = 0.92      # this similar counts as "already correct"
FUZZY_MATCH_THRESHOLD = 0.6   # min similarity to accept a search match
TITLE_CHAR_DIFF_THRESHOLD = 3  # max differing chars for filename == title

ILLEGAL_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def leading_int(value):
    """Leading integer of a field like '3/12', or None."""
    if value is None:
        return None
    match = re.match(r"\s*(\d+)", str(value))
    return int(match.group(1)) if match else None


def fuzzy_ratio(a, b):
    if not a or not b:
        return 0.0
    a, b = a.lower().strip(), b.lower().strip()
    return difflib.SequenceMatcher(None, a, b).ratio()


def char_diff_count(a, b):
    """Rough count of differing characters between two strings."""
    matcher = difflib.SequenceMatcher(None, a, b)
    return sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )


def titles_match(a, b):
    """True if `a` and `b` differ by at most a few characters."""
    diff = char_diff_count(a.lower().strip(), b.lower().strip())
    return diff <= TITLE_CHAR_DIFF_THRESHOLD


def should_replace(new, current):
    """True if `new` differs enough from `current` to queue."""
    return fuzzy_ratio(new, current) < FUZZY_SAME_ENOUGH


def best_fuzzy_match(candidates, target):
    """Key of the {key: text} candidate closest to `target`, or None
    if nothing reaches FUZZY_MATCH_THRESHOLD."""
    best_key, best_score = None, 0.0
    for key, text in candidates.items():
        score = fuzzy_ratio(text, target)
        if score > best_score:
            best_key, best_score = key, score
    return best_key if best_score >= FUZZY_MATCH_THRESHOLD else None


def sanitize_filename_part(text):
    return ILLEGAL_FILENAME_CHARS_RE.sub("", text).strip()


def render_filename(template, path, values):
    """Fill `template`'s %placeholders from `values`, keeping `path`'s
    extension unless the template uses %ext."""
    values = dict(values, **{"%ext": path.suffix.lstrip(".")})
    name = template
    # Longest first, so e.g. %series isn't clobbered by a %s placeholder.
    for placeholder in sorted(values, key=len, reverse=True):
        value = sanitize_filename_part(str(values[placeholder]))
        name = name.replace(placeholder, value)
    if "%ext" not in template:
        name += path.suffix
    name = sanitize_filename_part(name)
    if name in ("", ".", ".."):
        name = "_" + name
    return name
