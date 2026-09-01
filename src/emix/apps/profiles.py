"""Application profiles: what an application is, and how to start it.

A profile carries configuration and compatibility knowledge, never a
copyrighted byte. Emix ships no operating systems and no applications; a
profile only describes software the user already has.

TOML is read with the standard library's :mod:`tomllib`, which is why Emix
requires Python 3.11. That is cheaper than an INI schema with invented nesting
conventions, and cheaper than a ``tomli`` dependency on a project whose whole
pitch is having none.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

from emix.apps import names, session
from emix.errors import Code, EmixError

#: Checked before the default location.
ENVIRONMENT = "EMIX_APPS"

#: Personalities an application may belong to. Validated here so a typo does
#: not produce a profile that silently belongs to nothing.
KNOWN_SYSTEMS = frozenset({"cpm", "vms", "cms"})

#: Every key a profile may set. A misspelling in a config file is expensive to
#: find by its effects, so it is refused by name instead.
_KNOWN_KEYS = frozenset(
    {
        "backend",
        "program",
        "application",
        "terminal",
        "executable",
        "command",
        "system",
        "notes",
        "exit",
        "columns",
        "rows",
        "timeout",
        "auxiliary",
        "alias-suffix",
    }
)

#: Alongside `emix.toml`, wherever this host keeps that. See
#: :func:`emix.config.config_dir`.
_DEFAULT_NAME = "apps.toml"


@dataclass(frozen=True)
class Profile:
    """One logical application, resolved from configuration."""

    name: str
    backend: str
    #: Program name as the guest sees it, e.g. ``TE.COM``.
    program: str
    #: Host directory whose contents become the application drive.
    application: Path
    #: Personality this application belongs to. Its filenames, prompts and
    #: backend are specific to one system, so it is only offered there.
    system: str = "cpm"
    #: Verb that launches this application from inside a personality. Defaults
    #: to the program's stem, so ``TE.COM`` answers to ``TE``.
    command: str = ""
    #: Terminal the application expects. Recorded, not yet enforced.
    terminal: str = "vt100"
    #: Explicit path to the backend executable, if it is not on ``PATH``.
    executable: Path | None = None
    #: Columns and rows the application assumes. Recorded so Emix can warn
    #: rather than silently hand a 132-column program an 80-column terminal.
    columns: int = 80
    rows: int = 24
    #: Seconds a non-interactive session may run before it is stopped. A
    #: human can always interrupt; a script cannot, and a wedged guest with
    #: nobody watching is exactly how TE floods a log.
    timeout: int = 60
    #: Shown before the application starts: keys, conventions, anything the
    #: program expects that a modern user would not guess. This is where
    #: compatibility knowledge lives, rather than in an adapter — the quirks
    #: found so far belong to applications, not to emulators.
    notes: str = ""
    #: How to leave the program, printed last and on its own.
    #:
    #: A full-screen program clears the display on startup, so the notes are
    #: gone by the time the user wants out. This line is the one that must
    #: survive being read in a hurry.
    exit_hint: str = ""
    #: Character introducing an 8.3 collision suffix. Applications disagree
    #: about what they will parse; see :mod:`emix.apps.names`.
    alias_suffix: str = names.DEFAULT_SUFFIX
    #: Glob patterns for files the application makes for itself.
    auxiliary: tuple[str, ...] = session.DEFAULT_AUXILIARY

    @classmethod
    def from_table(cls, name: str, table: dict[str, object]) -> Profile:
        def text(key: str, *, required: bool = True, default: str = "") -> str:
            value = table.get(key, default)
            if required and not value:
                raise EmixError(Code.SYNTAX, f"app.{name}", f"missing required key '{key}'")
            if not isinstance(value, str):
                raise EmixError(Code.SYNTAX, f"app.{name}.{key}", "expected a string")
            return value

        program = text("program")
        command = text("command", required=False, default=program.split(".")[0]).upper()
        if not command:
            raise EmixError(Code.SYNTAX, f"app.{name}.command", "must not be empty")
        system = text("system", required=False, default="cpm").lower()
        if system not in KNOWN_SYSTEMS:
            raise EmixError(
                Code.SYNTAX,
                f"app.{name}.system",
                f"unknown personality (known: {', '.join(sorted(KNOWN_SYSTEMS))})",
            )

        def number(key: str, default: int, low: int, high: int) -> int:
            value = table.get(key, default)
            # bool is a subclass of int in Python, so `timeout = true` would
            # otherwise validate and then behave as 1 second.
            if isinstance(value, bool) or not isinstance(value, int):
                raise EmixError(Code.SYNTAX, f"app.{name}.{key}", "expected a whole number")
            if not low <= value <= high:
                raise EmixError(
                    Code.SYNTAX, f"app.{name}.{key}", f"expected between {low} and {high}"
                )
            return value

        unknown = set(table) - _KNOWN_KEYS
        if unknown:
            raise EmixError(
                Code.SYNTAX, f"app.{name}", f"unknown key(s): {', '.join(sorted(unknown))}"
            )

        def patterns(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
            value = table.get(key)
            if value is None:
                return default
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise EmixError(Code.SYNTAX, f"app.{name}.{key}", "expected a list of patterns")
            return tuple(value)

        def optional_path(key: str) -> Path | None:
            value = table.get(key)
            if value is None:
                return None
            if not isinstance(value, str) or not value:
                raise EmixError(Code.SYNTAX, f"app.{name}.{key}", "expected a path as a string")
            return Path(value).expanduser()

        executable = optional_path("executable")
        return cls(
            name=name,
            backend=text("backend"),
            program=program,
            command=command,
            system=system,
            application=Path(text("application")).expanduser(),
            terminal=text("terminal", required=False, default="vt100"),
            executable=executable,
            alias_suffix=text("alias-suffix", required=False, default=names.DEFAULT_SUFFIX),
            notes=text("notes", required=False),
            exit_hint=text("exit", required=False),
            columns=number("columns", 80, 1, 1000),
            rows=number("rows", 24, 1, 1000),
            timeout=number("timeout", 60, 1, 86400),
            auxiliary=patterns("auxiliary", session.DEFAULT_AUXILIARY),
        )


def config_path() -> Path:
    from emix.config import config_dir

    override = os.environ.get(ENVIRONMENT)
    return Path(override).expanduser() if override else config_dir() / _DEFAULT_NAME


def load(path: Path | None = None) -> dict[str, Profile]:
    """Read every profile from the configuration file, or none if absent."""
    source = path or config_path()
    if not source.is_file():
        return {}
    try:
        payload = tomllib.loads(source.read_text(encoding="utf-8"))
    except OSError as error:
        raise EmixError(Code.IO_ERROR, str(source), str(error)) from error
    except tomllib.TOMLDecodeError as error:
        raise EmixError(Code.SYNTAX, str(source), str(error)) from error

    apps = payload.get("app", {})
    if not isinstance(apps, dict):
        raise EmixError(Code.SYNTAX, str(source), "'app' must be a table of profiles")
    profiles: dict[str, Profile] = {}
    for name, table in apps.items():
        if not isinstance(table, dict):
            raise EmixError(Code.SYNTAX, f"app.{name}", "expected a table, as [app.name]")
        profile = Profile.from_table(name, table)
        clash = next(
            (other for other in profiles.values() if other.command == profile.command), None
        )
        if clash is not None:
            raise EmixError(
                Code.SYNTAX,
                profile.command,
                f"both '{clash.name}' and '{name}' claim this command",
            )
        profiles[name] = profile
    return profiles


def get(name: str, path: Path | None = None) -> Profile:
    profiles = load(path)
    try:
        return profiles[name]
    except KeyError:
        known = ", ".join(sorted(profiles)) or "none configured"
        raise EmixError(Code.NO_FILE, name, f"unknown application (known: {known})") from None


EXAMPLE = (
    "# Emix application profiles. Emix ships no applications; this only\n"
    "# describes software you already have installed.\n"
    "\n"
    "[app.te-cpm]\n"
    'backend = "runcpm"\n'
    'program = "TE.COM"\n'
    'application = "~/dev/RunCPM/DISK/A/0"\n'
    'terminal = "vt100"\n'
    '# alias-suffix = "_"   # TE rejects "~" and "-" in a command tail\n'
    '# executable = "~/dev/RunCPM/RunCPM/RunCPM"\n'
    "# notes shown before the application starts:\n"
    '# notes = "ESC opens the menu: S save, X exit. Delete removes to the right."\n'
)
