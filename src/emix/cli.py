"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from emix import __version__
from emix import config as emix_config
from emix import update as emix_update
from emix.apps import profiles as app_profiles
from emix.apps.runner import describe_profiles, open_document
from emix.assist import COLOURS
from emix.config import Config
from emix.errors import EmixError
from emix.host import Drive, DriveSet
from emix.personalities import DRIVE_NAMES, PERSONALITIES, get
from emix.shell import Shell, default_history_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emix",
        description="Use your own computer through a historical computer personality.",
        epilog=(
            "Drives are mounted in order: the first --mount becomes the first drive "
            "name for the personality (A: for CP/M, DKA0: for VMS), and so on. "
            "Files stay real host files throughout."
        ),
    )
    parser.add_argument(
        "personality",
        nargs="?",
        default=None,
        choices=sorted(PERSONALITIES),
        help="personality to start (default: cpm, or the configured one)",
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
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "authentic output only, with no Emix hints "
            "(default: on for scripts and pipes, off when interactive)"
        ),
    )
    parser.add_argument(
        "--hint-colour",
        "--hint-color",
        dest="hint_colour",
        choices=sorted(COLOURS),
        default=None,
        metavar="COLOUR",
        help="colour for Emix hints (default: yellow; also $EMIX_HINT_COLOUR, $NO_COLOR)",
    )
    parser.add_argument(
        "--screen",
        choices=sorted(COLOURS),
        default=None,
        metavar="COLOUR",
        help=(
            "colour for the main text (default: green on a dark terminal, "
            "none elsewhere; also $EMIX_SCREEN, $NO_COLOR)"
        ),
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="report what is configured and what is missing, and change nothing",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="show how this copy was installed and offer to update it",
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


def build_open_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emix open",
        description="Open a host document in a historical application.",
    )
    parser.add_argument("document", type=Path, help="host file to open")
    parser.add_argument(
        "--with", "-w", dest="app", required=True, metavar="APP", help="configured application"
    )
    parser.add_argument("--yes", "-y", action="store_true", help="commit without confirming")
    parser.add_argument("--keep", action="store_true", help="keep the session workspace after exit")
    parser.add_argument(
        "--stay",
        action="store_true",
        help="stay at the guest prompt after the application exits",
    )
    return parser


def run_open(argv: list[str]) -> int:
    args = build_open_parser().parse_args(argv)
    try:
        profile = app_profiles.get(args.app)
        return open_document(
            args.document, profile, assume_yes=args.yes, keep=args.keep, stay=args.stay
        )
    except EmixError as error:
        print(f"emix: {error}", file=sys.stderr)
        return 1


def run_apps(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="emix apps", description="List configured applications.")
    parser.parse_args(argv)
    try:
        return describe_profiles(app_profiles.load())
    except EmixError as error:
        print(f"emix: {error}", file=sys.stderr)
        return 1


#: Subcommands checked before the personality parser, so ``emix cpm`` keeps
#: working exactly as it did.
SUBCOMMANDS = {"open": run_open, "apps": run_apps}


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] in SUBCOMMANDS:
        return SUBCOMMANDS[arguments[0]](arguments[1:])

    parser = build_parser()
    args = parser.parse_args(arguments)

    if args.update:
        return emix_update.update()

    if args.setup:
        # Answered before a personality starts, because the point is to find
        # out whether one will work. Any of them can say it; CP/M is nearest.
        shell = get("cpm")(DriveSet([Drive.create("A", Path.cwd())]), history=None)
        shell.execute("SETUP")
        return 0

    try:
        settings = emix_config.load()
    except EmixError as error:
        parser.error(f"configuration: {error}")

    # Command line, then configuration, then the built-in default. A flag
    # always wins, so a script's behaviour is readable from the script.
    personality = args.personality or settings.personality or "cpm"
    if personality not in PERSONALITIES:
        parser.error(f"unknown personality {personality!r}")

    mounts = list(args.mount or [])
    if args.root is not None:
        mounts.insert(0, args.root)
    if not mounts:
        mounts = settings.mounts_for(personality) or [Path.cwd()]

    try:
        drives = build_drives(personality, mounts)
    except EmixError as error:
        parser.error(str(error))

    factory = get(personality)
    history = None if (args.no_history or args.command) else default_history_path(personality)
    shell = factory(
        drives,
        history=history,
        strict=args.strict if args.strict is not None else settings.strict,
        hint_colour=args.hint_colour or settings.hint_colour,
        screen=args.screen or settings.screen,
    )

    if args.command:
        # A script must be able to tell that something failed. An interactive
        # session carries on; a one-shot invocation reports.
        remaining = list(args.command)
        ok = True
        while True:
            with shell.session():
                while remaining:
                    ok = shell.execute(remaining.pop(0)) and ok
                    if shell.becoming is not None:
                        break
            if shell.becoming is None:
                return 0 if ok else 1
            try:
                shell = _hand_over(shell, args, settings)
            except EmixError as error:
                shell.becoming = None
                shell.write(shell.render_error(error))
                return 1

    # BECOME stops the loop and names its successor, so a session is a
    # sequence of personalities over one set of mounts rather than one shell.
    while True:
        try:
            code = shell.run()
        except KeyboardInterrupt:
            shell.write("\n")
            return 130
        if shell.becoming is None:
            return code
        try:
            shell = _hand_over(shell, args, settings)
        except EmixError as error:
            shell.becoming = None
            shell.write(shell.render_error(error))


def _hand_over(shell: Shell, args: argparse.Namespace, settings: Config) -> Shell:
    """Build the personality this one is handing to, over the same drives."""
    key = shell.becoming or shell.key
    factory = get(key)
    return factory(
        shell.drives.renamed(DRIVE_NAMES[key]),
        history=None if args.no_history else default_history_path(key),
        strict=shell.strict,
        hint_colour=shell.hint_colour,
        screen=shell.screen_colour,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
