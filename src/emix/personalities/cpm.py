"""CP/M 2.2.

Digital Research's CP/M 2.2 had exactly six built-in commands in the CCP:
``DIR``, ``ERA``, ``REN``, ``SAVE``, ``TYPE`` and ``USER``. Everything else,
including ``STAT`` and ``PIP``, was a transient ``.COM`` program loaded from
disk. Emix keeps that distinction visible: :meth:`do_help` lists the built-ins
separately from the transients it simulates, and from the Emix conveniences
that no real CP/M ever had.
"""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import ClassVar

from emix import __version__
from emix.apps.names import AliasMap
from emix.assist import Concept
from emix.errors import Code, EmixError
from emix.host import case_collisions, terminal_width
from emix.shell import FAILED, STOP, Invocation, Outcome, Shell, verb

#: How each engine error code is worded by the CCP.
_MESSAGES = {
    Code.NO_FILE: "NO FILE",
    Code.NOT_A_FILE: "NO FILE",
    Code.BAD_NAME: "BAD FILE NAME",
    Code.AMBIGUOUS: "AMBIGUOUS HOST NAME",
    Code.EXISTS: "FILE EXISTS",
    Code.OUTSIDE_DRIVE: "BAD FILE NAME",
    Code.NO_DRIVE: "BDOS ERR ON {subject}: SELECT",
    Code.IO_ERROR: "BDOS ERR ON {drive}: R/O",
    Code.SYNTAX: "BAD COMMAND FORMAT",
    Code.AMBIGUOUS_VERB: "{subject}?",
    Code.UNKNOWN_VERB: "{subject}?",
    Code.NEEDS_SHELL: "{subject}?",
}


#: ``B:`` on a line of its own. CP/M 2.2 had drives A: to P:, and selecting
#: one was a CCP command in its own right rather than an entry in the table.
_BARE_DRIVE = re.compile(r"([A-P]):", re.IGNORECASE)


class CpmShell(Shell):
    """The CP/M 2.2 console command processor, backed by host directories."""

    key = "cpm"
    title = "CP/M 2.2"
    fold_input = True
    explanations: ClassVar[dict[str, str]] = {
        "REN.SYNTAX": (
            "CP/M names its destination first: REN NEW=OLD. It reads as an "
            "assignment, not as a Unix argument order."
        ),
        "PIP.SYNTAX": ("PIP names its destination first: PIP NEW=OLD, like an assignment."),
        "UNKNOWN_VERB": (
            "The CCP had six built-ins: DIR, ERA, REN, SAVE, TYPE and USER. "
            "Everything else, PIP and STAT included, was a .COM file loaded "
            "from disk."
        ),
    }
    translations: ClassVar[dict[Concept, str]] = {
        Concept.LIST: "DIR",
        Concept.SHOW: "TYPE",
        Concept.DELETE: "ERA",
        # PIP takes its destination first, which is the surprise worth naming.
        Concept.COPY: "PIP NEW=OLD",
        Concept.RENAME: "REN NEW=OLD",
        Concept.HELP: "HELP",
        Concept.QUIT: "EXIT",
        Concept.CLEAR: "CLS",
        Concept.WHERE: "DRIVES",
    }
    absences: ClassVar[dict[Concept, str]] = {
        # Saying so teaches more than a substitute would.
        Concept.CHDIR: "CP/M 2.2 had no directories at all, only drives A: to P:",
    }

    def banner(self) -> str:
        return (
            f"EMIX {__version__}\n"
            "CP/M 2.2 PERSONALITY\n"
            f"{self.drives.current}: {self.drives.drive().root}\n"
            "TYPE HELP FOR AVAILABLE COMMANDS.\n"
        )

    def prompt(self) -> str:
        return f"{self.drives.current}>"

    def render_error(self, error: EmixError) -> str:
        template = _MESSAGES.get(error.code, "BAD COMMAND FORMAT")
        text = template.format(subject=error.subject.upper(), drive=self.drives.current)
        if error.code is Code.AMBIGUOUS and error.detail:
            text = f"{text}: {error.detail}"
        return text + "\n"

    #: What CP/M 2.2 actually shipped. Everything else in the vocabulary is
    #: an Emix addition, and :meth:`do_help` says so in as many words.
    PERIOD: ClassVar[frozenset[str]] = frozenset(
        {"DIR", "ERA", "ERASE", "REN", "RENAME", "SAVE", "TYPE", "USER", "PIP", "STAT"}
    )

    def is_emix_verb(self, name: str) -> bool:
        return name.upper() not in self.PERIOD

    def house_case(self, text: str) -> str:
        """CP/M shouted. Web addresses do not, because a folded path can be
        wrong, and a listing that cannot be used is worse than an inconsistent
        one — the same rule that keeps long file names unfolded."""
        # Split on runs of whitespace *keeping them*, so a word ending a line
        # is not glued to the URL that starts the next one.
        return "".join(part if "://" in part else part.upper() for part in re.split(r"(\s+)", text))

    # -- file specifications --------------------------------------------

    def dispatch(self, invocation: Invocation) -> bool:
        """Intercept a bare drive letter, which the CCP treated as a command.

        Typing ``B:`` at ``A>`` selected drive B and changed the prompt. It is
        not a verb — there are sixteen of them and none is in the command table
        — so it is recognised here rather than looked up.

        An unmounted drive raises ``NO_DRIVE``, which this personality already
        words as ``BDOS ERR ON B: SELECT``: exactly what the CCP printed, and
        the reason the drive layer's error codes are symbolic.
        """
        letter = _BARE_DRIVE.fullmatch(invocation.verb)
        if letter and not invocation.args:
            self.drives.select(letter.group(1))
            return True
        return super().dispatch(invocation)

    def split_spec(self, spec: str) -> tuple[str | None, str]:
        """Split a CP/M ``d:name.typ`` specification into drive and name.

        This is also where an 8.3 alias becomes a host name again. Every CP/M
        command parses its filespec here, so the translation is written once
        and no verb can forget it.
        """
        drive, name = (spec[0].upper(), spec[2:]) if _has_drive(spec) else (None, spec)
        return drive, self.unalias(name, drive)

    def aliases(self, drive: str | None = None) -> AliasMap:
        """8.3 names for everything currently visible on a drive."""
        try:
            entries = self.drives.match("*", drive=drive)
        except EmixError:
            return AliasMap(())
        collisions = case_collisions(entries)
        return AliasMap(entry.name for entry in entries if entry.name not in collisions)

    def unalias(self, name: str, drive: str | None = None) -> str:
        """Turn ``PYPROJ_1.TOM`` back into ``pyproject.toml``.

        A real host name always wins, so this can only ever add a way to
        reach a file, never take one away.
        """
        if not name or "*" in name or "?" in name:
            return name
        if self.drives.exists(name, drive=drive):
            return name
        return self.aliases(drive).host(name) or name

    def _one(self, invocation: Invocation, default: str | None = None) -> str:
        if not invocation.args:
            if default is not None:
                return default
            raise EmixError(Code.SYNTAX, invocation.verb)
        if len(invocation.args) != 1:
            raise EmixError(Code.SYNTAX, invocation.verb)
        return invocation.args[0]

    # -- CCP built-ins ---------------------------------------------------

    @verb("DIR", summary="LIST FILES", usage="DIR [D:][PATTERN]")
    def do_dir(self, invocation: Invocation) -> None:
        drive, pattern = self.split_spec(self._one(invocation, default="*.*"))
        entries = self.drives.match(_widen(pattern), drive=drive)
        letter = (drive or self.drives.current).upper()
        if not entries:
            self.write("NO FILE\n")
            return
        # CP/M 2.2 printed four columns of "d: NAME     TYP" and no sizes.
        columns = max(1, min(4, terminal_width() // 18))
        collisions = case_collisions(entries)
        aliases = self.aliases(drive)
        cells = []
        for entry in entries:
            shown = _eight_three(aliases.alias(entry.name), verbatim=entry.name in collisions)
            cells.append(f"{letter}: {shown}")
        self.write("\n")
        for index in range(0, len(cells), columns):
            self.write(" ".join(cells[index : index + columns]).rstrip() + "\n")
        self.write("\n")

    @verb("TYPE", summary="DISPLAY A TEXT FILE", usage="TYPE [D:]FILE")
    def do_type(self, invocation: Invocation) -> None:
        drive, name = self.split_spec(self._one(invocation))
        path = self.drives.locate(name, drive=drive)
        content = self.drives.read_text(path)
        self.write(content)
        if content and not content.endswith("\n"):
            self.write("\n")

    @verb("ERA", summary="ERASE FILES", usage="ERA [D:]PATTERN", aliases=("ERASE",))
    def do_era(self, invocation: Invocation) -> None:
        drive, pattern = self.split_spec(self._one(invocation))
        matches = self.drives.match(_widen(pattern), drive=drive, files_only=True)
        if not matches:
            self.write("NO FILE\n")
            return
        # Real CP/M only confirmed for ERA *.*; Emix confirms for every
        # erase, because these are the user's actual host files.
        label = pattern.upper() if len(matches) > 1 else _eight_three(matches[0].name)
        if not self.confirm(f"ERASE {label} (Y/N)? "):
            self.write("NOT ERASED\n")
            return
        erased = 0
        for path in matches:
            try:
                self.drives.unlink(path)
                erased += 1
            except EmixError as error:
                self.write(self.render_error(error))
        self.write(f"{erased} FILE(S) ERASED\n")

    @verb("REN", summary="RENAME A FILE", usage="REN NEW=OLD", aliases=("RENAME",))
    def do_ren(self, invocation: Invocation) -> None:
        if "=" not in invocation.tail:
            raise EmixError(Code.SYNTAX, invocation.verb)
        new_spec, old_spec = (part.strip() for part in invocation.tail.split("=", 1))
        if not new_spec or not old_spec:
            raise EmixError(Code.SYNTAX, invocation.verb)
        old_drive, old_name = self.split_spec(old_spec)
        new_drive, new_name = self.split_spec(new_spec)
        source = self.drives.locate(old_name, drive=old_drive)
        destination = self.drives.reserve(new_name, drive=new_drive or old_drive)
        self.drives.rename(source, destination)

    @verb("SAVE", summary="SAVE MEMORY TO A FILE", usage="SAVE N FILE")
    def do_save(self, invocation: Invocation) -> Outcome:
        """The one CCP built-in Emix cannot honestly provide.

        ``SAVE`` wrote N pages of the Transient Program Area to disk. Emix has
        no TPA — it runs no 8080 — so there is nothing to save.

        The answer has to obey the same rule as everything else: CP/M's own
        response first, and the explanation as *marked* assistance. Emix prose
        on the native path would be exactly the confusion between period and
        non-period output that the rest of the project works to prevent — and
        in strict mode it would be unmarked invention.
        """
        self.write("SAVE?\n")
        if self.strict:
            # Strict mode is the authentic baseline. `SAVE?` is what a CCP
            # with no such program would have said, and that is all of it.
            return FAILED
        self.write_hints(
            [
                "SAVE copied pages of the Transient Program Area to disk.",
                "Emix runs no 8080, so there is no TPA to copy from and no",
                "honest way to provide this. It is listed because CP/M had it.",
            ]
        )
        # The operation was refused, so a script must not be told it worked.
        return FAILED

    @verb("USER", summary="SELECT A USER AREA", usage="USER N")
    def do_user(self, invocation: Invocation) -> None:
        # User areas are not modelled yet; area 0 is the only valid one.
        number = self._one(invocation, default="0")
        if not number.isdigit() or not 0 <= int(number) <= 15:
            raise EmixError(Code.SYNTAX, invocation.verb)
        if int(number) != 0:
            self.write("ONLY USER 0 IS MAPPED IN THIS RELEASE.\n")

    # -- simulated transients --------------------------------------------

    @verb("PIP", summary="COPY A FILE (TRANSIENT)", usage="PIP NEW=OLD")
    def do_pip(self, invocation: Invocation) -> None:
        """PIP, the Peripheral Interchange Program, is how CP/M copied."""
        if "=" not in invocation.tail:
            raise EmixError(Code.SYNTAX, invocation.verb)
        destination_spec, source_spec = (part.strip() for part in invocation.tail.split("=", 1))
        source_drive, source_name = self.split_spec(source_spec)
        dest_drive, dest_name = self.split_spec(destination_spec)
        source = self.drives.locate(source_name, drive=source_drive)
        destination = self.drives.reserve(dest_name, drive=dest_drive)
        self.drives.copy(source, destination)

    @verb("COPY", summary="COPY A FILE (EMIX)", usage="COPY SOURCE DEST")
    def do_copy(self, invocation: Invocation) -> None:
        """Not a CP/M command; kept because PIP's argument order surprises."""
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, invocation.verb)
        source_drive, source_name = self.split_spec(invocation.args[0])
        dest_drive, dest_name = self.split_spec(invocation.args[1])
        source = self.drives.locate(source_name, drive=source_drive)
        destination = self.drives.reserve(dest_name, drive=dest_drive)
        self.drives.copy(source, destination)

    @verb("STAT", summary="SHOW FREE SPACE (TRANSIENT)", usage="STAT [D:]")
    def do_stat(self, invocation: Invocation) -> None:
        drive = None
        if invocation.args:
            drive, remainder = self.split_spec(self._one(invocation))
            if remainder:
                raise EmixError(Code.SYNTAX, invocation.verb)
        letter = (drive or self.drives.current).upper()
        usage = self.drives.free_space(drive=drive)
        kilobytes = usage.free // 1024
        self.write(f"{letter}: R/W, SPACE: {kilobytes:,}K\n")

    # -- Emix conveniences ------------------------------------------------

    @verb("DRIVES", summary="LIST MOUNTED DRIVES", usage="DRIVES")
    def do_drives(self, invocation: Invocation) -> None:
        for name in self.drives.names:
            drive = self.drives.drive(name)
            marker = "*" if name == self.drives.current else " "
            self.write(f"{marker}{name}: {drive.root}\n")

    @verb("UNIX", summary="RUN A HOST COMMAND", usage="UNIX COMMAND [ARGS]")
    def do_unix(self, invocation: Invocation) -> Outcome:
        if not invocation.args:
            raise EmixError(Code.SYNTAX, invocation.verb)
        status = self.run_host(Invocation(verb=invocation.args[0], args=invocation.args[1:]))
        return Outcome(succeeded=status == 0)

    @verb("CLS", summary="CLEAR THE SCREEN", usage="CLS")
    def do_cls(self, invocation: Invocation) -> None:
        if invocation.args:
            raise EmixError(Code.SYNTAX, invocation.verb)
        self.write("\033[2J\033[H")

    @verb("VER", summary="SHOW THE EMIX VERSION", usage="VER")
    def do_ver(self, invocation: Invocation) -> None:
        self.write(f"EMIX {__version__}, CP/M 2.2 PERSONALITY\n")

    @verb("HELP", summary="SHOW HELP", usage="HELP [COMMAND]")
    def do_help(self, invocation: Invocation) -> None:
        if invocation.args:
            found = self.lookup(invocation.args[0])
            if found is None:
                self.write("NO HELP AVAILABLE\n")
                return
            self.write(f"{found.usage.upper()}\n  {found.summary.upper()}\n")
            return
        builtins = {"DIR", "ERA", "REN", "TYPE", "USER"}
        transients = {"PIP", "STAT"}
        self.write("CCP BUILT-IN COMMANDS:\n")
        self._list(name for name in builtins)
        self.write("\nSIMULATED TRANSIENT PROGRAMS:\n")
        self._list(name for name in transients)
        self.write("\nEMIX EXTENSIONS (NOT PART OF CP/M):\n")
        self._list(
            found.name
            for found in self.verbs
            if found.name not in builtins | transients and not found.hidden
        )
        self.write(
            "\nUNKNOWN COMMANDS ARE OFFERED TO THE HOST AS EXECUTABLES.\n"
            "NO SHELL IS INVOKED, SO |, >, && AND $VAR ARE NOT INTERPRETED.\n"
        )

    def _list(self, names: Iterable[str]) -> None:
        table = {found.name: found for found in self.verbs}
        for name in sorted(names):
            found = table.get(name)
            if found is not None:
                self.write(f"  {found.usage.upper():<24} {found.summary.upper()}\n")

    @verb("EXIT", summary="RETURN TO UNIX", usage="EXIT", aliases=("BYE", "QUIT"))
    def do_exit(self, invocation: Invocation) -> Outcome:
        self.write(self.farewell())
        return STOP

    def farewell(self) -> str:
        return "RETURNING TO UNIX.\n"


def _widen(pattern: str) -> str:
    """CP/M's ``*.*`` means every file; ``fnmatch`` would demand a dot."""
    return "*" if pattern in {"*.*", ""} else pattern


def _has_drive(spec: str) -> bool:
    return len(spec) >= 2 and spec[1] == ":" and spec[0].isalpha()


def _eight_three(name: str, *, verbatim: bool = False) -> str:
    """Present an already-aliased name in CP/M's ``NAME     TYP`` columns.

    Callers pass a name that :class:`AliasMap` has already made fit, so the
    printed name can always be typed back. The verbatim escape remains for
    case-colliding host names, which no alias can disambiguate.
    """
    if verbatim:
        # Two host names folding to one CP/M name; upper-casing would print
        # the same row twice and name neither file usefully.
        return name
    stem, _, extension = name.upper().rpartition(".")
    if not stem:
        stem, extension = name.upper(), ""
    if len(stem) > 8 or len(extension) > 3:
        return name.upper()
    return f"{stem:<8} {extension:<3}"
