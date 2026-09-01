"""Personality-neutral error codes.

The engine raises :class:`EmixError` with a symbolic :class:`Code`. Each
personality renders that code in its own house style, so CP/M can answer
``NO FILE`` where VMS answers ``%RMS-E-FNF, file not found``.
"""

from __future__ import annotations

from enum import Enum


class Code(Enum):
    """What went wrong, independent of how a personality words it."""

    NO_FILE = "no such file"
    NOT_A_FILE = "not a regular file"
    BAD_NAME = "malformed file name"
    AMBIGUOUS = "several host files differ only by case"
    EXISTS = "destination already exists"
    OUTSIDE_DRIVE = "path leaves the drive root"
    NO_DRIVE = "no such drive"
    IO_ERROR = "host I/O error"
    SYNTAX = "malformed command"
    UNKNOWN_VERB = "unrecognised command"
    AMBIGUOUS_VERB = "ambiguous abbreviation"
    NEEDS_SHELL = "running it would require a shell"


class EmixError(Exception):
    """An expected, user-facing failure.

    ``subject`` is the name the user typed (or the offending host path) and
    ``detail`` carries any extra text, such as an ``OSError`` message.
    """

    def __init__(self, code: Code, subject: str = "", detail: str = "") -> None:
        super().__init__(code.value)
        self.code = code
        self.subject = subject
        self.detail = detail

    def __str__(self) -> str:
        parts = [self.code.value]
        if self.subject:
            parts.append(f"({self.subject})")
        if self.detail:
            parts.append(f"- {self.detail}")
        return " ".join(parts)
