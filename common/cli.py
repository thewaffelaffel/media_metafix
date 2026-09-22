"""argparse helpers shared by every step."""

import argparse
from pathlib import Path

# Working files live here, relative to the current directory -- NOT
# inside root.
DEFAULT_TMP_DIR = "tmp"
DEFAULT_QUEUE_FILE = str(Path(DEFAULT_TMP_DIR) / "changes.yml")
SCANNED_ROOT_HELP = "Root folder the queue was scanned from."


def add_root_arg(subparser, help_text):
    subparser.add_argument("root", help=help_text)


def add_queue_arg(subparser, help_text):
    subparser.add_argument(
        "queue", nargs="?", default=DEFAULT_QUEUE_FILE,
        help=f"{help_text} (default: %(default)s)",
    )


def add_backup_args(subparser):
    subparser.add_argument(
        "--no-backup", action="store_true",
        help="Skip the backup of root normally taken before this step.",
    )
    subparser.add_argument(
        "--tmp-dir", default=DEFAULT_TMP_DIR,
        help="Working directory for backups (default: %(default)s)",
    )


def build_parser(prog, doc, adders):
    """Top-level parser with one subcommand per `adders` callable."""
    parser = argparse.ArgumentParser(
        prog=prog, description=doc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="step", required=True)
    for add in adders:
        add(subparsers)
    return parser


def run_step(parser, handlers, argv=None):
    args = parser.parse_args(argv)
    return handlers[args.step](args)
