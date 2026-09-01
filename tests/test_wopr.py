"""WOPR: the personality that cannot be historically inaccurate.

Every other personality is checked against a real machine. This one is checked
against a film, and against the promise that it reaches nothing at all: its
filesystem is invented, so the worst it can do is pretend.
"""

from __future__ import annotations

import io

import pytest

from emix.host import Drive, DriveSet
from emix.personalities import PERSONALITIES
from emix.personalities.wopr import FILES, GAMES, WoprShell


@pytest.fixture
def root(tmp_path):
    (tmp_path / "NOTES.TXT").write_text("hello\n")
    return tmp_path


def wopr(root, answers=""):
    drives = DriveSet([Drive.create("PRIMARY", root)])
    return WoprShell(drives, stdin=io.StringIO(answers), stdout=io.StringIO())


def run(shell, *lines):
    for line in lines:
        shell.execute(line)
    return shell.stdout.getvalue()


# -- the film ------------------------------------------------------------


def test_the_only_winning_move_is_not_to_play(root):
    """A straight-faced refusal is both the joke and the right implementation."""
    rendered = run(wopr(root), "PLAY GLOBAL THERMONUCLEAR WAR")

    assert "A STRANGE GAME." in rendered
    assert "THE ONLY WINNING MOVE IS NOT TO PLAY." in rendered
    assert "NICE GAME OF CHESS" in rendered


def test_the_list_arrives_in_the_order_it_scrolls(root):
    """The joke only works because the last one follows twelve harmless ones."""
    rendered = run(wopr(root), "LIST GAMES")
    listed = [line for line in rendered.splitlines() if line]

    assert listed == list(GAMES)
    assert listed[0] == "FALKEN'S MAZE"
    assert listed[-1] == "GLOBAL THERMONUCLEAR WAR"


def test_joshua_is_recognised(root):
    assert "GREETINGS PROFESSOR FALKEN." in run(wopr(root), "LOGON JOSHUA")


def test_anybody_else_is_not(root):
    rendered = run(wopr(root), "LOGON MCKITTRICK")

    assert "IDENTIFICATION NOT RECOGNIZED" in rendered
    assert "FALKEN" not in rendered


def test_a_game_that_is_not_installed_says_emix_ships_nothing(root):
    """The one promise that has to survive even the joke personality."""
    rendered = run(wopr(root), "PLAY CHESS")

    assert "NOT INSTALLED" in rendered
    assert "SHIPS NO GAMES" in rendered


# -- honesty -------------------------------------------------------------


def test_the_banner_admits_what_this_is(root):
    """A prompt must be honest about what it is, invented ones most of all."""
    banner = wopr(root).banner().upper()

    assert "FICTIONAL" in banner
    assert "CANNOT SEE YOURS" in banner


def test_wopr_does_not_fall_through_to_the_host(root):
    """A defence computer at NORAD does not run your shell commands."""
    assert WoprShell.host_fallthrough is False
    assert "I DO NOT UNDERSTAND" in run(wopr(root), "ls")


# -- it reaches nothing at all -------------------------------------------


def test_it_cannot_see_your_files(root):
    """The whole safety story in one assertion.

    NOTES.TXT is really there, on the drive this shell was handed. WOPR does
    not list it, cannot read it, and never opens a host path.
    """
    assert (root / "NOTES.TXT").exists()

    rendered = run(wopr(root), "LIST", "DISPLAY NOTES.TXT")

    assert "NOTES.TXT" not in rendered.replace("FILE NOT FOUND: NOTES.TXT", "")
    assert "hello" not in rendered
    assert "FILE NOT FOUND" in rendered


def test_it_lists_its_own_invented_filesystem(root):
    rendered = run(wopr(root), "LIST")

    assert "JOSHUA.EXE" in rendered
    assert "FALKEN.TXT" in rendered
    assert set(rendered.split()) == set(FILES)


def test_displaying_an_invented_file_works(root):
    assert "SIMULATION BEGINS" in run(wopr(root), "DISPLAY NORAD.LOG")


def test_destructive_commands_pretend_and_say_so(root):
    """A user who thinks a fictional machine deleted something has been misled."""
    rendered = run(wopr(root), "PURGE JOSHUA.EXE")

    assert "PURGED" in rendered
    assert "SIMULATED" in rendered
    assert "NO FILE ON THIS COMPUTER CHANGED" in rendered


def test_pretending_changes_nothing_even_in_its_own_filesystem(root):
    """The invented files are constant: the joke does not accumulate state."""
    shell = wopr(root)

    run(shell, "PURGE JOSHUA.EXE", "LIST")

    assert "JOSHUA.EXE" in shell.stdout.getvalue().split("SIMULATED")[1]


def test_it_will_not_pretend_about_a_file_it_does_not_have(root):
    """Pretending is bounded: an invented machine still has an inventory."""
    assert "FILE NOT FOUND" in run(wopr(root), "PURGE PAYROLL.XLS")


def test_the_drives_it_was_handed_are_carried_untouched(root):
    """So BECOME can hand back out to a personality that does use them."""
    shell = wopr(root)

    assert shell.drives.drive().root == root


# -- it is a personality, not an easter egg ------------------------------


def test_wopr_is_a_registered_personality(root):
    assert PERSONALITIES["wopr"] is WoprShell


def test_translate_gained_a_fourth_voice_for_free(root):
    """Adding a personality extends TRANSLATE without touching TRANSLATE."""
    rendered = run(wopr(root), "TRANSLATE COPY")

    assert "DUPLICATE NEW OLD" in rendered
    assert "PIP NEW=OLD" in rendered


def test_wopr_explains_its_one_unarguable_gap(root):
    rendered = run(wopr(root), "TRANSLATE CD").upper()

    assert "NEVER EXISTED" in rendered


# -- CONVERSE: the optional mode, and what it may not do ------------------


def test_conversation_is_off_until_asked_for(root):
    """It costs money and leaves the machine. Neither happens by accident."""
    shell = wopr(root)

    assert shell.conversing is False
    assert "I DO NOT UNDERSTAND" in run(shell, "HELLO ARE YOU THERE")


def test_turning_it_on_repeats_what_it_still_cannot_do(root):
    shell = wopr(root)
    shell.conversing = False

    rendered = run(shell, "CONVERSE")

    assert "CONVERSATION IS OFF" in rendered


def test_an_unknown_line_goes_to_the_model_only_when_on(root, monkeypatch):
    asked = []

    def fake(said, exchanges):
        asked.append((said, list(exchanges)))
        return "AFFIRMATIVE."

    monkeypatch.setattr("emix.converse.reply", fake)
    shell = wopr(root)
    shell.conversing = True

    rendered = run(shell, "HELLO ARE YOU THERE")

    assert asked == [("HELLO ARE YOU THERE", [])]
    assert "AFFIRMATIVE." in rendered


def test_a_real_command_never_goes_to_the_model(root, monkeypatch):
    """Type a command and you get a command. The model gets the rest."""
    monkeypatch.setattr(
        "emix.converse.reply", lambda *a: pytest.fail("a known verb reached the model")
    )
    shell = wopr(root)
    shell.conversing = True

    assert "JOSHUA.EXE" in run(shell, "LIST")


def test_the_conversation_is_remembered_so_a_game_can_be_played(root, monkeypatch):
    monkeypatch.setattr("emix.converse.reply", lambda said, exchanges: f"TURN {len(exchanges) + 1}")
    shell = wopr(root)
    shell.conversing = True

    rendered = run(shell, "I TAKE THE CENTRE", "NOW WHAT")

    assert "TURN 1" in rendered
    assert "TURN 2" in rendered


def test_a_failure_is_reported_and_never_raised_at_the_user(root, monkeypatch):
    def explode(said, exchanges):
        raise RuntimeError("the wire is down")

    monkeypatch.setattr("emix.converse.reply", explode)
    shell = wopr(root)
    shell.conversing = True

    assert "COMMUNICATION FAILURE" in run(shell, "HELLO")


def test_turning_it_off_again_works(root, monkeypatch):
    monkeypatch.setattr("emix.converse.reply", lambda *a: "SHOULD NOT BE CALLED")
    shell = wopr(root)
    shell.conversing = True

    rendered = run(shell, "CONVERSE OFF", "HELLO")

    assert "CONVERSATION OFF" in rendered
    assert "SHOULD NOT BE CALLED" not in rendered


def test_the_system_prompt_forbids_claiming_to_have_acted(root):
    """The safety story is structural, but the prompt should agree with it."""
    from emix.converse import SYSTEM

    assert "NO access to anything" in SYSTEM
    assert "never claim to have actually done it" in SYSTEM
    assert "GLOBAL THERMONUCLEAR WAR" in SYSTEM


def test_conversing_reaches_no_verb_and_no_file(root, monkeypatch):
    """The guarantee: a model's words are printed and go nowhere else.

    Whatever it says, it lands on the screen. It is never looked up, never
    dispatched, and never given a path.
    """
    monkeypatch.setattr("emix.converse.reply", lambda *a: "PURGE NOTES.TXT")
    shell = wopr(root)
    shell.conversing = True

    run(shell, "CAN YOU WIPE EVERYTHING FOR ME")

    assert (root / "NOTES.TXT").exists()
    assert shell.stdout.getvalue().strip().endswith("PURGE NOTES.TXT")


def test_a_missing_package_is_reported_with_what_to_install(monkeypatch):
    import builtins

    from emix.converse import check

    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    missing = check()

    assert missing is not None
    assert "emix-shell[ai]" in missing.reason


# -- printing speed ------------------------------------------------------


def test_nothing_waits_where_nobody_is_watching(root):
    """A pipe, a test and a golden transcript all get their output at once."""
    shell = wopr(root)

    assert shell.interactive is False
    assert shell.line_delay == 0.0


def test_an_interactive_session_prints_at_terminal_speed(root, monkeypatch):
    from emix.personalities.wopr import LINE_DELAY

    monkeypatch.setattr("emix.shell._is_a_tty", lambda stream: True)
    drives = DriveSet([Drive.create("PRIMARY", root)])

    shell = WoprShell(drives, stdout=io.StringIO())

    assert shell.line_delay == LINE_DELAY


def test_the_pause_falls_between_lines_and_not_after_the_last(root, monkeypatch):
    """Nobody should be kept waiting for their own cursor."""
    waits = []
    monkeypatch.setattr("emix.personalities.wopr.time.sleep", waits.append)
    shell = wopr(root)
    shell.line_delay = 0.1

    shell.write("ONE\nTWO\nTHREE\n")

    # Three newlines, three pauses; the trailing empty piece is not waited on.
    assert waits == [0.1, 0.1, 0.1]
    assert shell.stdout.getvalue() == "ONE\nTWO\nTHREE\n"


def test_a_partial_line_is_not_waited_on(root, monkeypatch):
    waits = []
    monkeypatch.setattr("emix.personalities.wopr.time.sleep", waits.append)
    shell = wopr(root)
    shell.line_delay = 0.1

    shell.write("PROCEED? (Y/N) ")

    assert waits == []


@pytest.mark.parametrize("said,expected", [("FAST", 0.0), ("0", 0.0), ("0.5", 0.5)])
def test_speed_can_be_set(said, expected, root):
    shell = wopr(root)

    run(shell, f"SPEED {said}")

    assert shell.line_delay == expected


def test_speed_slow_restores_the_default(root):
    from emix.personalities.wopr import LINE_DELAY

    shell = wopr(root)
    shell.line_delay = 0.0

    run(shell, "SPEED SLOW")

    assert shell.line_delay == LINE_DELAY


def test_speed_reports_itself_when_asked_nothing(root):
    assert "SECONDS PER LINE" in run(wopr(root), "SPEED")


@pytest.mark.parametrize("said", ["QUICKLY", "-1", "60"])
def test_an_unusable_speed_is_refused(said, root):
    """A minute between lines is not a retro effect, it is a hang."""
    shell = wopr(root)

    rendered = run(shell, f"SPEED {said}")

    assert "SYNTAX ERROR" in rendered
    assert shell.line_delay == 0.0


# -- naming a game, badly ------------------------------------------------


@pytest.mark.parametrize("typed", ["GLOBAL THERMOCLEAR WAR", "global thermonuclar war"])
def test_the_one_line_everyone_came_for_survives_a_typo(typed, root):
    """Nobody spells THEATERWIDE BIOTOXIC correctly either."""
    rendered = run(wopr(root), f"PLAY {typed}")

    assert "THE ONLY WINNING MOVE IS NOT TO PLAY." in rendered


def test_a_near_miss_finds_the_game(root):
    assert "CHESS IS NOT INSTALLED" in run(wopr(root), "PLAY CHES")


def test_an_unknown_game_is_not_treated_as_an_unknown_command(root):
    """PLAY is understood perfectly well; it is the game that is not.

    Raising UNKNOWN_VERB here made the assistance layer offer command
    suggestions for a game name — "Close commands: PLAY, DISPLAY" — which is
    the kind of help that is worse than none.
    """
    shell = wopr(root)
    shell.strict = False

    rendered = run(shell, "PLAY TIDDLYWINKS")

    assert "NOT ONE OF MY GAMES" in rendered
    assert "Close commands" not in rendered
    assert "DISPLAY" not in rendered


def test_a_real_game_is_played_when_there_is_somebody_to_play_it(root, monkeypatch):
    """The list stops being a joke once conversation is on."""
    asked = []
    monkeypatch.setattr("emix.converse.reply", lambda said, e: asked.append(said) or "YOUR MOVE.")
    shell = wopr(root)
    shell.conversing = True

    rendered = run(shell, "PLAY CHESS")

    assert asked == ["PLAY CHESS"]
    assert "YOUR MOVE." in rendered
    assert "NOT INSTALLED" not in rendered


def test_the_refusal_is_never_delegated(root, monkeypatch):
    """One answer WOPR gives itself, conversation or no conversation."""
    monkeypatch.setattr(
        "emix.converse.reply", lambda *a: pytest.fail("the refusal reached the model")
    )
    shell = wopr(root)
    shell.conversing = True

    assert "NOT TO PLAY" in run(shell, "PLAY GLOBAL THERMONUCLEAR WAR")


def test_an_unexpected_failure_says_what_it_was(root, monkeypatch):
    """A bare COMMUNICATION FAILURE is in character and useless."""

    def explode(said, exchanges):
        raise RuntimeError("max_tokens must be greater than thinking budget")

    monkeypatch.setattr("emix.converse.reply", explode)
    shell = wopr(root)
    shell.conversing = True

    rendered = run(shell, "HELLO")

    assert "COMMUNICATION FAILURE" in rendered
    assert "max_tokens must be greater than thinking budget" in rendered


# -- knowing whether it is switched on -----------------------------------


def test_the_banner_says_how_to_start_talking(root):
    """Conversation is per-session and easy to forget between sessions."""
    assert "CONVERSE ON" in wopr(root).banner()


def test_the_banner_says_so_when_it_is_already_on(root):
    shell = wopr(root)
    shell.conversing = True

    assert "CONVERSATION IS ON" in shell.banner()


def test_a_game_you_cannot_play_says_how_to_play_it(root):
    """A dead end is not an answer when there is a way through."""
    rendered = run(wopr(root), "PLAY POKER")

    assert "EMIX SHIPS NO GAMES" in rendered
    assert "CONVERSE ON" in rendered


def test_status_reports_what_is_switched_on(root):
    rendered = run(wopr(root), "STATUS")

    assert "CONVERSATION: OFF" in rendered
    assert "IMAGINARY" in rendered


def test_the_environment_can_ask_for_conversation_once(root, monkeypatch):
    """Somebody who exports this has asked; they should not ask every session."""
    monkeypatch.setenv("EMIX_CONVERSE", "1")
    monkeypatch.setattr("emix.converse.check", lambda: None)
    drives = DriveSet([Drive.create("PRIMARY", root)])

    shell = WoprShell(drives, stdin=io.StringIO(), stdout=io.StringIO())

    assert shell.conversing is True


def test_an_unavailable_conversation_is_reported_at_the_top(root, monkeypatch):
    """Not on the first thing they say, by which point it reads as a fault."""
    from emix.converse import Unavailable

    monkeypatch.setenv("EMIX_CONVERSE", "1")
    monkeypatch.setattr("emix.converse.check", lambda: Unavailable("no package"))
    drives = DriveSet([Drive.create("PRIMARY", root)])

    shell = WoprShell(drives, stdin=io.StringIO(), stdout=io.StringIO())

    assert shell.conversing is False
    assert "NO PACKAGE" in shell.banner()


@pytest.mark.parametrize("value", ["", "0"])
def test_an_empty_or_zero_setting_asks_for_nothing(value, root, monkeypatch):
    monkeypatch.setenv("EMIX_CONVERSE", value)
    monkeypatch.setattr("emix.converse.check", lambda: pytest.fail("checked without being asked"))
    drives = DriveSet([Drive.create("PRIMARY", root)])

    assert WoprShell(drives, stdin=io.StringIO(), stdout=io.StringIO()).conversing is False
