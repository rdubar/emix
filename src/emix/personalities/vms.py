"""VAX/VMS DCL.

DCL differs from CP/M in three ways that shape the engine:

* verbs may be abbreviated to any unambiguous prefix (four characters is the
  documented minimum, so ``DIRE`` works and ``DIR`` is a defined synonym);
* ``/QUALIFIERS`` attach to the verb without a space;
* messages follow ``%FACILITY-S-IDENT, text``.

File versions (``REPORT.TXT;3``) are parsed and displayed as ``;1`` but are
not yet stored: the host keeps one copy. See ROADMAP.md for the plan.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import ClassVar

from emix import __version__
from emix.assist import Concept
from emix.errors import Code, EmixError
from emix.host import case_collisions
from emix.shell import STOP, Invocation, Outcome, Shell, verb

_MESSAGES = {
    Code.NO_FILE: "%RMS-E-FNF, file not found",
    Code.NOT_A_FILE: "%RMS-E-FNF, file not found",
    Code.BAD_NAME: "%RMS-F-SYN, file specification syntax error",
    Code.AMBIGUOUS: "%RMS-F-AMB, ambiguous host file name",
    Code.EXISTS: "%RMS-E-FEX, file already exists, not superseded",
    Code.OUTSIDE_DRIVE: "%RMS-F-SYN, file specification syntax error",
    Code.NO_DRIVE: "%SYSTEM-W-NOSUCHDEV, no such device available",
    Code.IO_ERROR: "%RMS-F-WER, file write error",
    Code.SYNTAX: "%DCL-W-INSFPRM, missing command parameters",
    Code.UNKNOWN_VERB: "%DCL-W-IVVERB, unrecognized command verb - check validity and spelling",
    Code.AMBIGUOUS_VERB: "%DCL-W-ABVERB, ambiguous command verb - supply more characters",
}

#: DEVICE:[DIRECTORY]NAME.TYPE;VERSION, every part optional.
_SPEC = re.compile(
    r"^(?:(?P<device>[A-Za-z][A-Za-z0-9$_]*):)?"
    r"(?:\[(?P<directory>[^\]]*)\])?"
    r"(?P<name>[^;\[\]:]*)"
    r"(?:;(?P<version>[-*\d]*))?$"
)


class VmsShell(Shell):
    """A DCL-flavoured personality over host directories."""

    key = "vms"
    title = "OpenVMS"
    # DCL has no implicit host fallthrough; use RUN or SPAWN.
    host_fallthrough = False
    explanations: ClassVar[dict[str, str]] = {
        "UNKNOWN_VERB": (
            "DCL verbs may be abbreviated to any unambiguous prefix, so DIR, "
            "DIRE and DIRECTORY are one command."
        ),
        "DELETE.SYNTAX": (
            "DELETE requires an explicit version number, as in FILE.TXT;1. "
            "VMS kept every version, so deleting without naming one was too "
            "easy to get wrong."
        ),
        "DELETE": (
            "DELETE needs an explicit version, as in FILE.TXT;1. VMS kept "
            "every version of a file, so a delete without one was too easy to "
            "get wrong."
        ),
    }
    translations: ClassVar[dict[Concept, str]] = {
        Concept.LIST: "DIRECTORY",
        Concept.SHOW: "TYPE",
        # The version number is the whole lesson; suggesting a bare DELETE
        # would just produce the next error.
        Concept.DELETE: "DELETE FILE.TXT;1 (the version number is required)",
        Concept.COPY: "COPY",
        Concept.RENAME: "RENAME",
        Concept.HELP: "HELP",
        Concept.QUIT: "LOGOUT",
        Concept.WHERE: "SHOW DEFAULT",
        Concept.CHDIR: "SET DEFAULT",
    }

    def banner(self) -> str:
        return (
            f"\tEmix {__version__}  VAX/VMS Personality\n\n"
            f"\tLast interactive login on {datetime.now():%d-%b-%Y %H:%M:%S}\n\n"
        )

    def prompt(self) -> str:
        return "$ "

    def render_error(self, error: EmixError) -> str:
        text = _MESSAGES.get(error.code, "%DCL-W-IVVERB, unrecognized command verb")
        if error.subject and error.code in {Code.NO_FILE, Code.NOT_A_FILE, Code.EXISTS}:
            return f"%DCL-W-FILERR, error handling {error.subject.upper()}\n-{text}\n"
        return text + "\n"

    # -- parsing ---------------------------------------------------------

    def parse(self, line: str) -> Invocation | None:
        """Split ``/QUALIFIERS`` off the verb and its parameters."""
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            return None
        qualifiers: dict[str, str] = {}
        words = []
        for token in self.split(stripped):
            head, *quals = _split_qualifiers(token)
            if head:
                words.append(head)
            for qualifier in quals:
                name, _, value = qualifier.partition("=")
                qualifiers[name.upper()] = value
        if not words:
            raise EmixError(Code.SYNTAX, stripped)
        head, *rest = words
        return Invocation(
            verb=head,
            args=rest,
            qualifiers=qualifiers,
            tail=stripped[len(head) :].strip(),
        )

    def split_spec(self, spec: str) -> tuple[str | None, str]:
        """Reduce a VMS file specification to a drive and a leaf name."""
        match = _SPEC.match(spec)
        if match is None or not match.group("name"):
            raise EmixError(Code.BAD_NAME, spec)
        directory = match.group("directory")
        if directory and directory not in {"", ".", "000000"}:
            raise EmixError(Code.BAD_NAME, spec, "directory syntax is not modelled yet")
        return match.group("device"), match.group("name")

    def _one(self, invocation: Invocation, default: str | None = None) -> str:
        if not invocation.args:
            if default is not None:
                return default
            raise EmixError(Code.SYNTAX, invocation.verb)
        if len(invocation.args) != 1:
            raise EmixError(Code.SYNTAX, invocation.verb)
        return invocation.args[0]

    # -- commands ---------------------------------------------------------

    @verb(
        "DIRECTORY",
        summary="List files in a directory",
        usage="DIRECTORY [/SIZE] [/DATE] [filespec]",
        aliases=("DIR",),
        min_abbrev=4,
    )
    def do_directory(self, invocation: Invocation) -> None:
        spec = invocation.args[0] if invocation.args else "*.*"
        device, pattern = self.split_spec(spec)
        entries = self.drives.match(_widen(pattern), drive=device)
        name = (device or self.drives.current).upper()
        self.write(f"\nDirectory {name}:[{self.drives.relative_default() or '000000'}]\n\n")
        if not entries:
            self.write("%DIRECT-W-NOFILES, no files found\n\n")
            return
        blocks = 0
        collisions = case_collisions(entries)
        for entry in entries:
            shown = entry.name if entry.name in collisions else entry.name.upper()
            label = f"{shown};1"
            if entry.is_dir():
                label = f"{shown}.DIR;1"
            line = label
            if invocation.has("SIZE") or invocation.has("DATE"):
                size = 0 if entry.is_dir() else (entry.stat().st_size + 511) // 512
                blocks += size
                line = f"{label:<26}{size:>7}"
                if invocation.has("DATE"):
                    stamp = datetime.fromtimestamp(entry.stat().st_mtime)
                    line += f"  {stamp:%d-%b-%Y %H:%M:%S}"
            self.write(line + "\n")
        self.write(f"\nTotal of {len(entries)} file{'s' if len(entries) != 1 else ''}")
        self.write(f", {blocks} block{'s' if blocks != 1 else ''}.\n\n" if blocks else ".\n\n")

    @verb("TYPE", summary="Display a file", usage="TYPE filespec", min_abbrev=3)
    def do_type(self, invocation: Invocation) -> None:
        device, name = self.split_spec(self._one(invocation))
        content = self.drives.read_text(self.drives.locate(name, drive=device))
        self.write(content)
        if content and not content.endswith("\n"):
            self.write("\n")

    @verb("COPY", summary="Copy a file", usage="COPY input output", min_abbrev=3)
    def do_copy(self, invocation: Invocation) -> None:
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, invocation.verb)
        source_device, source_name = self.split_spec(invocation.args[0])
        dest_device, dest_name = self.split_spec(invocation.args[1])
        source = self.drives.locate(source_name, drive=source_device)
        destination = self.drives.reserve(dest_name, drive=dest_device)
        self.drives.copy(source, destination)
        if invocation.has("LOG"):
            self.write(
                f"%COPY-S-COPIED, {source.name.upper()} copied to {destination.name.upper()};1\n"
            )

    @verb("RENAME", summary="Rename a file", usage="RENAME old new", min_abbrev=3)
    def do_rename(self, invocation: Invocation) -> None:
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, invocation.verb)
        old_device, old_name = self.split_spec(invocation.args[0])
        new_device, new_name = self.split_spec(invocation.args[1])
        source = self.drives.locate(old_name, drive=old_device)
        destination = self.drives.reserve(new_name, drive=new_device or old_device)
        self.drives.rename(source, destination)

    @verb(
        "DELETE",
        summary="Delete a file (an explicit version is required)",
        usage="DELETE filespec;version",
        min_abbrev=3,
    )
    def do_delete(self, invocation: Invocation) -> None:
        spec = self._one(invocation)
        if ";" not in spec:
            # The genuine VMS requirement, and a genuinely useful guard.
            self.write("%DELETE-W-NOVER, explicit version number required\n")
            return
        device, pattern = self.split_spec(spec)
        matches = self.drives.match(_widen(pattern), drive=device, files_only=True)
        if not matches:
            self.write("%DELETE-W-SEARCHFAIL, error searching for file\n")
            return
        if not self.confirm(f"Delete {len(matches)} file(s)? [N]: "):
            self.write("%DELETE-I-NODELETE, no files deleted\n")
            return
        for path in matches:
            self.drives.unlink(path)
            self.write(f"%DELETE-I-FILDEL, {path.name.upper()};1 deleted\n")

    @verb("SET", summary="Set a process characteristic", usage="SET DEFAULT device:", min_abbrev=3)
    def do_set(self, invocation: Invocation) -> None:
        if not invocation.args or invocation.args[0].upper() not in {"DEF", "DEFAULT"}:
            raise EmixError(Code.SYNTAX, invocation.verb)
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, invocation.verb)
        target = invocation.args[1]
        device, remainder = (target[:-1], "") if target.endswith(":") else (None, target)
        if device:
            self.drives.select(device)
        elif remainder in {"[-]", "[-.]"}:
            self.drives.set_default("..")
        else:
            raise EmixError(Code.BAD_NAME, target)

    @verb(
        "SHOW",
        summary="Display process information",
        usage="SHOW DEFAULT|TIME|DEVICES",
        min_abbrev=3,
    )
    def do_show(self, invocation: Invocation) -> None:
        topic = invocation.args[0].upper() if invocation.args else "DEFAULT"
        if topic.startswith("DEF"):
            self.write(f"  {self.drives.current}:[{self.drives.relative_default() or '000000'}]\n")
        elif topic.startswith("TIM"):
            self.write(f"  {datetime.now():%d-%b-%Y %H:%M:%S}\n")
        elif topic.startswith("DEV"):
            self.write("\nDevice                  Directory\n")
            for name in self.drives.names:
                self.write(f"{name + ':':<24}{self.drives.drive(name).root}\n")
            self.write("\n")
        else:
            raise EmixError(Code.SYNTAX, invocation.verb)

    @verb("RUN", summary="Run a host image", usage="RUN image [args]", min_abbrev=3)
    def do_run(self, invocation: Invocation) -> Outcome:
        if not invocation.args:
            raise EmixError(Code.SYNTAX, invocation.verb)
        status = self.run_host(Invocation(verb=invocation.args[0], args=invocation.args[1:]))
        return Outcome(succeeded=status == 0)

    @verb("SPAWN", summary="Run a host command", usage="SPAWN command [args]", min_abbrev=3)
    def do_spawn(self, invocation: Invocation) -> Outcome:
        outcome = self.do_run(invocation)
        return outcome if outcome is not None else Outcome()

    @verb("HELP", summary="Display help", usage="HELP [topic]", min_abbrev=4)
    def do_help(self, invocation: Invocation) -> None:
        if invocation.args:
            found = self.lookup(invocation.args[0])
            if found is None:
                self.write(f"%HELP-E-NOTFOUND, no help for {invocation.args[0].upper()}\n")
                return
            self.write(f"\n{found.name}\n\n  {found.summary}\n\n  Format:\n    {found.usage}\n\n")
            return
        self.write("\n  Emix DCL personality. Verbs may be abbreviated.\n\n")
        for found in self.verbs:
            if not found.hidden:
                self.write(f"    {found.name:<12}{found.summary}\n")
        self.write("\n  Topic? Use HELP <verb> for one command.\n\n")

    @verb("LOGOUT", summary="End the session", usage="LOGOUT", aliases=("LO", "EXIT"), min_abbrev=3)
    def do_logout(self, invocation: Invocation) -> Outcome:
        self.write(self.farewell())
        return STOP

    def farewell(self) -> str:
        return f"  EMIX       job terminated at {datetime.now():%d-%b-%Y %H:%M:%S}\n"


def _split_qualifiers(token: str) -> list[str]:
    """``DIRECTORY/SIZE/DATE`` becomes ``["DIRECTORY", "SIZE", "DATE"]``."""
    return token.split("/")


def _widen(pattern: str) -> str:
    return "*" if pattern in {"*.*", "", "*"} else pattern
