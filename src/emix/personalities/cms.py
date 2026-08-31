"""IBM VM/CMS.

CMS is the mainframe personality because it is genuinely interactive, unlike
MVS/TSO batch work. Its file model is the interesting part and the reason it
exists in Emix: a file is identified by three blank-separated tokens rather
than one dotted string.

    PROFILE EXEC A
    filename filetype filemode

Emix maps ``filename filetype`` onto the host name ``FILENAME.FILETYPE`` and
``filemode`` onto a drive, so ``PROFILE EXEC A`` is ``PROFILE.EXEC`` on drive
A. Building this personality is what proves the engine's drive layer is
genuinely shared rather than CP/M's private arrangement wearing a hat.
"""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any, ClassVar

from emix import __version__
from emix.assist import Concept
from emix.errors import Code, EmixError
from emix.host import case_collisions
from emix.shell import Invocation, Shell, verb

_MESSAGES = {
    Code.NO_FILE: "DMSxxx002E File '{subject}' not found",
    Code.NOT_A_FILE: "DMSxxx002E File '{subject}' not found",
    Code.BAD_NAME: "DMSxxx054E Incomplete or invalid fileid '{subject}'",
    Code.AMBIGUOUS: "DMSxxx024E Host file name is ambiguous: {detail}",
    Code.EXISTS: "DMSxxx024E File '{subject}' already exists",
    Code.OUTSIDE_DRIVE: "DMSxxx054E Incomplete or invalid fileid '{subject}'",
    Code.NO_DRIVE: "DMSxxx069E Disk '{subject}' not accessed",
    Code.IO_ERROR: "DMSxxx105S Error writing file '{subject}'",
    Code.SYNTAX: "DMSxxx005E No option specified",
    Code.UNKNOWN_VERB: "DMSxxx002E Unknown CP/CMS command",
    Code.AMBIGUOUS_VERB: "DMSxxx002E Unknown CP/CMS command",
}


class CmsShell(Shell):
    """A VM/CMS personality over host directories."""

    key = "cms"
    title = "VM/CMS"
    host_fallthrough = False
    explanations: ClassVar[dict[str, str]] = {
        "SYNTAX": (
            "A CMS file is three words: FILENAME FILETYPE FILEMODE. The "
            "filemode is the disk letter and is often left to default to A."
        ),
    }
    translations: ClassVar[dict[Concept, str]] = {
        Concept.LIST: "LISTFILE",
        Concept.SHOW: "TYPE",
        Concept.DELETE: "ERASE",
        Concept.COPY: "COPYFILE",
        Concept.RENAME: "RENAME",
        Concept.HELP: "HELP",
        Concept.QUIT: "LOGOFF",
        Concept.WHERE: "QUERY DISK",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._started = time.process_time()

    def banner(self) -> str:
        return (
            f"EMIX {__version__} - VM/CMS PERSONALITY\n"
            f"CMS  LOGON AT {datetime.now():%H:%M:%S} ON {datetime.now():%m/%d/%y}\n"
            "Ready;\n"
        )

    def prompt(self) -> str:
        return ""

    def after_command(self, line: str) -> None:
        """CMS answers 'Ready;' with processor times after each command.

        Errors carry their own Ready(nnnnn) line from :meth:`render_error`,
        and the base class skips this hook when a command raised, so the two
        never double up. LOGOFF ends the session without one.
        """
        if line.strip() and self.running:
            self.write(self._ready())

    def _ready(self, code: int = 0) -> str:
        elapsed = time.process_time() - self._started
        stamp = f"T={elapsed:.2f}/{elapsed:.2f} {datetime.now():%H:%M:%S}"
        if code:
            return f"Ready({code:05d}); {stamp}\n"
        return f"Ready; {stamp}\n"

    def render_error(self, error: EmixError) -> str:
        template = _MESSAGES.get(error.code, "DMSxxx002E Unknown CP/CMS command")
        text = template.format(subject=error.subject.upper(), detail=error.detail)
        return f"{text}\n{self._ready(28)}"

    # -- the three-token fileid -------------------------------------------

    def fileid(self, args: list[str], *, wildcards: bool = False) -> tuple[str | None, str]:
        """Turn ``FN FT FM`` into a drive and a host leaf name."""
        if not args:
            raise EmixError(Code.BAD_NAME, "")
        name = args[0]
        filetype = args[1] if len(args) > 1 else ("*" if wildcards else "")
        filemode = args[2] if len(args) > 2 else None
        if len(args) > 3:
            raise EmixError(Code.BAD_NAME, " ".join(args))
        if filemode is not None:
            # A filemode is a letter and an optional number, e.g. "A1".
            if not filemode[0].isalpha():
                raise EmixError(Code.BAD_NAME, filemode)
            filemode = filemode[0]
        leaf = f"{name}.{filetype}" if filetype else name
        return filemode, leaf

    @staticmethod
    def display(leaf: str, drive: str) -> str:
        stem, _, filetype = leaf.rpartition(".")
        if not stem:
            stem, filetype = leaf, ""
        return f"{stem.upper():<8} {filetype.upper():<8} {drive.upper()}1"

    # -- commands ----------------------------------------------------------

    @verb(
        "LISTFILE",
        summary="List files on a minidisk",
        usage="LISTFILE [fn [ft [fm]]]",
        aliases=("LISTF",),
    )
    def do_listfile(self, invocation: Invocation) -> None:
        drive, pattern = self.fileid(invocation.args or ["*"], wildcards=True)
        entries = self.drives.match(pattern, drive=drive, files_only=True)
        letter = (drive or self.drives.current).upper()
        if not entries:
            raise EmixError(Code.NO_FILE, pattern)
        collisions = case_collisions(entries)
        for entry in entries:
            if entry.name in collisions:
                self.write(f"{entry.name}  {letter.upper()}1\n")
            else:
                self.write(self.display(entry.name, letter) + "\n")

    @verb("TYPE", summary="Display a file", usage="TYPE fn ft [fm]")
    def do_type(self, invocation: Invocation) -> None:
        drive, leaf = self.fileid(invocation.args)
        content = self.drives.read_text(self.drives.locate(leaf, drive=drive))
        self.write(content)
        if content and not content.endswith("\n"):
            self.write("\n")

    @verb("COPYFILE", summary="Copy a file", usage="COPYFILE fn ft fm fn ft fm", aliases=("COPY",))
    def do_copyfile(self, invocation: Invocation) -> None:
        source_args, dest_args = _halve(invocation.args)
        source_drive, source_leaf = self.fileid(source_args)
        dest_drive, dest_leaf = self.fileid(dest_args)
        source = self.drives.locate(source_leaf, drive=source_drive)
        destination = self.drives.reserve(dest_leaf, drive=dest_drive)
        self.drives.copy(source, destination)

    @verb("RENAME", summary="Rename a file", usage="RENAME fn ft fm fn ft fm")
    def do_rename(self, invocation: Invocation) -> None:
        old_args, new_args = _halve(invocation.args)
        old_drive, old_leaf = self.fileid(old_args)
        new_drive, new_leaf = self.fileid(new_args)
        source = self.drives.locate(old_leaf, drive=old_drive)
        destination = self.drives.reserve(new_leaf, drive=new_drive or old_drive)
        self.drives.rename(source, destination)

    @verb("ERASE", summary="Erase files", usage="ERASE fn ft [fm]")
    def do_erase(self, invocation: Invocation) -> None:
        drive, pattern = self.fileid(invocation.args, wildcards=True)
        matches = self.drives.match(pattern, drive=drive, files_only=True)
        letter = (drive or self.drives.current).upper()
        if not matches:
            raise EmixError(Code.NO_FILE, pattern)
        listing = ", ".join(self.display(entry.name, letter).strip() for entry in matches)
        if not self.confirm(f"ERASE {listing}? (Y/N) "):
            self.write("DMSxxx000I No files erased\n")
            return
        for path in matches:
            self.drives.unlink(path)

    @verb(
        "QUERY", summary="Query the virtual machine", usage="QUERY DISK|TIME|SEARCH", aliases=("Q",)
    )
    def do_query(self, invocation: Invocation) -> None:
        topic = invocation.args[0].upper() if invocation.args else "DISK"
        if topic.startswith("DISK"):
            self.write("LABEL  VDEV M  STAT   CYL TYPE BLKSZ   FILES  BLKS USED-(%)\n")
            for name in self.drives.names:
                usage = self.drives.free_space(drive=name)
                percent = 100 - int(usage.free * 100 / usage.total)
                count = sum(1 for _ in self.drives.drive(name).root.iterdir())
                self.write(
                    f"EMIX{name} 019{name} {name}  R/W    500 3390  4096 "
                    f"{count:>7} {usage.used // 4096:>5}-{percent:>3}\n"
                )
        elif topic.startswith("TIME"):
            self.write(f"TIME IS {datetime.now():%H:%M:%S} {datetime.now():%m/%d/%y}\n")
        elif topic.startswith("SEARCH"):
            for name in self.drives.names:
                self.write(f"EMIX{name} 019{name} {name}   R/W    {self.drives.drive(name).root}\n")
        else:
            raise EmixError(Code.SYNTAX, invocation.verb)

    @verb("CMS", summary="Run a host command", usage="CMS command [args]")
    def do_cms(self, invocation: Invocation) -> None:
        if not invocation.args:
            raise EmixError(Code.SYNTAX, invocation.verb)
        self.run_host(Invocation(verb=invocation.args[0], args=invocation.args[1:]))

    @verb("HELP", summary="Display help", usage="HELP [command]")
    def do_help(self, invocation: Invocation) -> None:
        if invocation.args:
            found = self.lookup(invocation.args[0])
            if found is None:
                self.write("DMSxxx003E HELP file not found\n")
                return
            self.write(f"\n{found.name}\n\n  {found.summary}\n\n  Format: {found.usage}\n\n")
            return
        self.write("\nCMS COMMANDS\n\n")
        for found in self.verbs:
            if not found.hidden:
                self.write(f"  {found.name:<10}{found.summary}\n")
        self.write("\nA fileid is three tokens: FILENAME FILETYPE FILEMODE.\n\n")

    @verb("LOGOFF", summary="End the session", usage="LOGOFF", aliases=("LOGOUT", "EXIT", "QUIT"))
    def do_logoff(self, invocation: Invocation) -> bool:
        self.write(self.farewell())
        return True

    def farewell(self) -> str:
        return (
            "CONNECT= 00:00:00 VIRTCPU= 000:00.01 TOTCPU= 000:00.01\n"
            f"LOGOFF AT {datetime.now():%H:%M:%S}\n"
        )


def _halve(args: list[str]) -> tuple[list[str], list[str]]:
    """Split ``fn ft fm fn ft fm`` down the middle."""
    if len(args) < 2 or len(args) % 2:
        raise EmixError(Code.BAD_NAME, " ".join(args))
    middle = len(args) // 2
    return args[:middle], args[middle:]
