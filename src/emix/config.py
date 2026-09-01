"""Settings that persist between sessions.

Emix works with no configuration at all, and that must stay true: a fresh
install run from a checkout should behave exactly as documented. This file
only removes repetition — the drives you always mount, the personality you
always start, the colour you prefer.

Precedence is the ordinary one, and is worth stating because it is the thing
people get wrong: **command line, then configuration file, then the built-in
default.** A flag always wins, which is what makes a script's behaviour
readable from the script alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import tomllib

from emix.assist import COLOURS
from emix.errors import Code, EmixError
from emix.host import on_windows

#: Checked before the default location.
ENVIRONMENT = "EMIX_CONFIG"

_DEFAULT_NAME = "emix.toml"


def config_dir() -> Path:
    """Where this host keeps per-user configuration.

    ``~/.config`` on Unix, ``%APPDATA%`` on Windows. Unix's spelling works on
    Windows too if you make the directory, but nobody would think to look
    there, and a setting the user cannot find is a setting that does not work.
    """
    if on_windows():
        roaming = os.environ.get("APPDATA")
        base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
        return base / "emix"
    return Path("~/.config/emix").expanduser()


@dataclass(frozen=True)
class Config:
    """Everything a configuration file may set."""

    personality: str = ""
    #: Host directories to mount, per personality, plus a ``default`` key.
    drives: dict[str, list[Path]] = field(default_factory=dict)
    strict: bool | None = None
    #: Empty means "not chosen", which lets Emix ask the terminal instead of
    #: quietly overriding the answer with a default.
    hint_colour: str = ""
    #: The main text colour. Empty means "not chosen", as above.
    screen: str = ""

    def mounts_for(self, personality: str) -> list[Path]:
        """Configured drives for a personality, falling back to the default."""
        return self.drives.get(personality) or self.drives.get("default") or []


def config_path() -> Path:
    """The configuration file, in whatever this host calls that place."""
    override = os.environ.get(ENVIRONMENT)
    return Path(override).expanduser() if override else config_dir() / _DEFAULT_NAME


def load(path: Path | None = None) -> Config:
    """Read the configuration file, or return defaults if there is none."""
    source = path or config_path()
    if not source.is_file():
        return Config()
    try:
        payload_text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise EmixError(Code.IO_ERROR, str(source), str(error)) from error
    try:
        payload = tomllib.loads(payload_text)
    except OSError as error:
        raise EmixError(Code.IO_ERROR, str(source), str(error)) from error
    except tomllib.TOMLDecodeError as error:
        raise EmixError(Code.SYNTAX, str(source), toml_detail(payload_text, error)) from error

    emix = payload.get("emix", {})
    if not isinstance(emix, dict):
        raise EmixError(Code.SYNTAX, str(source), "'emix' must be a table")

    colour = _colour(emix, "hint-colour", source)
    screen = _colour(emix, "screen", source)

    strict = emix.get("strict")
    if strict is not None and not isinstance(strict, bool):
        raise EmixError(Code.SYNTAX, str(source), "'strict' must be true or false")

    # Not `or {}`: that quietly accepts every false-valued wrong type, so a
    # `drives = []` typo would read as "no drives configured" rather than as
    # the mistake it is.
    configured = payload.get("drives", {})
    if not isinstance(configured, dict):
        raise EmixError(Code.SYNTAX, str(source), "'drives' must be a table")
    drives: dict[str, list[Path]] = {}
    for key, value in configured.items():
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise EmixError(Code.SYNTAX, f"drives.{key}", "expected a path or a list of paths")
        drives[key] = [Path(item).expanduser() for item in value]

    return Config(
        personality=str(emix.get("personality", "")),
        drives=drives,
        strict=strict,
        hint_colour=colour,
        screen=screen,
    )


#: TOML reads a backslash inside a double-quoted string as an escape, so a
#: Windows path pasted straight in fails on `\U` or `\x` with a message about
#: hex values that tells the reader nothing about what to do.
_BACKSLASH_IN_QUOTES = re.compile(r'"[^"\n]*\\[^"\n]*"')


def toml_detail(text: str, error: Exception) -> str:
    """The parser's words, plus what to do about them if we can tell."""
    detail = str(error)
    if _BACKSLASH_IN_QUOTES.search(text):
        detail += (
            ". A Windows path in double quotes needs its backslashes doubled, "
            "because TOML reads a single one as an escape. Single quotes take "
            "the path exactly as written: drives = ['C:\\Users\\me\\Documents'] "
            "is the easiest spelling, and forward slashes work too."
        )
    return detail


def _colour(emix: dict[str, object], key: str, source: Path) -> str:
    """One colour-valued key, refused by name if it is not a colour Emix has."""
    value = str(emix.get(key, ""))
    if value and value not in COLOURS:
        raise EmixError(
            Code.SYNTAX, str(source), f"unknown {key} {value!r} (try {', '.join(COLOURS)})"
        )
    return value


EXAMPLE = (
    "# ~/.config/emix/emix.toml — every key is optional.\n"
    "\n"
    "[emix]\n"
    'personality = "cpm"\n'
    "strict = false\n"
    'screen = "bright-green"        # main text; "none" for your terminal\'s own colour\n'
    'hint-colour = "bright-yellow"  # Emix\'s own lines, never the same as the screen\n'
    "# Any of: yellow cyan green magenta blue red grey white, each with a\n"
    "# bright- twin, or none.\n"
    "\n"
    "[drives]\n"
    '# Mounted in order. "default" applies to any personality without its own.\n'
    'default = ["~/Documents"]\n'
    'cpm = ["~/Documents", "~/src"]\n'
)
