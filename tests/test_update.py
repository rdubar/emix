"""Updating Emix itself: the right command for the way it was installed."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from emix.update import DISTRIBUTION, Installation, Method, detect, latest_version, update


@pytest.fixture
def checkout(tmp_path):
    """A source tree shaped like the repository."""
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    package = tmp_path / "src" / "emix"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    return tmp_path


def installed_at(prefix: str) -> Installation:
    return detect(
        module_file="/opt/venv/lib/python3.12/site-packages/emix/__init__.py", prefix=prefix
    )


# -- detection ----------------------------------------------------------


def test_a_uv_tool_install_is_upgraded_with_uv():
    found = installed_at("/home/x/.local/share/uv/tools/emix-shell")

    assert found.method is Method.UV_TOOL
    assert found.command == ("uv", "tool", "upgrade", DISTRIBUTION)


def test_a_pipx_install_is_upgraded_with_pipx():
    found = installed_at("/home/x/.local/pipx/venvs/emix-shell")

    assert found.method is Method.PIPX
    assert found.command[:2] == ("pipx", "upgrade")


def test_anything_else_falls_back_to_pip():
    found = installed_at("/usr/local")

    assert found.method is Method.PIP
    assert found.command[1:] == ("-m", "pip", "install", "--upgrade", DISTRIBUTION)


def test_a_source_checkout_is_recognised_by_its_layout(checkout):
    """An editable install points here too, and git is what updates it."""
    found = detect(module_file=str(checkout / "src" / "emix" / "__init__.py"), prefix="/anywhere")

    assert found.method is Method.SOURCE
    assert found.command == ()
    assert found.location == checkout


def test_a_package_merely_living_in_a_src_directory_is_not_a_checkout(tmp_path):
    package = tmp_path / "src" / "emix"
    package.mkdir(parents=True)

    found = detect(module_file=str(package / "__init__.py"), prefix="/usr/local")

    assert found.method is not Method.SOURCE


# -- what it tells the user ---------------------------------------------


def test_a_checkout_is_told_to_pull_rather_than_reinstall(checkout, monkeypatch):
    monkeypatch.setattr(
        "emix.update.detect", lambda *a, **k: Installation(Method.SOURCE, (), checkout)
    )
    stream = io.StringIO()

    assert update(stream=stream, check=False) == 0
    assert "git -C" in stream.getvalue()
    assert str(checkout) in stream.getvalue()


def test_the_command_is_shown_before_anything_runs(monkeypatch):
    """Nothing is executed on a guess, including an update of Emix itself."""
    monkeypatch.setattr(
        "emix.update.detect",
        lambda *a, **k: Installation(Method.UV_TOOL, ("uv", "tool", "upgrade"), Path("/x")),
    )
    ran = []
    stream = io.StringIO()

    update(
        stream=stream,
        check=False,
        confirm=lambda _: "n",
        runner=lambda argv, cwd: ran.append(argv) or 0,
    )

    assert "uv tool upgrade" in stream.getvalue()
    assert ran == [], "declining must not run anything"
    assert "Not updated" in stream.getvalue()


def test_confirming_runs_exactly_the_command_it_showed(monkeypatch):
    monkeypatch.setattr(
        "emix.update.detect",
        lambda *a, **k: Installation(Method.PIPX, ("pipx", "upgrade", DISTRIBUTION), Path("/x")),
    )
    ran = []

    status = update(
        stream=io.StringIO(),
        check=False,
        confirm=lambda _: "y",
        runner=lambda argv, cwd: ran.append(argv) or 0,
    )

    assert status == 0
    assert ran == [["pipx", "upgrade", DISTRIBUTION]]


def test_an_interrupt_at_the_prompt_updates_nothing(monkeypatch):
    monkeypatch.setattr(
        "emix.update.detect",
        lambda *a, **k: Installation(Method.PIP, ("pip", "install"), Path("/x")),
    )
    ran = []

    def interrupt(_):
        raise KeyboardInterrupt

    update(
        stream=io.StringIO(),
        check=False,
        confirm=interrupt,
        runner=lambda argv, cwd: ran.append(argv) or 0,
    )

    assert ran == []


def test_an_unreachable_index_is_reported_not_guessed(monkeypatch):
    monkeypatch.setattr("emix.update.latest_version", lambda *a, **k: None)
    monkeypatch.setattr(
        "emix.update.detect", lambda *a, **k: Installation(Method.SOURCE, (), Path("/x"))
    )
    stream = io.StringIO()

    update(stream=stream, check=True)

    assert "Could not reach the package index" in stream.getvalue()


def test_a_newer_published_version_is_named(monkeypatch):
    monkeypatch.setattr("emix.update.latest_version", lambda *a, **k: "9.9.9")
    monkeypatch.setattr(
        "emix.update.detect", lambda *a, **k: Installation(Method.SOURCE, (), Path("/x"))
    )
    stream = io.StringIO()

    update(stream=stream, check=True)

    assert "9.9.9" in stream.getvalue()


def test_the_index_check_never_raises(monkeypatch):
    """Offline, proxied and rate-limited hosts must all just say nothing."""

    def explode(*_args, **_kwargs):
        raise OSError("no network")

    monkeypatch.setattr("emix.update.urllib.request.urlopen", explode)

    assert latest_version(timeout=0.01) is None
