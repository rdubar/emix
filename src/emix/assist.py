"""Assistance that teaches the historical system instead of replacing it.

Emix exists so somebody can find out what these systems felt like. That goal
is easy to destroy with kindness: if typing ``ls`` quietly ran ``DIR``, the
user would never learn ``DIR``, and Emix would be misrepresenting CP/M while
appearing helpful.

So assistance here obeys three rules.

1. **The authentic response comes first, verbatim.** ``LS?`` is exactly what
   CP/M printed, and it still prints. A hint is added *below* it, never
   instead of it, and never reworded.
2. **Hints are visibly Emix's voice.** They carry a marker no historical
   system used, so nobody mistakes invented prose for a period diagnostic.
3. **Nothing is executed on a guess.** A hint names the real command; the
   user types it. That is what turns a convenience into a lesson.

:data:`Concept` is the pivot that keeps this to one table rather than three:
modern habits map to an idea, and each personality says what it calls that
idea. ``rm`` is a *deletion*; CP/M spells that ``ERA``, CMS ``ERASE``, and
VMS ``DELETE`` with a version number it will insist on.
"""

from __future__ import annotations

from collections.abc import Iterable
import difflib
from enum import Enum

#: Named colours for the hint marker. ``none`` disables colour entirely.
#:
#: Colour matters here beyond taste: a hint is Emix speaking over a
#: reproduction of somebody else's system, and a different colour separates
#: the two voices faster than any prefix can.
COLOURS: dict[str, str] = {
    "yellow": "33",
    "cyan": "36",
    "green": "32",
    "magenta": "35",
    "blue": "34",
    "red": "31",
    "grey": "90",
    "gray": "90",
    "none": "",
}

#: On a dark terminal, green phosphor. Anywhere else — or when the terminal
#: will not say — amber, which stays legible on either ground.
PHOSPHOR = "green"
DEFAULT_COLOUR = "yellow"


def default_colour(dark: bool | None) -> str:
    """The hint colour to use when nobody has chosen one."""
    return PHOSPHOR if dark else DEFAULT_COLOUR


def colourise(text: str, colour: str) -> str:
    """Wrap ``text`` in an ANSI colour, or return it untouched."""
    code = COLOURS.get(colour, "")
    return f"\033[{code}m{text}\033[0m" if code else text


#: How close a mistyped verb must be before Emix mentions the real one.
_SIMILARITY = 0.6

#: How many near-misses to offer at once.
_SUGGESTIONS = 3


class Concept(Enum):
    """A thing a user wants to do, independent of what any system calls it."""

    LIST = "list the files"
    SHOW = "show a file's contents"
    DELETE = "delete a file"
    COPY = "copy a file"
    RENAME = "rename a file"
    HELP = "ask for help"
    QUIT = "leave"
    CLEAR = "clear the screen"
    WHERE = "ask where you are"
    CHDIR = "change directory"


#: Modern habits, folded to lower case. These are the commands a user's hands
#: type before their brain catches up.
MODERN: dict[str, Concept] = {
    "ls": Concept.LIST,
    "ll": Concept.LIST,
    "dir": Concept.LIST,
    "cat": Concept.SHOW,
    "more": Concept.SHOW,
    "less": Concept.SHOW,
    "head": Concept.SHOW,
    "tail": Concept.SHOW,
    "type": Concept.SHOW,
    "rm": Concept.DELETE,
    "del": Concept.DELETE,
    "unlink": Concept.DELETE,
    "cp": Concept.COPY,
    "copy": Concept.COPY,
    "mv": Concept.RENAME,
    "move": Concept.RENAME,
    "ren": Concept.RENAME,
    "help": Concept.HELP,
    "man": Concept.HELP,
    "info": Concept.HELP,
    "?": Concept.HELP,
    "exit": Concept.QUIT,
    "quit": Concept.QUIT,
    "logout": Concept.QUIT,
    "bye": Concept.QUIT,
    "clear": Concept.CLEAR,
    "cls": Concept.CLEAR,
    "pwd": Concept.WHERE,
    "cd": Concept.CHDIR,
    "chdir": Concept.CHDIR,
}


def concept_for(verb: str) -> Concept | None:
    return MODERN.get(verb.strip().lower())


def translation_hint(title: str, verb: str, translations: dict[Concept, str]) -> str | None:
    """ "CP/M has no ls. Try DIR." — or nothing, if there is no honest answer.

    Silence is a real outcome. Where a system genuinely had no equivalent,
    inventing one would teach a system that never existed.
    """
    concept = concept_for(verb)
    if concept is None:
        return None
    replacement = translations.get(concept)
    if not replacement:
        return None
    typed = verb.strip()
    if typed.upper() == replacement.split()[0].upper():
        return None
    return f"{title} has no {typed.lower()}. To {concept.value}, use {replacement}."


def near_misses(typed: str, known: Iterable[str]) -> list[str]:
    """Names close enough to ``typed`` to be worth mentioning."""
    candidates = sorted({name.upper() for name in known})
    return difflib.get_close_matches(typed.upper(), candidates, n=_SUGGESTIONS, cutoff=_SIMILARITY)


def did_you_mean(typed: str, known: Iterable[str], *, noun: str = "command") -> str | None:
    found = near_misses(typed, known)
    if not found:
        return None
    if len(found) == 1:
        return f"Did you mean the {noun} {found[0]}?"
    return f"Close {noun}s: {', '.join(found)}."


#: Why each failure happens, in terms of the system rather than the code.
#:
#: These are Emix's own words about a real behaviour, which is why ``EXPLAIN``
#: prints them under the Emix marker. Anything a personality wants to add
#: about its own rules goes in :attr:`Shell.explanations`.
GENERAL: dict[str, str] = {
    "NO_FILE": "No file of that name is on the selected drive.",
    "NOT_A_FILE": "That name exists but is a directory, not a file.",
    "BAD_NAME": (
        "That name cannot be used here. Separators, wildcards where none are "
        "allowed, and the names '.' and '..' are all rejected before the host "
        "is touched."
    ),
    "AMBIGUOUS": (
        "Two host files differ only by case, and this system folds case, so "
        "both would answer to the same name. Emix refuses rather than picking "
        "one for you. Rename one on the host."
    ),
    "EXISTS": "Something of that name is already there, and Emix will not overwrite it.",
    "OUTSIDE_DRIVE": (
        "That path leaves the drive once symlinks are followed. Drives are "
        "sealed: a personality can only reach inside its own root."
    ),
    "NO_DRIVE": "No such drive is mounted. Mount more with --mount.",
    "IO_ERROR": (
        "The host refused the operation. The detail after the dash is the host's own words."
    ),
    "SYNTAX": "The command was recognised but its arguments were not in the expected shape.",
    "UNKNOWN_VERB": "This system has no such command.",
    "AMBIGUOUS_VERB": (
        "The abbreviation matches more than one command, so it is not yet "
        "unambiguous. Type more letters."
    ),
}


def explain(code_name: str, personality_notes: dict[str, str]) -> list[str]:
    """Lines explaining a failure: the general rule, then the local one."""
    lines = []
    general = GENERAL.get(code_name)
    if general:
        lines.append(general)
    local = personality_notes.get(code_name)
    if local:
        lines.append(local)
    return lines
