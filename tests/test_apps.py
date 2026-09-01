"""Document sessions: aliasing, manifests, change detection, commit."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from conftest import ANY_EXECUTABLE, needs_symlinks, toml_path
from emix.apps.backends import (
    Disposition,
    FakeBackend,
    Launch,
    Result,
    RunCPMBackend,
    _write_submit,
)
from emix.apps.manifest import SCHEMA, ChangeKind, Manifest
from emix.apps.names import to_alias
from emix.apps.profiles import Profile
from emix.apps.runner import open_document, open_session
from emix.apps.session import DocumentSession, user_area_layout
from emix.errors import Code, EmixError
from emix.personalities.cpm import CpmShell


@pytest.fixture
def home(tmp_path):
    directory = tmp_path / "documents"
    directory.mkdir()
    return directory


@pytest.fixture
def document(home):
    path = home / "Meeting notes.txt"
    path.write_text("original\n")
    return path


def session_for(home, **kwargs):
    return DocumentSession.create(app="test", backend="fake", home=home, **kwargs)


# -- aliases ------------------------------------------------------------


def test_a_name_that_already_fits_is_only_case_folded():
    assert to_alias("notes.txt") == "NOTES.TXT"


def test_a_long_name_gets_a_reversible_suffix():
    assert to_alias("Meeting notes.txt") == "MEETIN_1.TXT"


def test_collisions_take_the_next_ordinal():
    assert to_alias("Meeting notes.txt", {"MEETIN_1.TXT"}) == "MEETIN_2.TXT"


def test_the_suffix_character_is_configurable_per_application():
    # TE rejects "~" when it re-parses the command tail; other programs want it.
    assert to_alias("Meeting notes.txt", suffix="~") == "MEETIN~1.TXT"


def test_characters_cpm_cannot_hold_are_folded_not_dropped():
    assert to_alias("a+b.txt") == "A_B.TXT"


def test_a_leading_dot_is_a_stem_not_an_extension():
    assert to_alias(".profile").startswith("_PROFI")


# -- manifest -----------------------------------------------------------


def test_the_manifest_round_trips(home, document):
    session = session_for(home)
    session.stage([document])
    written = session.write_manifest()

    reloaded = Manifest.read(session.root)

    assert reloaded.schema == SCHEMA
    assert reloaded.session_id == written.session_id
    assert reloaded.files[0].guest == "MEETIN_1.TXT"
    assert reloaded.files[0].host == str(document.resolve())


def test_an_unknown_manifest_schema_is_refused_rather_than_guessed(home, document):
    session = session_for(home)
    session.stage([document])
    session.write_manifest()
    path = session.root / "session.json"
    payload = json.loads(path.read_text())
    payload["schema"] = SCHEMA + 1
    path.write_text(json.dumps(payload))

    with pytest.raises(EmixError) as caught:
        Manifest.read(session.root)

    assert "schema" in caught.value.detail


def test_the_manifest_exists_before_any_guest_could_run(home, document):
    session = session_for(home)
    session.stage([document])
    session.write_manifest()

    assert (session.root / "session.json").is_file()


# -- staging and change detection --------------------------------------


def test_staging_copies_only_the_selected_document(home, document):
    (home / "private.txt").write_text("must not be exposed")
    session = session_for(home)
    session.stage([document])

    staged = list(session.drive_dir(session.DOCUMENT_DRIVE).iterdir())

    assert [path.name for path in staged] == ["MEETIN_1.TXT"]


def test_an_untouched_document_reports_no_pending_change(home, document):
    session = session_for(home)
    session.stage([document])
    session.write_manifest()

    assert DocumentSession.pending(session.changes()) == []


def test_an_edited_document_is_reported_as_modified(home, document):
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")

    changes = DocumentSession.pending(session.changes())

    assert [change.kind for change in changes] == [ChangeKind.MODIFIED]
    assert changes[0].host == document.resolve()


def test_a_file_the_guest_created_returns_beside_the_original(home, document):
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / "CHAPTER2.TXT").write_text("a second file\n")

    created = [c for c in session.changes() if c.kind is ChangeKind.CREATED]

    assert len(created) == 1
    assert created[0].host == home / "chapter2.txt"


def test_change_detection_uses_content_not_mtime(home, document):
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    staged = session.drive_dir(entry.drive) / entry.guest
    staged.touch()  # new mtime, identical bytes

    assert DocumentSession.pending(session.changes()) == []


# -- commit -------------------------------------------------------------


def test_commit_writes_the_edit_back_to_the_host(home, document):
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")

    written = session.commit(session.changes())

    assert written == [document.resolve()]
    assert document.read_text() == "edited\n"


def test_commit_refuses_when_the_host_file_moved_underneath_the_session(home, document):
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")
    document.write_text("somebody else got here first\n")

    with pytest.raises(EmixError) as caught:
        session.commit(session.changes())

    assert caught.value.code is Code.EXISTS
    assert document.read_text() == "somebody else got here first\n"


def test_a_conflict_commits_nothing_at_all(home, document):
    second = home / "Other document.txt"
    second.write_text("second\n")
    session = session_for(home)
    staged = session.stage([document, second])
    session.write_manifest()
    for entry in staged:
        (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")
    second.write_text("changed on the host\n")

    with pytest.raises(EmixError):
        session.commit(session.changes())

    # The unconflicted document must not have been half-applied.
    assert document.read_text() == "original\n"


def test_two_long_names_get_distinct_reversible_aliases(home, document):
    twin = home / "Meeting notes.text"
    twin.write_text("twin\n")
    session = session_for(home)

    staged = session.stage([document, twin])

    guests = [entry.guest for entry in staged]
    assert len(set(guests)) == 2
    assert {Path(entry.host).name for entry in staged} == {document.name, twin.name}


def test_discard_leaves_the_host_untouched(home, document):
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")

    session.discard()

    assert document.read_text() == "original\n"
    assert not session.root.exists()


# -- backends -----------------------------------------------------------


def test_a_submit_file_is_consumed_from_the_end(tmp_path):
    path = tmp_path / "$$$.SUB"
    _write_submit(path, ["B:", "A:TE.COM NOTES.TXT"])
    payload = path.read_bytes()

    assert len(payload) == 256
    # Records are written in reverse, because the CCP reads from the end:
    # the *last* record is the *first* command to run.
    assert payload[0] == len("A:TE.COM NOTES.TXT")
    assert payload[1:19] == b"A:TE.COM NOTES.TXT"
    assert payload[128] == 2
    assert payload[129:131] == b"B:"


def test_a_submit_command_too_long_for_a_record_is_refused(tmp_path):
    with pytest.raises(EmixError):
        _write_submit(tmp_path / "$$$.SUB", ["X" * 200])


def test_runcpm_reports_a_useful_error_when_it_is_not_installed(monkeypatch):
    monkeypatch.delenv(RunCPMBackend.ENVIRONMENT, raising=False)
    monkeypatch.setattr("emix.apps.backends.shutil.which", lambda _: None)

    with pytest.raises(EmixError) as caught:
        RunCPMBackend().check()

    assert RunCPMBackend.ENVIRONMENT in caught.value.detail


# -- the whole session --------------------------------------------------


def profile(tmp_path: Path) -> Profile:
    application = tmp_path / "app"
    application.mkdir(exist_ok=True)
    return Profile(
        name="test-editor",
        backend="fake",
        program="TE.COM",
        application=application,
    )


def test_a_full_session_stages_runs_and_commits(tmp_path, home, document, capsys):
    def edit(session: DocumentSession) -> None:
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / entry.guest).write_text("edited by the guest\n")

    backend = FakeBackend(mutate=edit)

    status = open_document(
        document, profile(tmp_path), backend=backend, assume_yes=True, stream=io.StringIO()
    )

    assert status == 0
    assert document.read_text() == "edited by the guest\n"
    assert backend.prepared == Launch(program="TE.COM", arguments=("MEETIN_1.TXT",))


def test_declining_the_prompt_leaves_the_host_alone(tmp_path, home, document, capsys):
    def edit(session: DocumentSession) -> None:
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")

    status = open_document(
        document,
        profile(tmp_path),
        backend=FakeBackend(mutate=edit),
        confirm=lambda _: "n",
        stream=io.StringIO(),
    )

    assert status == 0
    assert document.read_text() == "original\n"


# -- session end --------------------------------------------------------


def test_the_session_ends_when_the_application_exits(tmp_path):
    """A document session should not strand the user at a CP/M prompt."""
    application = tmp_path / "app"
    application.mkdir()
    (application / "EXIT.COM").write_bytes(b"\x00")
    session = DocumentSession.create(
        app="t", backend="runcpm", home=tmp_path, layout=user_area_layout
    )

    RunCPMBackend(ANY_EXECUTABLE).prepare(
        session, application, Launch(program="TE.COM", arguments=("NOTES.TXT",))
    )

    submit = (session.drive_dir(session.APPLICATION_DRIVE) / "$$$.SUB").read_bytes()
    assert b"A:EXIT.COM" in submit
    # Written in reverse, so the terminator is the first record.
    assert submit[1:11] == b"A:EXIT.COM"


def test_stay_leaves_the_user_at_the_guest_prompt(tmp_path):
    application = tmp_path / "app"
    application.mkdir()
    (application / "EXIT.COM").write_bytes(b"\x00")
    session = DocumentSession.create(
        app="t", backend="runcpm", home=tmp_path, layout=user_area_layout
    )

    RunCPMBackend(ANY_EXECUTABLE).prepare(
        session,
        application,
        Launch(program="TE.COM", arguments=("NOTES.TXT",), exit_after=False),
    )

    submit = (session.drive_dir(session.APPLICATION_DRIVE) / "$$$.SUB").read_bytes()
    assert b"EXIT.COM" not in submit


def test_an_application_drive_without_exit_still_works(tmp_path):
    application = tmp_path / "app"
    application.mkdir()
    session = DocumentSession.create(
        app="t", backend="runcpm", home=tmp_path, layout=user_area_layout
    )

    RunCPMBackend(ANY_EXECUTABLE).prepare(
        session, application, Launch(program="TE.COM", arguments=("NOTES.TXT",))
    )

    assert (session.drive_dir(session.APPLICATION_DRIVE) / "$$$.SUB").is_file()


# -- launching from inside a personality --------------------------------


@pytest.fixture
def installed(monkeypatch, tmp_path):
    """One configured application, backed by the fake emulator."""
    application = tmp_path / "app"
    application.mkdir()
    profile = Profile(
        name="test-editor",
        backend="fake",
        program="TE.COM",
        application=application,
        command="TE",
    )
    monkeypatch.setattr("emix.apps.profiles.load", lambda path=None: {"test-editor": profile})
    return profile


def cpm_shell(root, answers: str = "Y\n"):
    from emix.host import Drive, DriveSet

    drives = DriveSet([Drive.create("A", root)])
    return CpmShell(drives, stdin=io.StringIO(answers), stdout=io.StringIO())


def test_apps_lists_installed_applications(installed, home):
    shell = cpm_shell(home)

    shell.execute("APPS")

    assert "TE" in shell.stdout.getvalue()
    assert "TE.COM" in shell.stdout.getvalue()


def test_apps_says_so_when_nothing_is_configured(monkeypatch, home):
    monkeypatch.setattr("emix.apps.profiles.load", lambda path=None: {})
    shell = cpm_shell(home)

    shell.execute("APPS")

    assert "NO APPLICATIONS CONFIGURED" in shell.stdout.getvalue().upper()


def test_an_application_verb_opens_a_file_from_the_current_drive(installed, home, document):
    shell = cpm_shell(home)
    edited = []

    def edit(session):
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / entry.guest).write_text("edited in the app\n")
        edited.append(entry.guest)

    from emix.apps import runner

    original = runner.build_backend
    runner.build_backend = lambda profile: FakeBackend(mutate=edit)
    try:
        shell.execute('TE "Meeting notes.txt"')
    finally:
        runner.build_backend = original

    assert edited == ["MEETIN_1.TXT"]
    assert "MEETIN_1.TXT" in shell.stdout.getvalue()
    assert document.read_text() == "edited in the app\n"


@needs_symlinks
def test_an_application_cannot_reach_outside_the_drive(installed, home, tmp_path):
    """Application arguments go through DriveSet, like every other verb."""
    secret = tmp_path / "secret.txt"
    secret.write_text("must not be staged")
    (home / "escape.txt").symlink_to(secret)
    shell = cpm_shell(home)

    shell.execute("TE ESCAPE.TXT")

    assert "must not be staged" not in shell.stdout.getvalue()
    assert shell.stdout.getvalue().strip() != ""


def test_an_application_verb_wants_exactly_one_file(installed, home):
    shell = cpm_shell(home)

    shell.execute("TE ONE.TXT TWO.TXT")

    assert shell.stdout.getvalue().strip() != ""


# -- documents that do not exist yet ------------------------------------


def test_a_reserved_name_comes_home_when_the_guest_creates_it(home):
    session = session_for(home)
    entry = session.stage_new("Brand new notes.txt")
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("written in the app\n")

    changes = DocumentSession.pending(session.changes())

    assert [c.kind for c in changes] == [ChangeKind.CREATED]
    assert changes[0].host == home / "Brand new notes.txt"
    session.commit(changes)
    assert (home / "Brand new notes.txt").read_text() == "written in the app\n"


def test_a_reserved_name_the_guest_never_used_is_not_a_change(home):
    session = session_for(home)
    session.stage_new("unwritten.txt")
    session.write_manifest()

    assert DocumentSession.pending(session.changes()) == []
    assert not (home / "unwritten.txt").exists()


def test_a_reserved_name_refuses_to_clobber_a_file_that_appeared(home):
    session = session_for(home)
    entry = session.stage_new("appeared.txt")
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("from the guest\n")
    (home / "appeared.txt").write_text("somebody else made this\n")

    with pytest.raises(EmixError):
        session.commit(session.changes())

    assert (home / "appeared.txt").read_text() == "somebody else made this\n"


def test_a_new_document_keeps_a_reversible_alias(home):
    session = session_for(home)

    entry = session.stage_new("Meeting notes.txt")

    assert entry.guest == "MEETIN_1.TXT"
    assert entry.origin_digest is None


def test_an_application_opens_with_no_document_at_all(tmp_path, home, capsys):
    backend = FakeBackend()

    status = open_session(
        profile(tmp_path), home=home, backend=backend, assume_yes=True, stream=io.StringIO()
    )

    assert status == 0
    assert backend.prepared == Launch(program="TE.COM", arguments=())


def test_an_application_verb_accepts_a_file_that_does_not_exist(installed, home):
    shell = cpm_shell(home)

    def create(session):
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / entry.guest).write_text("brand new\n")

    from emix.apps import runner

    original = runner.build_backend
    runner.build_backend = lambda profile: FakeBackend(mutate=create)
    try:
        shell.execute("TE NEWFILE.TXT")
    finally:
        runner.build_backend = original

    assert (home / "NEWFILE.TXT").read_text() == "brand new\n"


def test_an_application_verb_needs_no_arguments_at_all(installed, home):
    shell = cpm_shell(home)
    from emix.apps import runner

    original = runner.build_backend
    runner.build_backend = lambda profile: FakeBackend()
    try:
        shell.execute("TE")
    finally:
        runner.build_backend = original

    assert "Empty workspace" in shell.stdout.getvalue()


def test_a_new_document_name_still_cannot_escape_the_drive(installed, home):
    shell = cpm_shell(home)

    shell.execute("TE ../escape.txt")

    assert not (home.parent / "escape.txt").exists()


# -- profile notes ------------------------------------------------------


def test_profile_notes_are_shown_before_the_application_starts(tmp_path, home, document):
    application = tmp_path / "app"
    application.mkdir()
    noted = Profile(
        name="test-editor",
        backend="fake",
        program="TE.COM",
        application=application,
        notes="Delete removes to the RIGHT; use ^H for the left.",
    )
    stream = io.StringIO()

    open_session(noted, document=document, backend=FakeBackend(), assume_yes=True, stream=stream)

    assert "Delete removes to the RIGHT" in stream.getvalue()


def test_a_profile_without_notes_stays_quiet(tmp_path, home, document):
    stream = io.StringIO()

    open_session(
        profile(tmp_path), document=document, backend=FakeBackend(), assume_yes=True, stream=stream
    )

    preamble = stream.getvalue().split("DOCUMENT SESSION COMPLETE")[0]
    assert "Preparing" in preamble
    # The note block is the only indented part of the preamble.
    assert not any(line.startswith("  ") for line in preamble.splitlines())


def test_notes_are_read_from_configuration(tmp_path):
    from emix.apps import profiles as module

    config = tmp_path / "apps.toml"
    config.write_text(
        '[app.x]\nbackend = "fake"\nprogram = "TE.COM"\n'
        f"application = {toml_path(tmp_path)}\n" + 'notes = "Use ^H to delete left."\n'
    )

    loaded = module.load(config)

    assert loaded["x"].notes == "Use ^H to delete left."
    assert loaded["x"].command == "TE"


# -- the application's own housekeeping ---------------------------------


def test_an_editor_backup_is_reported_but_not_committed(home, document):
    """TE writes TE.BKP on every save. It is not the user's document."""
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / "TE.BKP").write_text("the editor's copy\n")

    changes = session.changes()

    assert any(c.kind is ChangeKind.AUXILIARY for c in changes)
    assert DocumentSession.pending(changes) == []
    session.commit(changes)
    assert not (home / "te.bkp").exists()


def test_auxiliary_patterns_come_from_the_profile(home, document):
    session = session_for(home, auxiliary=("*.SCRATCH",))
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / "WORK.SCRATCH").write_text("x\n")
    (session.drive_dir(entry.drive) / "KEEP.BAK").write_text("y\n")

    kinds = {c.guest: c.kind for c in session.changes()}

    assert kinds["WORK.SCRATCH"] is ChangeKind.AUXILIARY
    # .BAK is only auxiliary because the default list says so.
    assert kinds["KEEP.BAK"] is ChangeKind.CREATED


def test_the_report_names_ignored_files_rather_than_hiding_them(tmp_path, home, document):
    def backup(session):
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / "TE.BKP").write_text("copy\n")

    stream = io.StringIO()
    open_session(
        profile(tmp_path),
        document=document,
        backend=FakeBackend(mutate=backup),
        assume_yes=True,
        stream=stream,
    )

    assert "IGNORED" in stream.getvalue()
    assert "TE.BKP" in stream.getvalue()


# -- resource ceiling and geometry --------------------------------------


def test_an_unattended_session_gets_a_ceiling(tmp_path, home, document, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO())  # not a terminal
    backend = FakeBackend()

    open_session(
        profile(tmp_path), document=document, backend=backend, assume_yes=True, stream=io.StringIO()
    )

    assert backend.timeout == 60.0


def test_a_timeout_is_reported_without_touching_the_host(tmp_path, home, document, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO())

    wedged = FakeBackend(result=Result(Disposition.TIMEOUT, detail="stopped after 60s"))

    stream = io.StringIO()
    status = open_session(
        profile(tmp_path), document=document, backend=wedged, assume_yes=True, stream=stream
    )

    assert status == 1
    assert "did not finish" in stream.getvalue()
    assert document.read_text() == "original\n"


def test_an_interrupt_writes_nothing_to_the_host(tmp_path, home, document):
    class Interrupted(FakeBackend):
        def run(self, session, *, timeout=None):
            raise KeyboardInterrupt

    stream = io.StringIO()
    status = open_session(
        profile(tmp_path), document=document, backend=Interrupted(), assume_yes=True, stream=stream
    )

    assert status == 130
    assert "Nothing has been written" in stream.getvalue()
    assert document.read_text() == "original\n"


def test_a_guest_that_fails_never_commits_what_it_wrote(tmp_path, home, document):
    """B2: partial output from a crashed program is not evidence of intent."""

    def half_write(session):
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / entry.guest).write_text("half a docum")

    stream = io.StringIO()
    status = open_session(
        profile(tmp_path),
        document=document,
        backend=FakeBackend(mutate=half_write, result=Result(Disposition.FAILED, status=7)),
        assume_yes=True,
        stream=stream,
    )

    assert status == 1
    assert document.read_text() == "original\n"
    assert "Workspace kept at" in stream.getvalue()


def test_a_non_zero_exit_is_a_failure_unless_the_profile_says_otherwise(tmp_path, home, document):
    stream = io.StringIO()
    status = open_session(
        profile(tmp_path),
        document=document,
        backend=FakeBackend(result=Result(Disposition.FAILED, status=3)),
        assume_yes=True,
        stream=stream,
    )

    assert status == 1
    assert "exit status" not in document.read_text()


def test_a_small_terminal_is_warned_about(tmp_path, home, document, monkeypatch):
    monkeypatch.setattr("os.get_terminal_size", lambda *a: os.terminal_size((40, 10)))
    stream = io.StringIO()

    open_session(
        profile(tmp_path), document=document, backend=FakeBackend(), assume_yes=True, stream=stream
    )

    assert "expects 80x24" in stream.getvalue()
    assert "40x10" in stream.getvalue()


def test_the_com_extension_is_stripped_from_the_launch_command(tmp_path):
    """The CCP appends .COM itself, and some programs refuse it spelled out."""
    application = tmp_path / "app"
    application.mkdir()
    session = DocumentSession.create(
        app="t", backend="runcpm", home=tmp_path, layout=user_area_layout
    )

    RunCPMBackend(ANY_EXECUTABLE).prepare(
        session, application, Launch(program="MBASIC.COM", arguments=())
    )

    submit = (session.drive_dir(session.APPLICATION_DRIVE) / "$$$.SUB").read_bytes()
    assert b"A:MBASIC\x00" in submit
    assert b"MBASIC.COM" not in submit


def test_an_empty_workspace_still_has_a_document_drive(tmp_path, home):
    backend = FakeBackend()

    open_session(
        profile(tmp_path), home=home, backend=backend, assume_yes=True, stream=io.StringIO()
    )

    # Nothing to assert about content; the drive simply must exist to select.
    assert backend.prepared == Launch(program="TE.COM", arguments=())


# -- the alias map ------------------------------------------------------


def test_an_alias_map_is_reversible():
    from emix.apps.names import AliasMap

    mapping = AliasMap(["pyproject.toml", "NOTES.TXT", "Meeting notes.txt"])

    assert mapping.alias("pyproject.toml") == "PYPROJ_1.TOM"
    assert mapping.host("PYPROJ_1.TOM") == "pyproject.toml"
    assert mapping.alias("NOTES.TXT") == "NOTES.TXT"


def test_an_alias_map_gives_two_similar_names_distinct_aliases():
    from emix.apps.names import AliasMap

    mapping = AliasMap(["meeting-notes.txt", "meeting notes.txt"])

    aliases = {mapping.alias(n) for n in ["meeting-notes.txt", "meeting notes.txt"]}
    assert len(aliases) == 2
    for alias in aliases:
        assert mapping.host(alias) in {"meeting-notes.txt", "meeting notes.txt"}


def test_an_alias_map_does_not_depend_on_input_order():
    from emix.apps.names import AliasMap

    forward = AliasMap(["a-long-name.txt", "b-long-name.txt"])
    backward = AliasMap(["b-long-name.txt", "a-long-name.txt"])

    assert forward.alias("a-long-name.txt") == backward.alias("a-long-name.txt")


def test_an_unknown_alias_maps_to_nothing():
    from emix.apps.names import AliasMap

    assert AliasMap(["notes.txt"]).host("NOSUCH_1.TXT") is None


# -- the review's blockers, as regressions ------------------------------


def test_a_host_edit_during_staging_is_detected_not_overwritten(home, document, monkeypatch):
    """B1: the manifest must describe the bytes the session actually holds."""
    import emix.apps.session as module

    real = module.shutil.copy2

    def racing_copy(source, destination):
        result = real(source, destination)
        Path(source).write_text("somebody else edited this\n")
        return result

    monkeypatch.setattr(module.shutil, "copy2", racing_copy)
    session = session_for(home)
    entry = session.stage([document])[0]
    monkeypatch.setattr(module.shutil, "copy2", real)
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("edited in the guest\n")

    assert session.conflicts(session.changes()), "the concurrent host edit must be a conflict"
    with pytest.raises(EmixError):
        session.commit(session.changes())
    assert document.read_text() == "somebody else edited this\n"


def test_a_failed_replacement_rolls_the_whole_commit_back(home, document, monkeypatch):
    """B3: a commit is all of it or none of it."""
    second = home / "Second document.txt"
    second.write_text("second original\n")
    session = session_for(home)
    staged = session.stage([document, second])
    session.write_manifest()
    for entry in staged:
        (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")

    calls = {"n": 0}
    real = DocumentSession._replace

    def failing(source, destination):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real(source, destination)

    monkeypatch.setattr(DocumentSession, "_replace", staticmethod(failing))

    with pytest.raises(EmixError) as caught:
        session.commit(session.changes())

    assert "rolled back" in caught.value.detail
    assert document.read_text() == "original\n"
    assert second.read_text() == "second original\n"


def test_a_rollback_also_removes_files_the_commit_created(home, document, monkeypatch):
    session = session_for(home)
    first = session.stage([document])[0]
    second = session.stage_new("brand-new.txt")
    session.write_manifest()
    (session.drive_dir(first.drive) / first.guest).write_text("edited\n")
    (session.drive_dir(second.drive) / second.guest).write_text("new\n")

    calls = {"n": 0}
    real = DocumentSession._replace

    def failing(source, destination):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real(source, destination)

    monkeypatch.setattr(DocumentSession, "_replace", staticmethod(failing))

    with pytest.raises(EmixError):
        session.commit(session.changes())

    assert document.read_text() == "original\n"
    assert not (home / "brand-new.txt").exists()


def test_a_deletion_by_the_guest_is_reported_and_not_applied(home, document):
    """H5: silence would let the user think nothing happened."""
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).unlink()

    changes = session.changes()

    assert [c.kind for c in changes] == [ChangeKind.DELETED]
    assert DocumentSession.pending(changes) == []
    session.commit(changes)
    assert document.read_text() == "original\n"


def test_a_profile_is_only_offered_to_its_own_personality(monkeypatch, home):
    """M4: a CP/M profile handed a DCL filespec would misbehave."""
    from emix.host import Drive, DriveSet
    from emix.personalities.vms import VmsShell

    cpm_only = Profile(
        name="te", backend="fake", program="TE.COM", application=home, command="TE", system="cpm"
    )
    monkeypatch.setattr("emix.apps.profiles.load", lambda path=None: {"te": cpm_only})
    drives = DriveSet([Drive.create("A", home)])

    assert "TE" in CpmShell(drives, stdin=io.StringIO(), stdout=io.StringIO()).applications()
    assert "TE" not in VmsShell(drives, stdin=io.StringIO(), stdout=io.StringIO()).applications()


def test_an_application_argument_uses_the_personality_filespec(installed, home, tmp_path):
    """B4: drive prefixes and aliases must reach the same file TYPE would."""
    from emix.host import Drive, DriveSet

    other = tmp_path / "second"
    other.mkdir()
    (other / "NOTES.TXT").write_text("on drive B\n")
    (home / "pyproject.toml").write_text("[project]\n")
    drives = DriveSet([Drive.create("A", home), Drive.create("B", other)])
    shell = CpmShell(drives, stdin=io.StringIO("N\n"), stdout=io.StringIO())

    assert shell.resolve_document("B:NOTES.TXT").host == other / "NOTES.TXT"
    assert shell.resolve_document("PYPROJ_1.TOM").host == home / "pyproject.toml"
    assert shell.resolve_document("BRANDNEW.TXT").new_name == "BRANDNEW.TXT"


# -- the implementation review's findings, as regressions ----------------


def _fail_nth_replace(monkeypatch, n):
    """Make the nth call to _replace fail, leaving earlier ones applied."""
    real = DocumentSession._replace
    calls = {"n": 0}

    def failing(source, destination):
        calls["n"] += 1
        if calls["n"] == n:
            raise OSError("replacement failed")
        return real(source, destination)

    monkeypatch.setattr(DocumentSession, "_replace", staticmethod(failing))
    return real


def test_a_failed_rollback_is_never_reported_as_a_successful_one(home, document, monkeypatch):
    """I1: the message must not claim an undo that did not happen."""
    second = home / "second.txt"
    second.write_text("second original\n")
    session = session_for(home)
    session.stage([document, second])
    session.write_manifest()
    for entry in session.manifest.files:
        (session.drive_dir(entry.drive) / entry.guest).write_text("guest edit\n")

    _fail_nth_replace(monkeypatch, 2)
    real_os_replace = os.replace

    def failing_restore(source, destination):
        # Match the rollback directory exactly: the pytest tmp_path contains
        # this test's own name, so a substring check matches everything.
        if Path(source).parent.name == "rollback":
            raise OSError("restoration failed")
        return real_os_replace(source, destination)

    monkeypatch.setattr(os, "replace", failing_restore)

    with pytest.raises(EmixError) as caught:
        session.commit(session.changes())

    detail = caught.value.detail
    assert "could not be fully undone" in detail
    assert "was rolled back" not in detail
    assert session.rollback is not None and not session.rollback.complete
    assert document.resolve() in session.rollback.unresolved
    assert session.rollback.backups, "the original must still be on disk"


def test_a_failed_commit_keeps_the_workspace_holding_its_rollback_copies(
    tmp_path, home, document, monkeypatch
):
    """I1: discarding the workspace destroys the only evidence."""

    def edit(session):
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")

    monkeypatch.setattr(
        DocumentSession,
        "commit",
        lambda self, changes: (_ for _ in ()).throw(EmixError(Code.IO_ERROR, "commit", "boom")),
    )
    stream = io.StringIO()

    status = open_session(
        profile(tmp_path),
        document=document,
        backend=FakeBackend(mutate=edit),
        assume_yes=True,
        stream=stream,
    )

    assert status == 1
    assert "Workspace kept at" in stream.getvalue()
    kept = Path(stream.getvalue().split("Workspace kept at:")[1].strip().splitlines()[0])
    assert kept.exists()


def test_an_unresolved_commit_names_the_files_and_their_originals(
    tmp_path, home, document, monkeypatch
):
    from emix.apps.session import RollbackOutcome

    def unresolved_commit(self, changes):
        self.rollback = RollbackOutcome(unresolved=(home / "doc.txt",), backups=(home / "keep",))
        raise EmixError(Code.IO_ERROR, "commit", "boom")

    monkeypatch.setattr(DocumentSession, "commit", unresolved_commit)

    def edit(session):
        entry = session.manifest.files[0]
        (session.drive_dir(entry.drive) / entry.guest).write_text("edited\n")

    stream = io.StringIO()

    open_session(
        profile(tmp_path),
        document=document,
        backend=FakeBackend(mutate=edit),
        assume_yes=True,
        stream=stream,
    )

    assert "UNRESOLVED" in stream.getvalue()
    assert "ORIGINAL AT" in stream.getvalue()


def test_a_host_edit_after_preflight_is_caught_before_the_write(home, document, monkeypatch):
    """I2: narrows the window between the conflict check and the replace."""
    import emix.apps.session as module

    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("guest edit\n")

    real_copy = module.shutil.copy2

    def racing_backup(source, destination):
        # The host changes after conflicts() cleared it and before the replace.
        Path(source).write_text("concurrent edit\n")
        return real_copy(source, destination)

    monkeypatch.setattr(module.shutil, "copy2", racing_backup)

    with pytest.raises(EmixError) as caught:
        session.commit(session.changes())

    assert "during the commit" in caught.value.detail
    assert document.read_text() == "concurrent edit\n"


def test_a_host_file_that_vanishes_after_preflight_is_caught(home, document, monkeypatch):
    session = session_for(home)
    entry = session.stage([document])[0]
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("guest edit\n")
    changes = session.changes()
    # Preflight catches a file already gone, so reaching the loop's own guard
    # means simulating a disappearance between the two.
    monkeypatch.setattr(DocumentSession, "conflicts", lambda self, pending: [])
    document.unlink()

    with pytest.raises(EmixError) as caught:
        session.commit(changes)

    assert "disappeared" in caught.value.detail


def test_a_reserved_name_that_appears_before_the_write_is_caught(home, monkeypatch):
    session = session_for(home)
    entry = session.stage_new("late.txt")
    session.write_manifest()
    (session.drive_dir(entry.drive) / entry.guest).write_text("from the guest\n")
    changes = session.changes()
    (home / "late.txt").write_text("somebody else got here\n")

    with pytest.raises(EmixError):
        session.commit(changes)

    assert (home / "late.txt").read_text() == "somebody else got here\n"


def test_an_optional_path_must_be_a_string(tmp_path):
    from emix.apps import profiles as module

    config = tmp_path / "apps.toml"
    config.write_text(
        f'[app.x]\nbackend="fake"\nprogram="T.COM"\napplication={toml_path(tmp_path)}\nexecutable=42\n'
    )

    with pytest.raises(EmixError) as caught:
        module.load(config)

    assert "executable" in caught.value.subject


def test_an_unknown_personality_is_refused(tmp_path):
    from emix.apps import profiles as module

    config = tmp_path / "apps.toml"
    config.write_text(
        f'[app.x]\nbackend="fake"\nprogram="T.COM"\napplication={toml_path(tmp_path)}\nsystem="cpn"\n'
    )

    with pytest.raises(EmixError) as caught:
        module.load(config)

    assert "cpn" in str(caught.value) or "unknown personality" in caught.value.detail
