"""Asking the terminal what colour it is.

Green phosphor is the right default only on a dark screen; on a light one it
is merely hard to read. So Emix asks rather than assumes, and when it cannot
get an answer it does not guess — it falls back to a colour that works on
either ground.

Two methods, cheapest first:

1. ``COLORFGBG``, which some terminals export. Free, and no I/O.
2. The OSC 11 query — write ``ESC ] 11 ; ? ESC \\`` and the terminal replies
   with its background colour. This is what modern terminals answer; those
   that do not simply say nothing, which is why the read is on a short timeout
   and every failure path returns "unknown" rather than a wrong answer.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import os
import re
import sys
import time
from typing import TextIO

from emix.host import on_windows

#: How long to wait for a terminal that may never answer.
_TIMEOUT = 0.12

#: ``rgb:RRRR/GGGG/BBBB``, with 1 to 4 hex digits per channel.
_RGB = re.compile(rb"rgb:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})")

#: The whole reply, so it can be cut out of whatever else arrived with it.
#: OSC replies end with either ST (``ESC \``) or a bare BEL, depending on the
#: terminal, and both spellings are common enough to accept.
_REPLY = re.compile(rb"\033\]11;[^\033\a]*(?:\033\\|\a)")

#: Terminals whose background is not in doubt, so asking is pointless. The
#: Linux framebuffer console cannot answer OSC 11 at all and is always black,
#: which would otherwise leave a Raspberry Pi's own console — the most
#: period-looking screen Emix runs on — with no phosphor.
_KNOWN_DARK = frozenset({"linux"})

#: What ``SetConsoleMode`` calls VT output, which Windows consoles start with
#: switched off. Until it is on, an escape sequence is printed as its own
#: characters rather than obeyed.
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

#: ``GetStdHandle`` for standard output, and the descriptor it corresponds to.
_STD_OUTPUT_HANDLE = -11
_STDOUT_FILENO = 1

#: The dark half of the sixteen; 7 and 9-15 are the light half.
_DARK_INDICES = frozenset({0, 1, 2, 3, 4, 5, 6, 8})


def enable_ansi(stream: TextIO | None = None) -> bool:
    """Ask a Windows console to obey escape sequences. True if it will.

    ``stream`` is the one about to be written to. The question is only ever
    asked of the process's own console, so a shell writing somewhere else —
    a buffer, a capture, a file — is told yes without any console being
    touched. Asking the console about a stream that is not the console is how
    you end up disabling colour for output the console never sees.

    Everywhere else this is free: POSIX terminals have always obeyed them, so
    the answer is yes without asking anybody. On Windows the console starts in
    a mode where ``ESC[92m`` is five characters to print rather than an
    instruction, and the only way to change that is to say so.

    Windows Terminal usually arrives with the bit already set and the classic
    console usually does not, so this asks rather than assuming which one is
    in front of us.

    Every prototype is declared. ``ctypes`` defaults a return value to C
    ``int``, but ``GetStdHandle`` returns a pointer-sized ``HANDLE``: on 64-bit
    Windows an undeclared call can truncate a high-valued or redirected handle
    into a number that no later call recognises, and both console paths would
    then fail for a reason nothing reports.
    """
    if not on_windows():
        return True
    sink = sys.stdout if stream is None else stream
    try:
        descriptor = sink.fileno()
    except (AttributeError, OSError, ValueError):
        return True  # not a real file, so nothing to configure and nothing to break
    if descriptor != _STDOUT_FILENO:
        return True
    try:  # pragma: no cover - exercised only on Windows
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel.GetStdHandle.argtypes = (wintypes.DWORD,)
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetConsoleMode.restype = wintypes.BOOL
        kernel.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.SetConsoleMode.restype = wintypes.BOOL

        handle = kernel.GetStdHandle(_STD_OUTPUT_HANDLE)
        if not handle or handle == ctypes.c_void_p(-1).value:
            return False
        mode = wintypes.DWORD()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & _ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        wanted = mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel.SetConsoleMode(handle, wanted))
    except (AttributeError, OSError, ValueError):  # pragma: no cover - as above
        return False


@dataclass(frozen=True)
class Reply:
    """What the terminal said, and what the user typed while it was saying it.

    The second half matters because the probe reads from the same file
    descriptor the user types into. Anything read that was not part of the
    terminal's answer is the user's, and has to be given back rather than
    dropped on the floor.
    """

    #: ``None`` when the terminal would not say.
    dark: bool | None = None
    #: Keystrokes that arrived during the probe and must still be executed.
    typed_ahead: str = ""


def _luminance(red: float, green: float, blue: float) -> float:
    """Perceived brightness, 0 to 1. Green dominates because eyes do."""
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _from_colorfgbg() -> bool | None:
    """Read ``COLORFGBG``, which is ``foreground;background`` in ANSI colours."""
    value = os.environ.get("COLORFGBG")
    if not value:
        return None
    parts = value.split(";")
    if len(parts) < 2 or not parts[-1].isdigit():
        return None
    return int(parts[-1]) in _DARK_INDICES


def _from_osc11(stdin: TextIO, stdout: TextIO) -> Reply:
    """Ask the terminal directly. ``dark`` is ``None`` if it does not answer.

    The probe reads from the file descriptor the user is typing into, so it
    keeps reading until the reply arrives or the deadline passes, then hands
    back everything that was not the reply. Discarding that instead would
    swallow a command typed — or pasted — during the first tenth of a second.
    """
    try:
        import select
        import termios
        import tty
    except ImportError:  # pragma: no cover - not a POSIX host
        return Reply()
    try:
        descriptor = stdin.fileno()
        saved = termios.tcgetattr(descriptor)
    except (OSError, ValueError, termios.error):
        return Reply()
    seen = b""
    try:
        # TCSANOW, because tty.setraw defaults to TCSAFLUSH, which throws away
        # anything already typed. That is the difference between a probe that
        # costs a tenth of a second and one that eats a pasted command.
        tty.setraw(descriptor, termios.TCSANOW)
        stdout.write("\033]11;?\033\\")
        stdout.flush()
        deadline = time.monotonic() + _TIMEOUT
        while not _REPLY.search(seen):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
                break
            chunk = os.read(descriptor, 64)
            if not chunk:
                break
            seen += chunk
    except (OSError, ValueError):
        return Reply(typed_ahead=_decode(seen))
    finally:
        # Leaving the terminal in raw mode would break the user's shell, so
        # this restore must run even when everything above has failed.
        with contextlib.suppress(OSError, ValueError, termios.error):
            termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)

    reply = _REPLY.search(seen)
    # Whatever sits either side of the reply was typed by a person, not sent
    # by the terminal, and is theirs to get back.
    typed_ahead = _decode(seen[: reply.start()] + seen[reply.end() :] if reply else seen)
    found = _RGB.search(reply.group() if reply else b"")
    if not found:
        return Reply(typed_ahead=typed_ahead)
    channels = []
    for raw in found.groups():
        text = raw.decode("ascii")
        channels.append(int(text, 16) / (16 ** len(text) - 1))
    return Reply(dark=_luminance(*channels) < 0.4, typed_ahead=typed_ahead)


def _decode(raw: bytes) -> str:
    """Type-ahead as text. Undecodable bytes were not a command worth keeping."""
    return raw.decode("utf-8", "ignore")


def ask_background(stdin: TextIO | None = None, stdout: TextIO | None = None) -> Reply:
    """Whether the terminal has a dark background, and any keystrokes it cost.

    Never probes anything that is not an interactive terminal: writing an
    escape sequence into a pipe would corrupt whatever is reading it.
    """
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    from_environment = _from_colorfgbg()
    if from_environment is not None:
        return Reply(dark=from_environment)
    try:
        if not (source.isatty() and sink.isatty()):
            return Reply()
    except (AttributeError, ValueError):
        return Reply()
    if on_windows():
        # Unknown, deliberately. There is no termios to run an OSC 11
        # conversation over, and the legacy attribute word is not an answer:
        # Windows Terminal paints an arbitrary RGB background chosen in a
        # profile, and ConPTY reports a "default" index that says nothing
        # about it — so a black-looking nibble can be rendering white. Rather
        # than paint green onto a light screen, Emix says it does not know,
        # and a Windows user who wants the phosphor asks for it by name.
        return Reply()
    terminal = os.environ.get("TERM", "")
    if terminal in {"", "dumb"}:
        return Reply()
    if terminal in _KNOWN_DARK:
        return Reply(dark=True)
    return _from_osc11(source, sink)


def background_is_dark(stdin: TextIO | None = None, stdout: TextIO | None = None) -> bool | None:
    """Whether the terminal has a dark background. ``None`` means unknown.

    Convenience for callers with no keyboard to give type-ahead back to.
    """
    return ask_background(stdin, stdout).dark
