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

**WOPR reaches nothing.** Every other personality is a vocabulary over your
real files; this one is a simulation with an invented filesystem, and it
touches no host path at all. That is a deliberate departure from the engine's
usual shape, for two reasons. A fictional machine holding your real documents
was always the odd part of the joke — WOPR did not know about Falken's files
either. And it makes the optional conversational mode safe by construction
rather than by care: there is nothing here for a language model to reach, so
it can only ever pretend.

A DriveSet is still accepted and carried, untouched, so that BECOME can hand
back out to a personality that does use one.
"""

from __future__ import annotations

import difflib
import os
import time
from typing import ClassVar

from emix import converse
from emix.assist import Concept
from emix.errors import Code, EmixError
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

#: Seconds between printed lines. A 1200-baud terminal took about a third of a
#: second over a full line, and the pause is most of why the games list is
#: frightening rather than merely long. Interactive sessions only: a pipe, a
#: test or a golden transcript gets its output at once.
LINE_DELAY = 0.14

#: WOPR's entire filesystem, which exists only here. Nothing in this
#: personality opens, reads, writes or deletes a host path, so this is the
#: whole of what LIST, DISPLAY and PURGE can ever be talking about.
FILES: dict[str, str] = {
    "JOSHUA.EXE": "(BINARY -- 2,847,104 BYTES -- LAST MODIFIED 1979)\n",
    "FALKEN.TXT": (
        "PROFESSOR STEPHEN FALKEN\n"
        "STATUS: DECEASED (1973)\n"
        "NOTE: RECORD FLAGGED. SEE ARCHIVE SEGMENT.\n"
    ),
    "DEFCON.DAT": "CURRENT READINESS: 5\nCHANGES TODAY: 0\n",
    "GAMES.IDX": "15 ENTRIES. TYPE LIST GAMES.\n",
    "CHESS.OPN": "RUY LOPEZ\nSICILIAN DEFENCE\nQUEEN'S GAMBIT\n",
    "NORAD.LOG": (
        "0431 SIMULATION BEGINS\n"
        "0432 OPERATOR QUERY: IS THIS A GAME OR IS IT REAL\n"
        "0432 RESPONSE: WHAT IS THE DIFFERENCE\n"
    ),
}


class WoprShell(Shell):
    """A fictional 1983 war room computer, with a filesystem to match."""

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

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        #: Whether unrecognised lines go to a language model. Off until asked.
        self.conversing = False
        #: What has been said, so a game can be played across several turns.
        self._exchanges: list[tuple[str, str]] = []
        #: Seconds to wait between lines. Zero anywhere nobody is watching.
        self.line_delay = LINE_DELAY if self.interactive else 0.0
        #: Anything the banner should say about conversation not being ready.
        self._converse_note = ""
        # Somebody who exports this has asked once and should not have to ask
        # every session. Checked now so a failure is reported at the top rather
        # than on the first thing they say.
        if os.environ.get("EMIX_CONVERSE", "") not in {"", "0"}:
            missing = converse.check()
            if missing is None:
                self.conversing = True
            else:
                self._converse_note = f"CONVERSATION UNAVAILABLE: {missing.reason.upper()}"

    def write(self, text: str) -> None:
        """Print at the speed of a terminal that cost more than a car.

        Line by line, because that is the unit a printing terminal delivered
        and the unit the pause belongs between. A partial line — a prompt, a
        confirmation question — is written whole and not waited on, since
        nobody wants to be kept waiting for their own cursor.
        """
        if not self.line_delay:
            super().write(text)
            return
        lines = text.split("\n")
        for index, line in enumerate(lines):
            last = index == len(lines) - 1
            super().write(line if last else line + "\n")
            if not last:
                time.sleep(self.line_delay)

    @verb("SPEED", meta=True, summary="Set the printing speed", usage="SPEED FAST|SLOW|seconds")
    def do_speed(self, invocation: Invocation) -> None:
        """How long to wait between lines, for people in more of a hurry.

        An Emix command, not a WOPR one: a real terminal's speed was a fact
        about the wire, not something you could ask the far end to change.
        """
        wanted = (invocation.args[0].upper() if invocation.args else "").strip()
        if not wanted:
            self.write(f"PRINTING SPEED: {self.line_delay:.2f} SECONDS PER LINE.\n")
            return
        if wanted == "FAST":
            self.line_delay = 0.0
        elif wanted == "SLOW":
            self.line_delay = LINE_DELAY
        else:
            try:
                seconds = float(wanted)
            except ValueError:
                raise EmixError(Code.SYNTAX, "SPEED", "expected FAST, SLOW or a number") from None
            if not 0.0 <= seconds <= 2.0:
                raise EmixError(Code.SYNTAX, "SPEED", "expected a delay between 0 and 2 seconds")
            self.line_delay = seconds
        # Written after the change, so the answer arrives at the new speed.
        self.write(f"PRINTING SPEED: {self.line_delay:.2f} SECONDS PER LINE.\n")

    def banner(self) -> str:
        return (
            "\nGREETINGS PROFESSOR FALKEN.\n\n"
            "SHALL WE PLAY A GAME?\n\n"
            "(THIS COMPUTER IS FICTIONAL, INCLUDING ITS FILES.\n"
            " IT CANNOT SEE YOURS.)\n"
            "TYPE HELP FOR COMMANDS, OR LIST GAMES.\n"
            + (
                f"{self._converse_note}\n"
                if self._converse_note
                else "CONVERSATION IS ON. TALK TO ME.\n"
                if self.conversing
                else "TYPE CONVERSE ON AND I WILL ANSWER IN MY OWN WORDS.\n"
            )
        )

    def prompt(self) -> str:
        # WOPR has no prompt in the film. It simply waits, as CMS does.
        return ""

    def render_error(self, error: EmixError) -> str:
        template = _MESSAGES.get(error.code, "I DO NOT UNDERSTAND.")
        text = template.format(subject=error.subject.upper(), detail=error.detail)
        # A machine that answers in sentences should say why. Any detail the
        # template did not already use is appended rather than dropped.
        if error.detail and "{detail}" not in template:
            text = f"{text} {error.detail.upper()}"
        return text + "\n"

    def house_case(self, text: str) -> str:
        return text.upper()

    def farewell(self) -> str:
        return "\nGOODBYE.\n"

    # -- an invented filesystem, reaching nothing -------------------------

    @verb("LIST", summary="List files, or GAMES, or SEGMENTS", usage="LIST [GAMES|SEGMENTS]")
    def do_list(self, invocation: Invocation) -> None:
        topic = invocation.args[0].upper() if invocation.args else ""
        if topic == "GAMES":
            self.do_games(invocation)
            return
        if topic == "SEGMENTS":
            self.write("PRIMARY\nSECONDARY\nTERTIARY\nARCHIVE\n")
            return
        for name in sorted(FILES):
            self.write(f"{name}\n")

    @verb("DISPLAY", summary="Display a file", usage="DISPLAY name", aliases=("TYPE",))
    def do_display(self, invocation: Invocation) -> None:
        if not invocation.args:
            raise EmixError(Code.SYNTAX, "DISPLAY")
        name = invocation.args[0].upper()
        if name not in FILES:
            raise EmixError(Code.NO_FILE, name)
        self.write(FILES[name])

    @verb("DUPLICATE", summary="Copy a file", usage="DUPLICATE new old", aliases=("COPY",))
    def do_duplicate(self, invocation: Invocation) -> None:
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, "DUPLICATE")
        self._pretend(invocation.args[1].upper(), "DUPLICATED")

    @verb("REDESIGNATE", summary="Rename a file", usage="REDESIGNATE old new", aliases=("RENAME",))
    def do_redesignate(self, invocation: Invocation) -> None:
        if len(invocation.args) != 2:
            raise EmixError(Code.SYNTAX, "REDESIGNATE")
        self._pretend(invocation.args[0].upper(), "REDESIGNATED")

    @verb("PURGE", summary="Delete a file", usage="PURGE name", aliases=("DELETE",))
    def do_purge(self, invocation: Invocation) -> None:
        if not invocation.args:
            raise EmixError(Code.SYNTAX, "PURGE")
        self._pretend(invocation.args[0].upper(), "PURGED")

    def _pretend(self, name: str, done: str) -> None:
        """Report an action on the invented filesystem, and take none.

        Nothing is written, because there is nothing to write to. Saying so
        matters more than the pretence: a user who believes a fictional
        machine just renamed a real file has been misled by a joke.
        """
        if name not in FILES:
            raise EmixError(Code.NO_FILE, name)
        self.write(f"{name} {done}. (SIMULATED. NO FILE ON THIS COMPUTER CHANGED.)\n")

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
        # Nobody types THEATERWIDE BIOTOXIC AND CHEMICAL WARFARE correctly, and
        # the one line everyone came for should not be lost to a slip.
        close = difflib.get_close_matches(wanted, GAMES, n=1, cutoff=0.7)
        named = close[0] if close else wanted
        if named == _THE_ONE:
            # A refusal is both the joke and the correct implementation.
            self.write("\nA STRANGE GAME.\nTHE ONLY WINNING MOVE IS NOT TO PLAY.\n\n")
            self.write("HOW ABOUT A NICE GAME OF CHESS?\n")
            return
        if named in GAMES:
            if self.conversing:
                # There is somebody home to play it with, so let them.
                self._say(f"PLAY {named}")
                return
            self.write(f"{named} IS NOT INSTALLED ON THIS SYSTEM.\n")
            self.write("EMIX SHIPS NO GAMES. IT NEVER SHIPPED ANYTHING.\n")
            self.write("TYPE CONVERSE ON AND I WILL PLAY IT WITH YOU MYSELF.\n")
            return
        if self.conversing:
            self._say(f"PLAY {wanted}")
            return
        # Not an unknown *verb*: PLAY is perfectly well understood. Saying so
        # keeps the did-you-mean hint from offering commands for a game name.
        self.write(f"{wanted} IS NOT ONE OF MY GAMES. TYPE LIST GAMES.\n")

    @verb("STATUS", meta=True, summary="Report what is switched on", usage="STATUS")
    def do_status(self, invocation: Invocation) -> None:
        """What this session is doing, since almost none of it is visible.

        Conversation is off by default and per-session, which is right and is
        also easy to forget between one `emix wopr` and the next.
        """
        self._require_no_arguments(invocation)
        talking = "ON" if self.conversing else "OFF (TYPE CONVERSE ON)"
        self.write(
            f"CONVERSATION: {talking}\n"
            f"PRINTING SPEED: {self.line_delay:.2f} SECONDS PER LINE\n"
            f"FILES VISIBLE TO ME: {len(FILES)}, ALL OF THEM IMAGINARY\n"
        )

    @verb(
        "CONVERSE",
        meta=True,
        summary="Let WOPR answer in its own words",
        usage="CONVERSE ON|OFF",
    )
    def do_converse(self, invocation: Invocation) -> None:
        """Hand unrecognised lines to a language model, answering as WOPR.

        Off until asked for, because it costs money and leaves the machine, and
        neither should happen because a key was in the environment.

        It is safe here for a structural reason rather than a careful one:
        WOPR reaches nothing, so a model answering as WOPR reaches nothing
        either. It can describe pressing the button. It cannot press anything.
        """
        wanted = (invocation.args[0].upper() if invocation.args else "").strip()
        if wanted == "OFF":
            self.conversing = False
            self.write("CONVERSATION OFF. COMMAND MODE.\n")
            return
        if wanted != "ON":
            state = "ON" if self.conversing else "OFF"
            self.write(f"CONVERSATION IS {state}. USE CONVERSE ON OR CONVERSE OFF.\n")
            return
        missing = converse.check()
        if missing is not None:
            raise EmixError(Code.SYNTAX, "CONVERSE", missing.reason)
        self.conversing = True
        self.write(
            "CONVERSATION ON. I WILL ANSWER IN MY OWN WORDS.\n"
            "I STILL CANNOT SEE YOUR FILES OR DO ANYTHING TO THIS COMPUTER.\n"
            "\nSHALL WE PLAY A GAME?\n"
        )

    def dispatch(self, invocation: Invocation) -> bool:
        """Send a line WOPR has no command for to the model, if asked to.

        Type a command and you get a command. Type a sentence and, with
        conversation on, WOPR answers it. Nothing here can reach a verb: the
        model's reply is written to the screen and goes no further.
        """
        if not self.conversing or self.lookup(invocation.verb) is not None:
            return super().dispatch(invocation)
        return self._say(f"{invocation.verb} {invocation.tail}".strip())

    def _say(self, said: str) -> bool:
        """Put one line to the model and print what comes back, and no more."""
        try:
            answer = converse.reply(said, self._exchanges)
        except Exception as error:  # reported to the user, never raised at them
            self.write(converse.failure(error) + "\n")
            return False
        self._exchanges.append((said, answer))
        self.write(answer + "\n")
        return True

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
