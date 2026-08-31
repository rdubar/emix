"""The shared personality engine: a REPL, a verb table, and host fallthrough.

This deliberately does not use :mod:`cmd`. ``cmd.Cmd`` dispatches on an exact
``do_<name>`` attribute after splitting the line on identifier characters,
which cannot express DCL's unambiguous abbreviation (``DIR``, ``DIRE`` and
``DIRECTORY`` are all the same verb) or its ``/QUALIFIER=value`` syntax.
Personalities subclass :class:`Shell` and declare verbs with :func:`verb`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
import contextlib
from dataclasses import dataclass, field
import io
import os
from pathlib import Path
import re
import shlex
import sys
from typing import ClassVar, TextIO

from emix import __version__
from emix.assist import (
    Concept,
    colourise,
    default_colour,
    did_you_mean,
    explain,
    translation_hint,
)
from emix.errors import Code, EmixError
from emix.host import DriveSet, run_host_command
from emix.terminal import background_is_dark


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
class Outcome:
    """What one command did.

    Separating "did it work" from "should the session end" keeps one boolean
    from having to mean both. It previously meant only the second, which is
    how ``UNIX false`` came to report success to a script: the handler had no
    way to say the command had failed.
    """

    #: Whether the command did what it was asked. A one-shot ``-c`` maps this
    #: to the process exit status.
    succeeded: bool = True
    #: Whether this ends the session.
    stop: bool = False


#: A command that ran and did not do what was asked.
FAILED = Outcome(succeeded=False)
#: A command that ends the session.
STOP = Outcome(stop=True)


@dataclass(frozen=True)
class ResolvedDocument:
    """One document an application was asked to open."""

    #: The existing host file, if there is one.
    host: Path | None = None
    #: The host leaf name to create, if there is not.
    new_name: str | None = None
    #: Directory a guest-created file returns to.
    home: Path = Path()


@dataclass(frozen=True)
class Verb:
    """A command in a personality's vocabulary."""

    name: str
    handler: Callable[..., Outcome | None]
    summary: str
    usage: str = ""
    aliases: tuple[str, ...] = ()
    #: Shortest accepted abbreviation. ``None`` means the verb must be typed
    #: in full, which is what CP/M and CMS expect.
    min_abbrev: int | None = None
    #: Hide from the command summary without removing the verb.
    hidden: bool = False
    #: An Emix command *about* the session rather than part of it. Meta verbs
    #: do not become "the last command", so EXPLAIN describes what you were
    #: actually doing rather than describing itself.
    meta: bool = False

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
    meta: bool = False,
) -> Callable[[Callable[..., Outcome | None]], Callable[..., Outcome | None]]:
    """Mark a method as a command in the enclosing personality."""

    def decorate(function: Callable[..., Outcome | None]) -> Callable[..., Outcome | None]:
        function._emix_verb = Verb(  # type: ignore[attr-defined]
            name=name.upper(),
            handler=function,
            summary=summary,
            usage=usage or name.upper(),
            aliases=tuple(alias.upper() for alias in aliases),
            min_abbrev=min_abbrev,
            hidden=hidden,
            meta=meta,
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
    #: What this personality calls each :class:`~emix.assist.Concept`. Empty
    #: means Emix stays silent rather than inventing an equivalent.
    translations: ClassVar[dict[Concept, str]] = {}
    #: What this personality wants to add to an explanation of each error
    #: code, beyond :data:`~emix.assist.GENERAL`.
    explanations: ClassVar[dict[str, str]] = {}
    #: Marker on every assisted line. It must not resemble a period
    #: diagnostic, or the assistance starts lying about history.
    hint_marker = "Emix: "

    def __init__(
        self,
        drives: DriveSet,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        history: Path | None = None,
        strict: bool | None = None,
        hint_colour: str | None = None,
    ) -> None:
        self.drives = drives
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.interactive = stdin is None and _is_a_tty(self.stdin)
        self.history_path = history
        self.verbs: list[Verb] = self._collect_verbs()
        self.running = True
        self._apps: dict[str, object] | None = None
        # Scripts must not depend on a guess, so anything non-interactive is
        # strict unless the caller says otherwise.
        self.strict = (not self.interactive) if strict is None else strict
        # Colour is for a human looking at a terminal. Anywhere else it is
        # corruption: escape codes in a pipe break scripts and golden
        # transcripts alike. NO_COLOR is the cross-tool convention.
        # Decide eligibility *before* asking the terminal anything. Probing a
        # terminal whose answer we would then throw away writes an escape
        # sequence for no reason, which a NO_COLOR user has explicitly asked
        # us not to do.
        if os.environ.get("NO_COLOR") is not None or not _is_a_tty(self.stdout):
            self.hint_colour = "none"
        else:
            chosen = hint_colour or os.environ.get("EMIX_HINT_COLOUR")
            if not chosen:
                # Green only where we know the screen is dark. Asking costs a
                # few milliseconds once; guessing costs legibility all session.
                chosen = default_colour(background_is_dark(self.stdin, self.stdout))
            self.hint_colour = chosen
        #: The last line that reached dispatch, for EXPLAIN.
        self.last_invocation: Invocation | None = None
        #: The last failure, for EXPLAIN.
        self.last_error: EmixError | None = None
        #: Whether the command in flight is one EXPLAIN should describe.
        self.recording = True

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

    def split_spec(self, spec: str) -> tuple[str | None, str]:
        """Split a file specification into drive and name.

        Personalities override this to understand their own syntax — CP/M's
        ``d:name.typ``, and its reversible 8.3 aliases.
        """
        return None, spec

    def house_case(self, text: str) -> str:
        """Fold shared Emix output into this personality's own casing.

        Only output the user *asked for* passes through here. Unsolicited
        hints keep their normal case deliberately: they are Emix's voice
        rather than the system's, and looking different is the point.
        """
        return text

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
        self._enable_completion()
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

    def execute(self, line: str) -> bool:
        """Dispatch one line, converting expected failures into house style.

        Returns whether it succeeded, so a one-shot ``-c`` invocation can tell
        a script what happened. An interactive session ignores this and
        carries on, as a command processor should.
        """
        invocation = None
        # A provisional record, in place *before* parsing, because parsing can
        # itself fail: an unmatched quote is a failure EXPLAIN should be able
        # to describe. It is rolled back below when the line turns out to be a
        # meta command, which must not become the subject EXPLAIN talks about.
        previous = (self.last_invocation, self.last_error)
        self.recording = True
        self.last_invocation = Invocation(verb=line.strip().split(" ")[0].upper(), args=[])
        self.last_error = None
        try:
            invocation = self.parse(line)
            if invocation is None:
                self.last_invocation, self.last_error = previous
                return True
            found = self.lookup(invocation.verb)
            self.recording = found is None or not found.meta
            if self.recording:
                self.last_invocation = invocation
            else:
                self.last_invocation, self.last_error = previous
            succeeded = self.dispatch(invocation)
        except EmixError as error:
            # The authentic response first, verbatim and unaltered. Only then
            # may Emix add anything of its own.
            self.write(self.render_error(error))
            # A failing meta command must not overwrite the invocation EXPLAIN
            # is about, or EXPLAIN describes one command and diagnoses another.
            if self.recording:
                self.last_error = error
            if not self.strict:
                self.write_hints(self.hints(error, invocation))
            return False
        except KeyboardInterrupt:
            self.write("^C\n")
            return False
        else:
            self.after_command(line)
            return succeeded

    def dispatch(self, invocation: Invocation) -> bool:
        """Run one invocation. Returns whether it succeeded.

        A host command that exits non-zero and an application that fails are
        both failures, even though neither raises: a script has to be able to
        tell, and printing an error is not telling.
        """
        found = self.lookup(invocation.verb)
        if found is not None:
            if self.is_emix_verb(found.name):
                with self._painted_output():
                    result = found.handler(self, invocation)
            else:
                result = found.handler(self, invocation)
            outcome = result if isinstance(result, Outcome) else Outcome()
            if outcome.stop:
                self.running = False
            return outcome.succeeded
        application = self.lookup_app(invocation.verb)
        if application is not None:
            return self.run_app(application, invocation) == 0
        if not self.host_fallthrough:
            raise EmixError(Code.UNKNOWN_VERB, invocation.verb)
        # A host command that works still teaches nothing about the era, so
        # the lesson goes above it rather than in place of it. The command
        # runs either way: assistance informs, it never obstructs. Only a
        # translation is worth saying here — a did-you-mean would be nonsense
        # about something that is going to succeed.
        if not self.strict:
            translated = translation_hint(self.title, invocation.verb, self.translations)
            if translated:
                self.write_hints([translated])
        return self.run_host(invocation) == 0

    # -- shared Emix commands ------------------------------------------

    @verb("ABOUT", meta=True, summary="Describe Emix", usage="ABOUT")
    def do_about(self, invocation: Invocation) -> None:
        """Describe the project without pretending to be a period command."""
        self._require_no_arguments(invocation)
        self.write(
            self.house_case(
                f"Emix {__version__}\n"
                "Historical computer personalities over a modern Unix host.\n"
                f"Active personality: {self.title} ({self.key})\n"
                "Emix recreates the interaction, not the original hardware or binaries.\n"
                "https://github.com/rdubar/emix\n"
            )
        )

    @verb(
        "CREDIT",
        meta=True,
        summary="Show Emix authorship and licence",
        usage="CREDIT",
        aliases=("CREDITS",),
    )
    def do_credit(self, invocation: Invocation) -> None:
        """Keep project credit available from every personality."""
        self._require_no_arguments(invocation)
        self.write(
            self.house_case(
                "Emix was created by Roger Dubar.\n"
                "Copyright (c) 2026 Roger Dubar.\n"
                "Released under the MIT License.\n"
                "Contributors and source: https://github.com/rdubar/emix\n"
            )
        )

    @verb("APPS", meta=True, summary="List installed historical applications", usage="APPS")
    def do_apps(self, invocation: Invocation) -> None:
        """Emix convenience: no historical system had a concept of this."""
        self._require_no_arguments(invocation)
        installed = self.applications()
        if not installed:
            self.write(
                self.house_case(
                    "No applications configured.\n"
                    "Run 'emix apps' from the host shell for a configuration template.\n"
                )
            )
            return
        for command, profile in sorted(installed.items()):
            name = getattr(profile, "name", "?")
            program = getattr(profile, "program", "?")
            # Verbs win over applications, so a profile named after one would
            # never run. Saying so beats leaving the user to wonder.
            shadowed = "  (SHADOWED BY A COMMAND)" if self.lookup(command) else ""
            self.write(self.house_case(f"{command:<10} {program:<14} {name}{shadowed}\n"))
        self.write(self.house_case("\nType a command with one file name to open it.\n"))

    @staticmethod
    def _require_no_arguments(invocation: Invocation) -> None:
        if invocation.args or invocation.qualifiers:
            raise EmixError(Code.SYNTAX, invocation.verb)

    # -- assistance ------------------------------------------------------

    def hints(self, error: EmixError, invocation: Invocation | None) -> list[str]:
        """Suggestions to print under an authentic error. Never instructions."""
        if error.code is Code.UNKNOWN_VERB and invocation is not None:
            return self._verb_hints(invocation.verb)
        if error.code in {Code.NO_FILE, Code.NOT_A_FILE} and error.subject:
            return self._file_hints(error.subject)
        return []

    def _verb_hints(self, verb: str) -> list[str]:
        translated = translation_hint(self.title, verb, self.translations)
        if translated:
            return [translated]
        known = [found.name for found in self.verbs if not found.hidden]
        known.extend(self.applications())
        suggestion = did_you_mean(verb, known)
        return [suggestion] if suggestion else []

    def _file_hints(self, subject: str) -> list[str]:
        try:
            names = [entry.name for entry in self.drives.match("*")]
        except EmixError:
            return []
        suggestion = did_you_mean(subject, names, noun="file")
        return [suggestion] if suggestion else []

    def paint(self, text: str) -> str:
        """Colour whole lines that are Emix speaking, not the system.

        Line by line, so the colour closes before every newline: a screen
        interrupted mid-write is left in a sane state.
        """
        if self.hint_colour == "none":
            return text
        painted = [
            line if not line.strip() or "\033[" in line else colourise(line, self.hint_colour)
            for line in text.split("\n")
        ]
        return "\n".join(painted)

    def write_hints(self, lines: list[str]) -> None:
        """Print Emix's own lines, every physical one of them marked.

        A single hint can carry an embedded newline — a re-rendered VMS error
        with its ``-%RMS`` continuation, or a CMS message followed by
        ``Ready;``. Marking the list item rather than the line would leave the
        continuation looking like the system speaking.
        """
        for entry in lines:
            for line in entry.split("\n"):
                self.write(self.paint(f"{self.hint_marker}{line}") + "\n")

    def is_emix_verb(self, name: str) -> bool:
        """Whether this command is an Emix addition rather than period kit.

        Its output is painted, because output no real machine could have
        produced should not look like output a real machine produced.
        """
        found = self.lookup(name)
        return bool(found and found.meta)

    @contextlib.contextmanager
    def _painted_output(self) -> Iterator[None]:
        """Capture a verb's output and colour it as Emix's own voice."""
        buffer = io.StringIO()
        original = self.stdout
        self.stdout = buffer
        try:
            yield
        finally:
            self.stdout = original
            captured = buffer.getvalue()
            if captured:
                self.write(self.paint(captured))

    @verb("EXPLAIN", meta=True, summary="Explain the last command or error", usage="EXPLAIN")
    def do_explain(self, invocation: Invocation) -> None:
        """Emix convenience, grounded in what just happened and nothing else.

        This is deliberately offline and deterministic. It reads the last
        invocation and the last error, and says what this personality does and
        why. Nothing is generated, so nothing can be invented.
        """
        self._require_no_arguments(invocation)
        if self.last_invocation is None:
            self.write_hints(["Nothing has run yet in this session."])
            return
        lines = [f"You typed: {self.last_invocation.verb}"]
        if self.last_error is None:
            found = self.lookup(self.last_invocation.verb)
            if found is not None:
                lines.append(f"{found.name} — {found.summary}.")
                if found.usage:
                    lines.append(f"Usage: {found.usage}")
                if found.min_abbrev:
                    shortest = found.name[: found.min_abbrev]
                    lines.append(f"It abbreviates to {shortest} or any longer prefix.")
                note = self.explanations.get(found.name)
                if note:
                    lines.append(note)
            else:
                lines.append("It was handed to the host, not to this personality.")
        else:
            lines.append(self.render_error(self.last_error).strip())
            code = self.last_error.code.name
            found = self.lookup(self.last_invocation.verb)
            name = found.name if found else self.last_invocation.verb.upper()
            if found is not None and found.usage and self.last_error.code is Code.SYNTAX:
                lines.append(f"Usage: {found.usage}")
            # A note keyed VERB.CODE is advice about the command that actually
            # failed. A note keyed CODE alone must be true of every command in
            # the personality — otherwise EXPLAIN ends up telling you DELETE
            # needs a version number when you mistyped STRICT.
            specific = self.explanations.get(f"{name}.{code}")
            notes = {code: specific} if specific else self.explanations
            lines.extend(explain(code, notes))
        self.write_hints(lines)

    @verb("STRICT", meta=True, summary="Show or set authentic-only mode", usage="STRICT [ON|OFF]")
    def do_strict(self, invocation: Invocation) -> None:
        """Emix convenience: no historical system had a concept of this."""
        if not invocation.args:
            state = "ON" if self.strict else "OFF"
            self.write(self.house_case(f"STRICT {state}\n"))
            return
        if len(invocation.args) != 1:
            raise EmixError(Code.SYNTAX, invocation.verb)
        setting = invocation.args[0].upper()
        if setting not in {"ON", "OFF"}:
            raise EmixError(Code.SYNTAX, invocation.verb, "expected ON or OFF")
        self.strict = setting == "ON"
        if self.strict:
            self.write(self.house_case("STRICT ON. Emix will add nothing to authentic output.\n"))
        else:
            self.write(self.house_case("STRICT OFF. Emix may add hints below authentic output.\n"))

    # -- installed applications -----------------------------------------

    def applications(self) -> dict[str, object]:
        """Configured application profiles, keyed by their launch verb."""
        if self._apps is None:
            from emix.apps import profiles

            try:
                # A CP/M profile launched from VMS would be handed a filespec
                # it cannot parse and a backend that does not match, so a
                # profile is only offered where it belongs.
                self._apps = {
                    p.command: p for p in profiles.load().values() if p.system == self.key
                }
            except EmixError:
                # A broken profile file must not stop the shell from starting.
                self._apps = {}
        return self._apps

    def lookup_app(self, verb: str) -> object | None:
        return self.applications().get(verb.upper())

    def run_app(self, profile: object, invocation: Invocation) -> int:
        """Open a file from the current drive in a historical application.

        The filename is resolved through :class:`~emix.host.DriveSet` first,
        so an application reaches exactly the files a typed ``TYPE`` would:
        inside the drive, after symlinks, case folded.
        """
        from emix.apps.runner import open_session

        if len(invocation.args) > 1:
            raise EmixError(Code.SYNTAX, invocation.verb, "expected at most one file name")

        document = None
        new_name = None
        home = self.drives.default
        if invocation.args:
            resolved = self.resolve_document(invocation.args[0])
            document, new_name, home = resolved.host, resolved.new_name, resolved.home

        return open_session(
            profile,  # type: ignore[arg-type]
            document=document,
            new_name=new_name,
            home=home,
            stream=self.stdout,
            confirm=lambda question: "Y" if self.confirm(question) else "N",
        )

    def resolve_document(self, spec: str) -> ResolvedDocument:
        """Turn what the user typed into one host file, or one name to create.

        Application arguments must go through exactly the same door as a typed
        ``TYPE``: the personality's own filespec syntax, its drive prefixes and
        its reversible aliases. Anything else means Emix prints a name in a
        listing that it will not then accept — which it did, before this
        existed.
        """
        drive, name = self.split_spec(spec)
        home = self.drives.drive(drive).root if drive else self.drives.default
        if self.drives.exists(name, drive=drive):
            return ResolvedDocument(host=self.drives.locate(name, drive=drive), home=home)
        # Not an error: an editor is how a file comes into existence. reserve()
        # applies the same name and containment rules a typed command would.
        self.drives.reserve(name, drive=drive)
        return ResolvedDocument(new_name=name, home=home)

    def run_host(self, invocation: Invocation) -> int:
        """Offer the line to the host as an executable, with no shell."""
        return run_host_command([invocation.verb, *invocation.args], cwd=self.drives.default)

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

    # -- completion -------------------------------------------------------

    def completions(self, text: str, line: str) -> list[str]:
        """Candidates for ``text``, offered in this personality's own casing.

        Completion is the one assistance that costs authenticity nothing: it
        changes what you type, never what runs. So it stays on even in strict
        mode, and it deliberately offers period spellings — completing to
        ``DIRECTORY`` is itself a way of learning the vocabulary.
        """
        first_word = not line[: len(line) - len(text)].strip()
        found: list[str] = []
        if first_word:
            found.extend(verb.name for verb in self.verbs if not verb.hidden)
            found.extend(self.applications())
        else:
            with contextlib.suppress(EmixError):
                found.extend(entry.name for entry in self.drives.match("*"))
        cased = [name.upper() if self.fold_input else name for name in found]
        prefix = text.upper() if self.fold_input else text
        return sorted({name for name in cased if name.startswith(prefix)})

    def _completer(self, text: str, state: int) -> str | None:
        try:
            import readline

            matches = self.completions(text, readline.get_line_buffer())
        except Exception:  # pragma: no cover - completion must never crash input
            return None
        return matches[state] if state < len(matches) else None

    def _enable_completion(self) -> None:
        if not self.interactive:
            return
        try:
            import readline
        except ImportError:  # pragma: no cover - readline is absent on some hosts
            return
        readline.set_completer(self._completer)
        readline.set_completer_delims(" \t\n=;")
        # libedit ships on macOS and spells its binding differently.
        binding = "bind ^I rl_complete" if "libedit" in readline.__doc__ else "tab: complete"
        readline.parse_and_bind(binding)

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
