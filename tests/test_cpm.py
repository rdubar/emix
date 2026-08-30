from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from emix.cpm import CpmShell


class CpmShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output = io.StringIO()
        self.input = io.StringIO()
        self.shell = CpmShell(self.root, stdin=self.input, stdout=self.output)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_dir_is_case_insensitive_and_uses_uppercase_presentation(self) -> None:
        (self.root / "ReadMe.txt").write_text("hello\n")

        self.shell.onecmd("dir *.txt")

        rendered = self.output.getvalue()
        self.assertIn("README.TXT", rendered)
        self.assertIn("1 FILE(S)", rendered)

    def test_type_finds_host_filename_without_case_sensitivity(self) -> None:
        (self.root / "ReadMe.txt").write_text("Hello from Unix\n")

        self.shell.onecmd("type README.TXT")

        self.assertEqual(self.output.getvalue(), "Hello from Unix\n")

    def test_copy_and_cpm_order_rename(self) -> None:
        (self.root / "old.txt").write_text("data")

        self.shell.onecmd("copy OLD.TXT copy.txt")
        self.shell.onecmd("ren NEW.TXT=COPY.TXT")

        self.assertEqual((self.root / "NEW.TXT").read_text(), "data")
        self.assertFalse((self.root / "copy.txt").exists())

    def test_erase_requires_confirmation(self) -> None:
        doomed = self.root / "scratch.txt"
        doomed.write_text("temporary")
        self.shell.stdin = io.StringIO("Y\n")

        self.shell.onecmd("era SCRATCH.TXT")

        self.assertFalse(doomed.exists())
        self.assertIn("1 FILE(S) ERASED", self.output.getvalue())

    def test_file_commands_cannot_escape_drive_root(self) -> None:
        self.shell.onecmd("type ../secret.txt")

        self.assertEqual(self.output.getvalue(), "BAD FILE NAME\n")

    @patch("emix.cpm.subprocess.run")
    def test_unknown_command_passes_arguments_to_host_without_shell(self, run) -> None:
        self.shell.onecmd('python3 -c "print(42)"')

        run.assert_called_once_with(
            ["python3", "-c", "print(42)"], cwd=self.shell.root, check=False
        )

    def test_unknown_executable_gets_cpm_style_error(self) -> None:
        with patch("emix.cpm.subprocess.run", side_effect=FileNotFoundError):
            self.shell.onecmd("missing-command")

        self.assertEqual(self.output.getvalue(), "MISSING-COMMAND?\n")


if __name__ == "__main__":
    unittest.main()
