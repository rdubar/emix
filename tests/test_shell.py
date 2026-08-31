"""The shared engine: dispatch, abbreviation, host fallthrough, the loop."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from emix import __version__
from emix.errors import Code, EmixError
from emix.personalities.cpm import CpmShell
from emix.personalities.vms import VmsShell
from emix.shell import STOP, Shell, verb


class Toy(Shell):
    key = "toy"

    @verb("DELETE", summary="delete", min_abbrev=3)
    def do_delete(self, invocation):
        self.write("deleted\n")

    @verb("DELIVER", summary="deliver", min_abbrev=3)
    def do_deliver(self, invocation):
        self.write("delivered\n")

    @verb("DESCRIBE", summary="describe", min_abbrev=3)
    def do_describe(self, invocation):
        self.write("described\n")

    @verb("QUIT", summary="quit")
    def do_quit(self, invocation):
        return STOP


def toy(drives, script=""):
    output = io.StringIO()
    return Toy(drives, stdin=io.StringIO(script), stdout=output), output


def test_unambiguous_abbreviation_dispatches(drives):
    shell, output = toy(drives)
    shell.execute("DELE")
    assert output.getvalue() == "deleted\n"


def test_ambiguous_abbreviation_is_reported_not_guessed(drives):
    # DEL prefixes both DELETE and DELIVER, so it must not silently pick one.
    shell, _ = toy(drives)
    with pytest.raises(EmixError) as caught:
        shell.lookup("DEL")
    assert caught.value.code is Code.AMBIGUOUS_VERB


def test_exact_name_beats_a_longer_verb_it_prefixes(drives):
    class Overlap(Toy):
        @verb("DEL", summary="short", min_abbrev=3)
        def do_del(self, invocation):
            self.write("short\n")

    output = io.StringIO()
    shell = Overlap(drives, stdin=io.StringIO(), stdout=output)
    shell.execute("DEL")
    assert output.getvalue() == "short\n"


def test_verbs_are_inherited_from_base_personalities(drives):
    shell, _ = toy(drives)
    assert {found.name for found in shell.verbs} >= {
        "ABOUT",
        "CREDIT",
        "DELETE",
        "DELIVER",
        "QUIT",
    }


def test_about_identifies_version_and_active_personality(drives):
    shell, output = toy(drives)

    shell.execute("ABOUT")

    rendered = output.getvalue()
    assert f"Emix {__version__}" in rendered
    assert "Active personality: Emix (toy)" in rendered
    assert "github.com/rdubar/emix" in rendered


def test_credit_has_a_plural_alias(drives):
    shell, output = toy(drives)

    shell.execute("CREDITS")

    rendered = output.getvalue()
    assert "Roger Dubar" in rendered
    assert "MIT License" in rendered


def test_banner_is_written_once_per_session(drives):
    # Regression: the old CLI called cmd.cmdloop() in a retry loop, so every
    # Ctrl-C reprinted the whole banner.
    shell, output = toy(drives, script="QUIT\n")
    shell.run()
    assert output.getvalue().count(shell.banner()) == 1


def test_interrupt_does_not_restart_or_reprint_the_banner(drives):
    shell, output = toy(drives)
    replies = iter([KeyboardInterrupt(), "QUIT"])

    def read():
        value = next(replies)
        if isinstance(value, BaseException):
            raise value
        return value

    with patch.object(Toy, "read_line", side_effect=read):
        shell.run()

    rendered = output.getvalue()
    assert rendered.count(shell.banner()) == 1
    assert "^C" in rendered


def test_empty_lines_are_ignored(drives):
    shell, output = toy(drives)
    shell.execute("")
    shell.execute("   ")
    assert output.getvalue() == ""


def test_host_commands_receive_argv_and_never_a_shell(drives):
    shell, _ = toy(drives)
    shell.host_fallthrough = True
    with patch("emix.host.subprocess.run") as run:
        shell.execute('python3 -c "print(42)"')

    argv, kwargs = run.call_args
    assert argv[0] == ["python3", "-c", "print(42)"]
    assert kwargs["cwd"] == drives.default
    # No shell means no shell injection: operators stay literal arguments.
    assert "shell" not in kwargs


def test_shell_operators_are_passed_through_as_literal_arguments(drives):
    shell, _ = toy(drives)
    shell.host_fallthrough = True
    with patch("emix.host.subprocess.run") as run:
        shell.execute("echo hi > /etc/passwd")

    assert run.call_args[0][0] == ["echo", "hi", ">", "/etc/passwd"]


def test_personalities_without_fallthrough_reject_unknown_verbs(drives):
    shell, output = toy(drives)
    shell.host_fallthrough = False
    shell.execute("NOSUCHVERB")
    assert output.getvalue()


def test_unterminated_quote_is_a_syntax_error_not_a_traceback(drives):
    shell, output = toy(drives)
    shell.execute('TYPE "unclosed')
    assert output.getvalue()


def test_confirm_treats_anything_but_yes_as_no(drives):
    for answer, expected in [
        ("Y\n", True),
        ("y\n", True),
        ("YES\n", True),
        ("n\n", False),
        ("\n", False),
        ("", False),
    ]:
        shell, _ = toy(drives, script=answer)
        assert shell.confirm("? ") is expected


def test_qualifiers_are_parsed_off_the_verb(drives):
    shell = VmsShell(drives, stdin=io.StringIO(), stdout=io.StringIO())
    invocation = shell.parse("DIRECTORY/SIZE/DATE=OLD *.TXT")

    assert invocation.verb == "DIRECTORY"
    assert invocation.args == ["*.TXT"]
    assert invocation.has("SIZE")
    assert invocation.qualifier("DATE") == "OLD"


def test_cpm_does_not_accept_abbreviations(drives):
    # CP/M's CCP matched whole verbs only; only DCL abbreviates.
    shell = CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO())
    assert shell.lookup("DIRECT") is None
