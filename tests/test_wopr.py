"""WOPR: the personality that cannot be historically inaccurate.

Every other personality is checked against a real machine. This one is checked
against a film, and against the promise that it stays honest about being an
invention while the files under it stay real.
"""

from __future__ import annotations

import io

import pytest

from emix.host import Drive, DriveSet
from emix.personalities import PERSONALITIES
from emix.personalities.wopr import GAMES, WoprShell


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


def test_a_game_nobody_has_heard_of_is_an_unknown_request(root):
    assert "I DO NOT UNDERSTAND" in run(wopr(root), "PLAY TIDDLYWINKS")


# -- honesty -------------------------------------------------------------


def test_the_banner_admits_what_this_is(root):
    """A prompt must be honest about what it is, invented ones most of all."""
    banner = wopr(root).banner().upper()

    assert "FICTIONAL" in banner
    assert "YOUR FILES ARE NOT" in banner


def test_wopr_does_not_fall_through_to_the_host(root):
    """A defence computer at NORAD does not run your shell commands."""
    assert WoprShell.host_fallthrough is False
    assert "I DO NOT UNDERSTAND" in run(wopr(root), "ls")


# -- the files under it are real -----------------------------------------


def test_files_are_listed_and_displayed(root):
    rendered = run(wopr(root), "LIST", "DISPLAY NOTES.TXT")

    assert "NOTES.TXT" in rendered
    assert "hello" in rendered


def test_a_missing_file_is_reported_in_its_own_words(root):
    assert "FILE NOT FOUND: NOSUCH.TXT" in run(wopr(root), "DISPLAY NOSUCH.TXT")


def test_copying_puts_the_destination_first(root):
    """WOPR is of CP/M's era, and PIP put the new name first."""
    run(wopr(root), "DUPLICATE COPY.TXT NOTES.TXT")

    assert (root / "COPY.TXT").read_text() == "hello\n"


def test_deleting_asks_first(root):
    """Destructive commands confirm, in every personality including this one."""
    shell = wopr(root, answers="N\n")

    run(shell, "PURGE NOTES.TXT")

    assert (root / "NOTES.TXT").exists()
    assert "NO FILES DELETED" in shell.stdout.getvalue()


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
