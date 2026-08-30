"""Command-line entry point for Emix."""

from __future__ import annotations

import argparse
from pathlib import Path

from emix import __version__
from emix.cpm import CpmShell


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emix",
        description="Use a modern Unix machine through a retro computer personality.",
    )
    parser.add_argument(
        "personality",
        nargs="?",
        default="cpm",
        choices=("cpm",),
        help="computer personality to start (default: cpm)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="host directory exposed as drive A: (default: current directory)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Emix {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        build_parser().error(f"drive root is not a directory: {root}")

    shell = CpmShell(root)
    while True:
        try:
            shell.cmdloop()
            return 0
        except KeyboardInterrupt:
            shell.stdout.write("^C\n")
            shell.stdout.flush()

