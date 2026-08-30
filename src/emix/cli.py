"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from emix import __version__
from emix.errors import EmixError
from emix.host import Drive, DriveSet
from emix.personalities import DRIVE_NAMES, PERSONALITIES, get
from emix.shell import default_history_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emix",
        description="Use a modern Unix machine through a historical computer personality.",
        epilog=(
            "Drives are mounted in order: the first --mount becomes the first drive "
            "name for the personality (A: for CP/M, DKA0: for VMS), and so on. "
            "Files stay real host files throughout."
        ),
    )
    parser.add_argument(
        "personality",
        nargs="?",
        default="cpm",
        choices=sorted(PERSONALITIES),
        help="personality to start (default: cpm)",
    )
    parser.add_argument(
        "--mount",
        "-m",
        type=Path,
        action="append",
        metavar="DIR",
        help="host directory to expose as the next drive (repeatable; default: .)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        metavar="DIR",
        help="alias for a single --mount, kept for compatibility",
    )
    parser.add_argument(
        "--command",
        "-c",
        action="append",
        metavar="TEXT",
        help="run a command and exit (repeatable); implies --no-history",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="do not read or write a readline history file",
    )
    parser.add_argument("--version", action="version", version=f"Emix {__version__}")
    return parser


def build_drives(personality: str, mounts: list[Path]) -> DriveSet:
    names = DRIVE_NAMES[personality]
    if len(mounts) > len(names):
        raise SystemExit(f"emix: {personality} personality supports at most {len(names)} drives")
    return DriveSet(
        # Fewer mounts than drive names is normal: mount what you need.
        Drive.create(name, path)
        for name, path in zip(names, mounts, strict=False)
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    mounts = list(args.mount or [])
    if args.root is not None:
        mounts.insert(0, args.root)
    if not mounts:
        mounts = [Path.cwd()]

    try:
        drives = build_drives(args.personality, mounts)
    except EmixError as error:
        parser.error(str(error))

    personality = get(args.personality)
    history = None if (args.no_history or args.command) else default_history_path(args.personality)
    shell = personality(drives, history=history)

    if args.command:
        for line in args.command:
            shell.execute(line)
        return 0

    try:
        return shell.run()
    except KeyboardInterrupt:
        shell.write("\n")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
