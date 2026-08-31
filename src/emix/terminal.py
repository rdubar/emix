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
import os
import re
import sys
from typing import TextIO

#: How long to wait for a terminal that may never answer.
_TIMEOUT = 0.12

#: ``rgb:RRRR/GGGG/BBBB``, with 1 to 4 hex digits per channel.
_RGB = re.compile(rb"rgb:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})")


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
    background = int(parts[-1])
    # 0-6 and 8 are the dark half of the sixteen; 7 and 9-15 are the light.
    return background in {0, 1, 2, 3, 4, 5, 6, 8}


def _from_osc11(stdin: TextIO, stdout: TextIO) -> bool | None:
    """Ask the terminal directly. Returns ``None`` if it does not answer."""
    try:
        import select
        import termios
        import tty
    except ImportError:  # pragma: no cover - not a POSIX host
        return None
    try:
        descriptor = stdin.fileno()
        saved = termios.tcgetattr(descriptor)
    except (OSError, ValueError, termios.error):
        return None
    try:
        tty.setraw(descriptor)
        stdout.write("\033]11;?\033\\")
        stdout.flush()
        if not select.select([descriptor], [], [], _TIMEOUT)[0]:
            return None
        reply = os.read(descriptor, 64)
    except (OSError, ValueError):
        return None
    finally:
        # Leaving the terminal in raw mode would break the user's shell, so
        # this restore must run even when everything above has failed.
        with contextlib.suppress(OSError, ValueError, termios.error):
            termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)

    found = _RGB.search(reply)
    if not found:
        return None
    channels = []
    for raw in found.groups():
        text = raw.decode("ascii")
        channels.append(int(text, 16) / (16 ** len(text) - 1))
    return _luminance(*channels) < 0.4


def background_is_dark(stdin: TextIO | None = None, stdout: TextIO | None = None) -> bool | None:
    """Whether the terminal has a dark background. ``None`` means unknown.

    Never probes anything that is not an interactive terminal: writing an
    escape sequence into a pipe would corrupt whatever is reading it.
    """
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    from_environment = _from_colorfgbg()
    if from_environment is not None:
        return from_environment
    try:
        if not (source.isatty() and sink.isatty()):
            return None
    except (AttributeError, ValueError):
        return None
    if os.environ.get("TERM", "") in {"", "dumb"}:
        return None
    return _from_osc11(source, sink)
