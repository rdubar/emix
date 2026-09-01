"""WOPR — the war room computer from *WarGames* (1983).

The one personality with no machine behind it, and the reason it can exist at
all. Every other personality is measured against a real system and can be
caught getting it wrong; this one is measured against a film, which makes it
the only place in Emix where invention is the honest answer rather than a bug.

It is a personality rather than an easter egg on purpose. An egg hidden inside
CP/M would put invented behaviour behind a period prompt, which is the exact
thing :meth:`Shell.is_emix_verb` and the painting rule exist to prevent. A
prompt should be honest about what it is, and this one announces itself in its
first three lines.

The film's dialogue is quoted where everybody knows it and written where
nobody would notice. Recreating an interaction is what Emix does everywhere
else; reproducing a screenplay is a different act.
"""

from __future__ import annotations

from typing import ClassVar

from emix.assist import Concept
from emix.errors import Code, EmixError
from emix.host import case_collisions
from emix.shell import STOP, Invocation, Outcome, Shell, verb

#: WOPR is a machine that answers, so it says what went wrong in sentences.
_MESSAGES = {
    Code.NO_FILE: "FILE NOT FOUND: {subject}",
    Code.NOT_A_FILE: "NOT A DATA FILE: {subject}",
    Code.BAD_NAME: "DESIGNATION NOT RECOGNIZED: {subject}",
    Code.AMBIGUOUS: "DESIGNATION IS AMBIGUOUS: {detail}",
    Code.EXISTS: "FILE ALREADY EXISTS: {subject}",
    Code.OUTSIDE_DRIVE: "ACCESS DENIED: {subject}",
    Code.NO_DRIVE: "NO SUCH SEGMENT: {subject}",
    Code.IO_ERROR: "WRITE FAILURE: {subject}",
    Code.SYNTAX: "SYNTAX ERROR",
    Code.UNKNOWN_VERB: "I DO NOT UNDERSTAND '{subject}'.",
    Code.AMBIGUOUS_VERB: "AMBIGUOUS REQUEST: {subject}",
    Code.NEEDS_SHELL: "REQUEST DENIED: {subject}",
}

#: The list, in the order it scrolls up the screen in the film. The joke only
#: works because the last one arrives after twelve harmless ones.
GAMES: tuple[str, ...] = (
    "FALKEN'S MAZE",
    "BLACK JACK",
    "GIN RUMMY",
    "HEARTS",
    "BRIDGE",
    "CHECKERS",
    "CHESS",
    "POKER",
    "FIGHTER COMBAT",
    "GUERRILLA ENGAGEMENT",
    "DESERT WARFARE",
    "AIR-TO-GROUND ACTIONS",
    "THEATERWIDE TACTICAL WARFARE",
    "THEATERWIDE BIOTOXIC AND CHEMICAL WARFARE",
    "GLOBAL THERMONUCLEAR WAR",
)

#: The one that is not a game. Answering it is the whole point of the list.
_THE_ONE = "GLOBAL THERMONUCLEAR WAR"

#: What the backdoor was, and the only name WOPR is pleased to see.
_FALKEN = "JOSHUA"


class WoprShell(Shell):
    """A fictional 1983 war room computer, over your own very real files."""

    key = "wopr"
    title = "WOPR"
    # A defence computer at NORAD does not shell out to Unix for you.
    host_fallthrough = False
    explanations: ClassVar[dict[str, str]] = {
        "UNKNOWN_VERB": (
            "WOPR is not a historical system. It is Emix's one invented "
            "personality, and its vocabulary is short: LIST, DISPLAY, "
            "DUPLICATE, REDESIGNATE, PURGE, GAMES and LOGOFF."
        ),
    }
    translations: ClassVar[dict[Concept, str]] = {
        Concept.LIST: "LIST",
        Concept.SHOW: "DISPLAY",
        Concept.DELETE: "PURGE",
        Concept.COPY: "DUPLICATE NEW OLD",
        Concept.RENAME: "REDESIGNATE OLD NEW",
        Concept.HELP: "HELP",
        Concept.QUIT: "LOGOFF",
        Concept.WHERE: "LIST SEGMENTS",
    }
    absences: ClassVar[dict[Concept, str]] = {
        Concept.CHDIR: "WOPR never existed, so it never needed anywhere to go",
        Concept.CLEAR: "the film's terminal scrolled; nothing was ever cleared",
    }

    def banner(self) -> str:
        return (
            "\nGREETINGS PROFESSOR FALKEN.\n\n"
            "SHALL WE PLAY A GAME?\n\n"
            "(THIS COMPUTER IS FICTIONAL. YOUR FILES ARE NOT.)\n"
            "TYPE HELP FOR COMMANDS, OR LIST GAMES.\n"
        )

    def prompt(self) -> str:
        # WOPR has no prompt in the film. It simply waits, as CMS does.
        return ""

    def render_error(self, error: EmixError) -> str:
        template = _MESSAGES.get(error.code, "I DO NOT UNDERSTAND.")
        return template.format(subject=error.subject.upper(), detail=error.detail) + "\n"

    def house_case(self, text: str) -> str:
        return text.upper()

    def farewell(self) -> str:
        return "\nGOODBYE.\n"

    # -- files, which are the part that is real ---------------------------

    @verb("LIST", summary="List files, or GAMES, or SEGMENTS", usage="LIST [pattern|GAMES]")
    def do_list(self, invocation: Invocation) -> None:
        topic = invocation.args[0].upper() if invocation.args else ""
        if topic == "GAMES":
            self.do_games(invocation)
            return
        if topic == "SEGMENTS":
            for name in self.drives.names:
                marker = "*" if name == self.drives.current else " "
                self.write(f"{marker} {name}  {self.drives.drive(name).root}\n")
            return
        pattern = invocation.args[0] if invocation.args else "*"
        entries = self.drives.match(pattern, files_only=True)
        if not entries:
            raise EmixError(Code.NO_FILE, pattern)
        collisions = case_collisions(entries)
        for entry in entries:
            suffix = "  (CASE AMBIGUOUS)" if entry.name in collisions else ""
            self.write(f"{entry.name.upper()}{suffix}\n")

    @verb("DISPLAY", summary="Display a file", usage="DISPLAY name", aliases=("TYPE",))
    def do_display(self, invocation: Invocation) -> None:
        if not invocation.args:
            raise EmixError(Code.SYNTAX, "DISPLAY")
        content = self.drives.read_text(self.drives.locate(invocation.args[0]))
        self.write(content)
        if content and not content.endswith("\n"):
            self.write("\n")

    @verb("DUPLICATE", summary="Copy a file", usage="DUPLICATE new old", aliases=("COPY",))
    def do_duplicate(self, invocation: Invocation) -> None:
        # Destination first, as CP/M's PIP had it: WOPR is of that era.
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, "DUPLICATE")
        new, old = invocation.args
        self.drives.copy(self.drives.locate(old), self.drives.reserve(new))

    @verb("REDESIGNATE", summary="Rename a file", usage="REDESIGNATE old new", aliases=("RENAME",))
    def do_redesignate(self, invocation: Invocation) -> None:
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, "REDESIGNATE")
        old, new = invocation.args
        self.drives.rename(self.drives.locate(old), self.drives.reserve(new))

    @verb("PURGE", summary="Delete files", usage="PURGE pattern", aliases=("DELETE",))
    def do_purge(self, invocation: Invocation) -> None:
        if not invocation.args:
            raise EmixError(Code.SYNTAX, "PURGE")
        matches = self.drives.match(invocation.args[0], files_only=True)
        if not matches:
            raise EmixError(Code.NO_FILE, invocation.args[0])
        listing = ", ".join(path.name.upper() for path in matches)
        if not self.confirm(f"CONFIRM PERMANENT DELETION OF {listing}. PROCEED? (Y/N) "):
            self.write("NO FILES DELETED.\n")
            return
        for path in matches:
            self.drives.unlink(path)

    # -- the reason anybody typed WOPR ------------------------------------

    @verb("GAMES", summary="List the games", usage="GAMES")
    def do_games(self, invocation: Invocation) -> None:
        self.write("\n".join(GAMES) + "\n")

    @verb("PLAY", summary="Play a game", usage="PLAY name")
    def do_play(self, invocation: Invocation) -> None:
        wanted = " ".join(invocation.args).upper().strip()
        if not wanted:
            self.write("SHALL WE PLAY A GAME?\n")
            return
        if wanted == _THE_ONE:
            # A refusal is both the joke and the correct implementation.
            self.write("\nA STRANGE GAME.\nTHE ONLY WINNING MOVE IS NOT TO PLAY.\n\n")
            self.write("HOW ABOUT A NICE GAME OF CHESS?\n")
            return
        if wanted in GAMES:
            self.write(f"{wanted} IS NOT INSTALLED ON THIS SYSTEM.\n")
            self.write("EMIX SHIPS NO GAMES. IT NEVER SHIPPED ANYTHING.\n")
            return
        raise EmixError(Code.UNKNOWN_VERB, wanted)

    @verb("LOGON", summary="Identify yourself", usage="LOGON name")
    def do_logon(self, invocation: Invocation) -> None:
        who = " ".join(invocation.args).upper().strip()
        if who == _FALKEN:
            self.write("\nGREETINGS PROFESSOR FALKEN.\n\nSHALL WE PLAY A GAME?\n")
            return
        self.write("IDENTIFICATION NOT RECOGNIZED BY SYSTEM.\n")

    @verb("HELP", summary="List commands", usage="HELP [command]")
    def do_help(self, invocation: Invocation) -> None:
        if invocation.args:
            found = self.lookup(invocation.args[0])
            if found is None:
                raise EmixError(Code.UNKNOWN_VERB, invocation.args[0])
            self.write(
                f"\n{found.name}\n\n  {found.summary.upper()}\n\n  FORMAT: {found.usage}\n\n"
            )
            return
        self.write("AVAILABLE COMMANDS:\n")
        for found in self.verbs:
            if not found.hidden:
                self.write(f"  {found.usage:<24} {found.summary.upper()}\n")

    @verb("LOGOFF", summary="End the session", usage="LOGOFF", aliases=("LOGOUT", "EXIT", "QUIT"))
    def do_logoff(self, invocation: Invocation) -> Outcome:
        self._require_no_arguments(invocation)
        return STOP
