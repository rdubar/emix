"""Assistance that teaches without altering authentic output."""

from __future__ import annotations

import io

import pytest

from emix.assist import Concept, concept_for, did_you_mean, explain, translation_hint
from emix.host import Drive, DriveSet
from emix.personalities.cms import CmsShell
from emix.personalities.cpm import CpmShell
from emix.personalities.vms import VmsShell

SHELLS = {"cpm": CpmShell, "vms": VmsShell, "cms": CmsShell}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "NOTES.TXT").write_text("hello\n")
    (tmp_path / "REPORT.TXT").write_text("hello\n")
    return tmp_path


def shell_for(key, root, *, strict=False, answers=""):
    drives = DriveSet([Drive.create("A", root)])
    return SHELLS[key](drives, stdin=io.StringIO(answers), stdout=io.StringIO(), strict=strict)


def run(shell, *lines):
    for line in lines:
        shell.execute(line)
    return shell.stdout.getvalue()


# -- the table ----------------------------------------------------------


def test_modern_habits_map_to_concepts():
    assert concept_for("ls") is Concept.LIST
    assert concept_for("RM") is Concept.DELETE
    assert concept_for("wibble") is None


def test_a_translation_names_the_real_command():
    hint = translation_hint("CP/M 2.2", "ls", {Concept.LIST: "DIR"})
    assert hint == "CP/M 2.2 has no ls. To list the files, use DIR."


def test_no_translation_is_offered_where_the_system_had_none():
    assert translation_hint("CP/M 2.2", "cd", {Concept.LIST: "DIR"}) is None


def test_a_command_is_not_suggested_as_a_replacement_for_itself():
    assert translation_hint("CP/M 2.2", "dir", {Concept.LIST: "DIR"}) is None


def test_near_misses_are_offered_and_nonsense_is_not():
    assert did_you_mean("DIRE", ["DIR", "ERA"]) == "Did you mean the command DIR?"
    assert did_you_mean("QQQQQQ", ["DIR", "ERA"]) is None


def test_explanations_pair_the_general_rule_with_the_local_one():
    lines = explain("SYNTAX", {"SYNTAX": "CP/M names its destination first."})
    assert len(lines) == 2
    assert lines[1] == "CP/M names its destination first."


# -- the rule that matters ----------------------------------------------


@pytest.mark.parametrize("key", sorted(SHELLS))
def test_the_authentic_error_is_printed_verbatim_before_any_hint(key, root):
    strict = run(shell_for(key, root, strict=True), "WIBBLE")
    assisted = run(shell_for(key, root, strict=False), "WIBBLE")

    assert assisted.startswith(strict)


@pytest.mark.parametrize("key", sorted(SHELLS))
def test_strict_mode_adds_absolutely_nothing(key, root):
    assert "Emix:" not in run(shell_for(key, root, strict=True), "ls", "cat NOTES.TXT", "NOSUCH")


@pytest.mark.parametrize("key", sorted(SHELLS))
def test_every_hint_is_marked_as_emix_speaking(key, root):
    rendered = run(shell_for(key, root, strict=False), "NOSUCHCOMMAND")

    for line in rendered.splitlines():
        assert "Did you mean" not in line or line.startswith("Emix:")


def test_a_hint_names_the_period_command(root):
    rendered = run(shell_for("vms", root, strict=False), "ls")

    assert "%DCL-W-IVVERB" in rendered
    assert "Emix: OpenVMS has no ls. To list the files, use DIRECTORY." in rendered


def test_a_mistyped_verb_gets_a_suggestion(root):
    assert "Did you mean the command DIRECTORY?" in run(
        shell_for("vms", root, strict=False), "DIRECTROY"
    )


def test_a_mistyped_filename_gets_a_suggestion(root):
    rendered = run(shell_for("cms", root, strict=False), "TYPE NOTEZ TXT A")

    assert "NOTES.TXT" in rendered


def test_scripts_are_strict_by_default(root):
    # Non-interactive input must not depend on a guess.
    drives = DriveSet([Drive.create("A", root)])
    shell = CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO())

    assert shell.strict is True


# -- the STRICT verb ----------------------------------------------------


def test_strict_can_be_turned_on_and_off_mid_session(root):
    shell = shell_for("vms", root, strict=False)

    rendered = run(shell, "STRICT ON", "ls", "STRICT OFF", "ls")

    assert rendered.count("Emix: OpenVMS has no ls") == 1


def test_strict_reports_its_own_state(root):
    assert "STRICT OFF" in run(shell_for("cpm", root, strict=False), "STRICT")


def test_strict_rejects_nonsense(root):
    shell = shell_for("cpm", root, strict=False)
    run(shell, "STRICT MAYBE")
    assert shell.strict is False


# -- EXPLAIN ------------------------------------------------------------


def test_explain_describes_the_previous_command_not_itself(root):
    rendered = run(shell_for("vms", root, strict=False), "DIRECTORY", "EXPLAIN")

    assert "You typed: DIRECTORY" in rendered
    assert "You typed: EXPLAIN" not in rendered


def test_explain_teaches_the_rule_behind_a_failure(root):
    rendered = run(shell_for("cpm", root, strict=False), "NOSUCH.TXT", "EXPLAIN")

    assert "Emix:" in rendered


def test_explain_before_anything_has_run_says_so(root):
    assert "Nothing has run yet" in run(shell_for("cpm", root, strict=False), "EXPLAIN")


def test_explain_covers_the_vms_version_rule(root):
    rendered = run(shell_for("vms", root, strict=False), "DELETE FOO.TXT", "EXPLAIN")

    assert "version" in rendered.lower()


# -- completion ---------------------------------------------------------


@pytest.mark.parametrize("key", sorted(SHELLS))
def test_completion_offers_verbs_on_the_first_word(key, root):
    shell = shell_for(key, root)

    assert shell.completions("TY", "TY") == ["TYPE"]


def test_completion_offers_file_names_after_the_verb(root):
    shell = shell_for("cpm", root)

    assert shell.completions("NOT", "TYPE NOT") == ["NOTES.TXT"]


def test_completion_offers_the_period_spelling(root):
    shell = shell_for("vms", root)

    assert "DIRECTORY" in shell.completions("DIR", "DIR")


def test_completion_never_raises_on_a_broken_drive(root):
    shell = shell_for("cpm", root)

    assert shell.completions("", "TYPE ") is not None


# -- colour -------------------------------------------------------------


def test_colour_is_off_when_output_is_not_a_terminal(root):
    shell = shell_for("cpm", root, strict=False)

    rendered = run(shell, "NOSUCHCOMMANDHERE")

    assert "\033[" not in rendered
    assert shell.hint_colour == "none"


def test_a_named_colour_wraps_the_hint(root):
    from emix.assist import colourise

    assert colourise("Emix: hi", "yellow") == "\033[33mEmix: hi\033[0m"
    assert colourise("Emix: hi", "none") == "Emix: hi"


def test_no_color_is_honoured(monkeypatch, root, tmp_path):
    monkeypatch.setenv("NO_COLOR", "1")
    drives = DriveSet([Drive.create("A", root)])

    shell = CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO(), hint_colour="cyan")

    assert shell.hint_colour == "none"


def test_an_unknown_colour_name_degrades_to_plain_text():
    from emix.assist import colourise

    assert colourise("x", "chartreuse") == "x"


# -- house casing -------------------------------------------------------


def test_cpm_folds_shared_emix_output_into_its_own_casing(root):
    rendered = run(shell_for("cpm", root, strict=False), "STRICT")

    assert "STRICT OFF" in rendered


def test_cpm_does_not_fold_a_web_address(root):
    rendered = run(shell_for("cpm", root, strict=False), "ABOUT")

    assert "https://github.com/rdubar/emix" in rendered
    assert "HISTORICAL COMPUTER PERSONALITIES" in rendered


def test_other_personalities_leave_shared_output_alone(root):
    rendered = run(shell_for("vms", root, strict=False), "ABOUT")

    assert "Historical computer personalities" in rendered


def test_hints_keep_their_own_case_even_where_the_system_shouts(root):
    """A hint is Emix's voice, so it should not look like CP/M's."""
    rendered = run(shell_for("cpm", root, strict=False), "DIRR")

    hints = [line for line in rendered.splitlines() if line.startswith("Emix:")]
    assert hints
    assert any(line != line.upper() for line in hints)


# -- painting Emix's own commands ---------------------------------------


def painted(key, root, line):
    """Run one line with colour forced on, and return what was written."""
    drives = DriveSet([Drive.create("A", root)])
    shell = SHELLS[key](
        drives, stdin=io.StringIO(), stdout=io.StringIO(), strict=False, hint_colour="yellow"
    )
    shell.hint_colour = "yellow"  # stdout is a StringIO, so force it back on
    shell.execute(line)
    return shell.stdout.getvalue()


@pytest.mark.parametrize("key", sorted(SHELLS))
def test_emix_only_commands_are_painted(key, root):
    assert "\033[33m" in painted(key, root, "ABOUT")


@pytest.mark.parametrize("key", sorted(SHELLS))
def test_period_commands_are_never_painted(key, root):
    assert "\033[" not in painted(key, root, "TYPE NOTES.TXT")


def test_cpm_paints_help_because_cpm_had_none(root):
    assert "\033[33m" in painted("cpm", root, "HELP")


def test_vms_does_not_paint_help_because_vms_had_it(root):
    assert "\033[" not in painted("vms", root, "HELP")


def test_cpm_treats_its_six_builtins_as_period_kit(root):
    drives = DriveSet([Drive.create("A", root)])
    shell = CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO())

    assert not shell.is_emix_verb("DIR")
    assert not shell.is_emix_verb("PIP")
    assert shell.is_emix_verb("ABOUT")
    assert shell.is_emix_verb("HELP")


def test_painting_is_off_entirely_without_colour(root):
    drives = DriveSet([Drive.create("A", root)])
    shell = CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO(), hint_colour="none")
    shell.execute("ABOUT")

    assert "\033[" not in shell.stdout.getvalue()


# -- applications that can never run ------------------------------------


def test_apps_says_when_a_profile_is_shadowed_by_a_command(monkeypatch, root):
    """Verbs beat applications, so a profile named TYPE would never fire."""
    from emix.apps.profiles import Profile

    shadowed = Profile(
        name="typewriter", backend="fake", program="TYPE.COM", application=root, command="TYPE"
    )
    monkeypatch.setattr("emix.apps.profiles.load", lambda path=None: {"typewriter": shadowed})

    rendered = run(shell_for("cpm", root, strict=False), "APPS")

    assert "SHADOWED" in rendered.upper()


# -- the review's assistance findings ------------------------------------


def test_every_physical_line_of_a_multiline_hint_is_marked(root):
    """H3: a continuation line must not look like the system speaking."""
    shell = shell_for("cms", root, strict=False)
    run(shell, "TYPE NOPE TXT A")
    before = shell.stdout.getvalue()
    run(shell, "EXPLAIN")
    explained = shell.stdout.getvalue()[len(before) :]

    # CMS renders its error as two lines, the second being Ready(nnnnn);.
    # Both are re-quoted by EXPLAIN, so both must carry the marker.
    body = [line for line in explained.splitlines() if line.strip()]
    assert any("Ready(" in line for line in body), explained
    for line in body:
        if not line.startswith("Ready;"):
            assert line.startswith("Emix:"), line


def test_a_failing_meta_command_does_not_steal_explains_subject(root):
    """H3: EXPLAIN described one command while diagnosing another."""
    rendered = run(shell_for("vms", root, strict=False), "NOPE", "STRICT MAYBE", "EXPLAIN")

    assert "You typed: NOPE" in rendered
    assert "no such command" in rendered.lower()
    assert "version" not in rendered.lower()


def test_explain_does_not_offer_advice_about_an_unrelated_command(root):
    rendered = run(shell_for("cpm", root, strict=False), "REN", "EXPLAIN")

    assert "destination first" in rendered


def test_no_color_prevents_the_terminal_probe_entirely(monkeypatch, root):
    """M1: probing a terminal whose answer we discard is pure noise."""
    monkeypatch.setenv("NO_COLOR", "1")
    probed = []
    monkeypatch.setattr("emix.shell.background_is_dark", lambda *a: probed.append(True) or True)

    shell = shell_for("cpm", root, strict=False)

    assert shell.hint_colour == "none"
    assert probed == []


def test_cpm_save_says_why_it_cannot_exist(root):
    """H4: claimed as one of the six built-ins, so it must answer for itself."""
    rendered = run(shell_for("cpm", root, strict=False), "SAVE 1 SNAP.COM")

    assert "NO TPA" in rendered.upper()


def test_explain_describes_a_line_that_could_not_even_be_parsed(root):
    """I5: the record has to exist before parsing, because parsing can fail."""
    rendered = run(shell_for("cpm", root, strict=False), 'TYPE "unterminated', "EXPLAIN")

    assert "You typed: TYPE" in rendered
    assert "Nothing has run yet" not in rendered


def test_a_parser_error_after_a_meta_command_still_explains_itself(root):
    """The sequence the review used: a failure, a meta command, then a parse error."""
    rendered = run(
        shell_for("cpm", root, strict=False), "NOPE", "STRICT", 'TYPE "unterminated', "EXPLAIN"
    )

    assert "You typed: TYPE" in rendered
    assert "You typed: NOPE" not in rendered


def test_a_parser_error_as_the_very_first_command_explains_itself(root):
    rendered = run(shell_for("cpm", root, strict=False), 'TYPE "unterminated', "EXPLAIN")

    assert "Nothing has run yet" not in rendered
