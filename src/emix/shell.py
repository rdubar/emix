"""The shared personality engine: a REPL, a verb table, and host fallthrough.

This deliberately does not use :mod:`cmd`. ``cmd.Cmd`` dispatches on an exact
``do_<name>`` attribute after splitting the line on identifier characters,
which cannot express DCL's unambiguous abbreviation (``DIR``, ``DIRE`` and
``DIRECTORY`` are all the same verb) or its ``/QUALIFIER=value`` syntax.
Personalities subclass :class:`Shell` and declare verbs with :func:`verb`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import contextlib
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shlex
import sys
from typing import TextIO

from emix.errors import Code, EmixError
from emix.host import DriveSet, run_host_command


@dataclass(frozen=True)
class Invocation:
    """One parsed command line handed to a verb handler."""

    verb: str
    #: Positional arguments after the verb, already word-split.
    args: list[str]
    #: ``/NAME`` or ``/NAME=VALUE`` qualifiers; empty for personalities
    #: that do not use them. A bare qualifier maps to ``""``.
    qualifiers: dict[str, str] = field(default_factory=dict)
    #: Everything after the verb, unsplit, for verbs that want it raw.
    tail: str = ""

    def qualifier(self, name: str) -> str | None:
        return self.qualifiers.get(name.upper())

    def has(self, name: str) -> bool:
        return name.upper() in self.qualifiers


@dataclass(frozen=True)
class Verb:
    """A command in a personality's vocabulary."""

    name: str
    handler: Callable[..., bool | None]
    summary: str
    usage: str = ""
    aliases: tuple[str, ...] = ()
    #: Shortest accepted abbreviation. ``None`` means the verb must be typed
    #: in full, which is what CP/M and CMS expect.
    min_abbrev: int | None = None
    #: Hide from the command summary without removing the verb.
    hidden: bool = False

    def matches(self, typed: str) -> bool:
        typed = typed.upper()
        if typed == self.name or typed in self.aliases:
            return True
        if self.min_abbrev is None:
            return False
        return len(typed) >= self.min_abbrev and self.name.startswith(typed)


def verb(
    name: str,
    *,
    summary: str,
    usage: str = "",
    aliases: Sequence[str] = (),
    min_abbrev: int | None = None,
    hidden: bool = False,
) -> Callable[[Callable[..., bool | None]], Callable[..., bool | None]]:
    """Mark a method as a command in the enclosing personality."""

    def decorate(function: Callable[..., bool | None]) -> Callable[..., bool | None]:
        function._emix_verb = Verb(  # type: ignore[attr-defined]
            name=name.upper(),
            handler=function,
            summary=summary,
            usage=usage or name.upper(),
            aliases=tuple(alias.upper() for alias in aliases),
            min_abbrev=min_abbrev,
            hidden=hidden,
        )
        return function

    return decorate


class Shell:
    """Base personality. Subclasses supply a vocabulary and a house style."""

    #: Short identifier used on the command line, e.g. ``cpm``.
    key = "shell"
    #: Human-readable name shown in the banner.
    title = "Emix"
    #: Whether unrecognised verbs are offered to the host as executables.
    host_fallthrough = True
    #: Whether input is folded to upper case before dispatch.
    fold_input = True

    def __init__(
        self,
        drives: DriveSet,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        history: Path | None = None,
    ) -> None:
        self.drives = drives
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.interactive = stdin is None and _is_a_tty(self.stdin)
        self.history_path = history
        self.verbs: list[Verb] = self._collect_verbs()
        self.running = True

    # -- vocabulary -----------------------------------------------------

    def _collect_verbs(self) -> list[Verb]:
        found: dict[str, Verb] = {}
        for klass in reversed(type(self).__mro__):
            for attribute in vars(klass).values():
                declared = getattr(attribute, "_emix_verb", None)
                if declared is not None:
                    found[declared.name] = declared
        return sorted(found.values(), key=lambda item: item.name)

    def lookup(self, typed: str) -> Verb | None:
        """Find a verb, preferring an exact name over an abbreviation."""
        typed = typed.upper()
        for candidate in self.verbs:
            if typed == candidate.name or typed in candidate.aliases:
                return candidate
        partial = [candidate for candidate in self.verbs if candidate.matches(typed)]
        if len(partial) > 1:
            raise EmixError(Code.AMBIGUOUS_VERB, typed, ", ".join(v.name for v in partial))
        return partial[0] if partial else None

    # -- house style, overridden by each personality --------------------

    def banner(self) -> str:
        return f"{self.title}\n"

    def prompt(self) -> str:
        return "> "

    def render_error(self, error: EmixError) -> str:
        return f"?{error.code.name}\n"

    def after_command(self, line: str) -> None:
        """Hook for personalities that print something after every command."""

    def farewell(self) -> str:
        return ""

    # -- parsing --------------------------------------------------------

    def split(self, line: str) -> list[str]:
        try:
            return shlex.split(line)
        except ValueError as error:
            raise EmixError(Code.SYNTAX, line, str(error)) from error

    def parse(self, line: str) -> Invocation | None:
        """Turn a raw line into an :class:`Invocation`. ``None`` means empty."""
        stripped = line.strip()
        if not stripped:
            return None
        head, _, remainder = _split_first_word(stripped)
        return Invocation(verb=head, args=self.split(remainder), tail=remainder)

    # -- the loop -------------------------------------------------------

    def run(self) -> int:
        """Read, evaluate and print until the personality stops."""
        self._enable_history()
        self.write(self.banner())
        while self.running:
            try:
                line = self.read_line()
            except KeyboardInterrupt:
                self.write("^C\n")
                continue
            except EOFError:
                self.write("\n" + self.farewell())
                break
            self.execute(line)
        self._save_history()
        return 0

    def read_line(self) -> str:
        if self.interactive:
            return input(self.prompt())
        self.write(self.prompt())
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\n")

    def execute(self, line: str) -> None:
        """Dispatch one line, converting expected failures into house style."""
        try:
            invocation = self.parse(line)
            if invocation is None:
                return
            self.dispatch(invocation)
        except EmixError as error:
            self.write(self.render_error(error))
        except KeyboardInterrupt:
            self.write("^C\n")
        else:
            self.after_command(line)

    def dispatch(self, invocation: Invocation) -> None:
        found = self.lookup(invocation.verb)
        if found is not None:
            if found.handler(self, invocation):
                self.running = False
            return
        if not self.host_fallthrough:
            raise EmixError(Code.UNKNOWN_VERB, invocation.verb)
        self.run_host(invocation)

    def run_host(self, invocation: Invocation) -> None:
        """Offer the line to the host as an executable, with no shell."""
        run_host_command([invocation.verb, *invocation.args], cwd=self.drives.default)

    # -- output ---------------------------------------------------------

    def write(self, text: str) -> None:
        self.stdout.write(text)
        self.stdout.flush()

    def confirm(self, question: str) -> bool:
        """Ask a yes/no question. Anything but an explicit yes means no."""
        self.write(question)
        if self.interactive:
            try:
                answer = input()
            except (EOFError, KeyboardInterrupt):
                self.write("\n")
                return False
        else:
            answer = self.stdin.readline()
            self.write(answer)
        return answer.strip().upper() in {"Y", "YES"}

    # -- readline history ------------------------------------------------

    def _enable_history(self) -> None:
        if not self.interactive or self.history_path is None:
            return
        try:
            import readline
        except ImportError:  # pragma: no cover - readline is absent on some hosts
            return
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError, ValueError):
            readline.read_history_file(self.history_path)
        readline.set_history_length(2000)

    def _save_history(self) -> None:
        if not self.interactive or self.history_path is None:
            return
        try:
            import readline

            readline.write_history_file(self.history_path)
        except (ImportError, OSError):  # pragma: no cover
            pass


def _split_first_word(line: str) -> tuple[str, str, str]:
    """Split ``line`` into its first word, the gap, and everything after."""
    match = re.search(r"\s", line)
    if match is None:
        return line, "", ""
    return line[: match.start()], match.group(), line[match.end() :].strip()


def _is_a_tty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):  # closed or unusual stream
        return False


def default_history_path(key: str) -> Path:
    """Per-personality history file, honouring ``XDG_STATE_HOME``."""
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "emix" / f"{key}_history"
