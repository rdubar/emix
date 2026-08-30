"""A small CP/M-flavoured shell backed by a host directory."""

from __future__ import annotations

import cmd
import fnmatch
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import TextIO

from emix import __version__


class CpmShell(cmd.Cmd):
    """CP/M command personality using one host directory as drive A:."""

    prompt = "A>"
    ruler = "-"

    def __init__(
        self,
        root: Path,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
    ) -> None:
        super().__init__(stdin=stdin or sys.stdin, stdout=stdout or sys.stdout)
        self.use_rawinput = stdin is None
        self.root = root.expanduser().resolve()
        self.intro = (
            f"EMIX {__version__}\n"
            "CP/M 2.2 PERSONALITY\n"
            f"A: {self.root}\n"
            "TYPE HELP FOR AVAILABLE COMMANDS."
        )

    def parseline(self, line: str) -> tuple[str | None, str | None, str]:
        command, arg, parsed = super().parseline(line)
        if command:
            command = command.upper()
        return command, arg, parsed

    def emptyline(self) -> None:
        return None

    def do_DIR(self, arg: str) -> None:
        """DIR [pattern] -- list files on drive A:."""
        pattern = self._single_argument(arg, default="*")
        if pattern is None:
            return
        pattern = self._strip_drive(pattern)
        if not self._valid_leaf(pattern, wildcards=True):
            return

        entries = sorted(
            (
                path
                for path in self.root.iterdir()
                if fnmatch.fnmatchcase(path.name.upper(), pattern.upper())
            ),
            key=lambda path: path.name.upper(),
        )
        self._write("\nA: DRIVE A DIRECTORY\n\n")
        if not entries:
            self._write("NO FILE\n")
            return

        for path in entries:
            name = path.name.upper()
            detail = "<DIR>" if path.is_dir() else f"{path.stat().st_size:>8}"
            self._write(f"A: {name:<28} {detail}\n")
        self._write(f"\n{len(entries)} FILE(S)\n")

    def do_TYPE(self, arg: str) -> None:
        """TYPE file -- display a text file."""
        name = self._single_argument(arg)
        if name is None:
            return
        path = self._find_file(name)
        if path is None:
            return
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            self._write(f"READ ERROR: {error}\n")
            return
        self._write(content)
        if content and not content.endswith("\n"):
            self._write("\n")

    def do_ERA(self, arg: str) -> None:
        """ERA pattern -- erase matching files after confirmation."""
        pattern = self._single_argument(arg)
        if pattern is None:
            return
        pattern = self._strip_drive(pattern)
        if not self._valid_leaf(pattern, wildcards=True):
            return
        matches = sorted(
            (
                path
                for path in self.root.iterdir()
                if path.is_file()
                and fnmatch.fnmatchcase(path.name.upper(), pattern.upper())
            ),
            key=lambda path: path.name.upper(),
        )
        if not matches:
            self._write("NO FILE\n")
            return

        label = pattern.upper() if len(matches) > 1 else matches[0].name.upper()
        if not self._confirm(f"ERASE {label} (Y/N)? "):
            self._write("NOT ERASED\n")
            return
        for path in matches:
            try:
                path.unlink()
            except OSError as error:
                self._write(f"ERASE ERROR {path.name.upper()}: {error}\n")
        self._write(f"{len(matches)} FILE(S) ERASED\n")

    do_ERASE = do_ERA

    def do_REN(self, arg: str) -> None:
        """REN new=old -- rename a file using CP/M argument order."""
        if "=" not in arg:
            self._write("USAGE: REN NEWNAME=OLDNAME\n")
            return
        new_name, old_name = (part.strip() for part in arg.split("=", 1))
        if not new_name or not old_name:
            self._write("USAGE: REN NEWNAME=OLDNAME\n")
            return
        source = self._find_file(old_name)
        if source is None:
            return
        destination = self._new_path(new_name)
        if destination is None:
            return
        if destination.exists() or self._casefold_match(destination.name) is not None:
            self._write("FILE EXISTS\n")
            return
        try:
            source.rename(destination)
        except OSError as error:
            self._write(f"RENAME ERROR: {error}\n")

    do_RENAME = do_REN

    def do_COPY(self, arg: str) -> None:
        """COPY source destination -- copy a host file on drive A:."""
        parts = self._arguments(arg)
        if parts is None:
            return
        if len(parts) != 2:
            self._write("USAGE: COPY SOURCE DESTINATION\n")
            return
        source = self._find_file(parts[0])
        if source is None:
            return
        destination = self._new_path(parts[1])
        if destination is None:
            return
        if destination.exists() or self._casefold_match(destination.name) is not None:
            self._write("FILE EXISTS\n")
            return
        try:
            shutil.copy2(source, destination)
        except OSError as error:
            self._write(f"COPY ERROR: {error}\n")

    def do_STAT(self, arg: str) -> None:
        """STAT -- show the host space available to drive A:."""
        if arg.strip():
            self._write("USAGE: STAT\n")
            return
        usage = shutil.disk_usage(self.root)
        self._write(
            f"A: {usage.free:,} BYTES FREE OF {usage.total:,} HOST BYTES\n"
        )

    def do_CLS(self, arg: str) -> None:
        """CLS -- clear the terminal."""
        if arg.strip():
            self._write("USAGE: CLS\n")
            return
        self._write("\033[2J\033[H")

    def do_UNIX(self, arg: str) -> None:
        """UNIX command [args] -- explicitly run a host command."""
        if not arg.strip():
            self._write("USAGE: UNIX COMMAND [ARGUMENTS]\n")
            return
        self._run_host_command(arg)

    def do_VER(self, arg: str) -> None:
        """VER -- display the Emix version."""
        if arg.strip():
            self._write("USAGE: VER\n")
            return
        self._write(f"EMIX {__version__}, CP/M 2.2 PERSONALITY\n")

    def do_HELP(self, arg: str) -> None:
        """HELP -- display available commands."""
        topic = arg.strip().upper()
        if topic:
            handler = getattr(self, f"do_{topic}", None)
            if handler is None or not handler.__doc__:
                self._write("NO HELP AVAILABLE\n")
                return
            self._write(handler.__doc__.strip() + "\n")
            return
        self._write(
            "AVAILABLE COMMANDS:\n"
            "  DIR [PATTERN]          LIST FILES\n"
            "  TYPE FILE              DISPLAY A TEXT FILE\n"
            "  COPY SOURCE DEST       COPY A FILE\n"
            "  REN NEW=OLD            RENAME A FILE\n"
            "  ERA PATTERN            ERASE FILES WITH CONFIRMATION\n"
            "  STAT                   DISPLAY FREE HOST SPACE\n"
            "  UNIX COMMAND [ARGS]     RUN A HOST COMMAND\n"
            "  CLS                    CLEAR THE SCREEN\n"
            "  VER                    DISPLAY THE EMIX VERSION\n"
            "  EXIT                   RETURN TO UNIX\n\n"
            "UNKNOWN COMMANDS ARE ALSO TRIED AS HOST EXECUTABLES.\n"
            "SHELL OPERATORS SUCH AS | AND > ARE NOT INTERPRETED.\n"
        )

    def do_EXIT(self, arg: str) -> bool | None:
        """EXIT -- return to the host shell."""
        if arg.strip():
            self._write("USAGE: EXIT\n")
            return None
        self._write("RETURNING TO UNIX.\n")
        return True

    do_BYE = do_EXIT
    do_QUIT = do_EXIT

    def do_EOF(self, arg: str) -> bool:
        self._write("\nRETURNING TO UNIX.\n")
        return True

    def default(self, line: str) -> None:
        if line.strip().upper() == "A:":
            return
        self._run_host_command(line)

    def _run_host_command(self, command_line: str) -> None:
        parts = self._arguments(command_line)
        if not parts:
            return
        try:
            subprocess.run(parts, cwd=self.root, check=False)
        except FileNotFoundError:
            self._write(f"{parts[0].upper()}?\n")
        except OSError as error:
            self._write(f"HOST COMMAND ERROR: {error}\n")

    def _arguments(self, arg: str) -> list[str] | None:
        try:
            return shlex.split(arg)
        except ValueError as error:
            self._write(f"COMMAND ERROR: {error}\n")
            return None

    def _single_argument(self, arg: str, default: str | None = None) -> str | None:
        parts = self._arguments(arg)
        if parts is None:
            return None
        if not parts and default is not None:
            return default
        if len(parts) != 1:
            self._write("BAD COMMAND FORMAT\n")
            return None
        return parts[0]

    def _find_file(self, name: str) -> Path | None:
        name = self._strip_drive(name)
        if not self._valid_leaf(name):
            return None
        path = self._casefold_match(name)
        if path is None or not path.is_file():
            self._write("NO FILE\n")
            return None
        return path

    def _new_path(self, name: str) -> Path | None:
        name = self._strip_drive(name)
        if not self._valid_leaf(name):
            return None
        return self.root / name

    def _casefold_match(self, name: str) -> Path | None:
        folded = name.casefold()
        return next(
            (path for path in self.root.iterdir() if path.name.casefold() == folded),
            None,
        )

    def _valid_leaf(self, name: str, *, wildcards: bool = False) -> bool:
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            self._write("BAD FILE NAME\n")
            return False
        if not wildcards and any(character in name for character in "*?"):
            self._write("BAD FILE NAME\n")
            return False
        return True

    @staticmethod
    def _strip_drive(name: str) -> str:
        return name[2:] if name[:2].upper() == "A:" else name

    def _confirm(self, prompt: str) -> bool:
        self._write(prompt)
        response = self.stdin.readline()
        return response.strip().upper() in {"Y", "YES"}

    def _write(self, text: str) -> None:
        self.stdout.write(text)
        self.stdout.flush()

