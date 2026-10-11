"""The interpreter check: the pinned minor line runs, every other line and every unreadable pin is refused."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import python_pin  # noqa: E402


def pin_file(directory, text):
    path = Path(directory) / ".python-version"
    path.write_text(text, encoding="utf-8")
    return path


def run(path, running):
    """Return the exit status and what the check wrote to standard error."""
    stream = io.StringIO()
    with contextlib.redirect_stderr(stream):
        status = python_pin.main(path, running)
    return status, stream.getvalue()


class Pinned(unittest.TestCase):
    def test_full_version_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(python_pin.pinned(pin_file(directory, "3.14.8\n")), (3, 14, 8))

    def test_missing_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(python_pin.InterpreterError, "Cannot read"):
                python_pin.pinned(Path(directory) / ".python-version")

    def test_anything_but_one_full_version_is_refused(self):
        for text in ("", "3.14", "3.14.8.1", "3.14.x", "v3.14.8", "3.14.8\n3.13.1", "pypy3.11-7.3.19"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(python_pin.InterpreterError, "one full version"):
                    python_pin.pinned(pin_file(directory, text))


class Check(unittest.TestCase):
    def test_equal_version_passes_without_a_note(self):
        self.assertEqual(python_pin.check((3, 14, 8), (3, 14, 8, "final", 0)), "")

    def test_other_patch_level_passes_and_is_named(self):
        for running in ((3, 14, 0), (3, 14, 7), (3, 14, 9)):
            with self.subTest(running=running):
                self.assertEqual(
                    python_pin.check((3, 14, 8), running), f"python-pin: pin 3.14.8, running 3.14.{running[2]}"
                )

    def test_other_minor_or_major_line_is_refused(self):
        for running in ((3, 13, 8), (3, 15, 0), (2, 14, 8), (4, 14, 8)):
            with self.subTest(running=running):
                with self.assertRaisesRegex(python_pin.InterpreterError, r"pins the 3\.14 line"):
                    python_pin.check((3, 14, 8), running)


class Main(unittest.TestCase):
    def test_pinned_line_returns_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(run(pin_file(directory, "3.14.8\n"), (3, 14, 8)), (0, ""))

    def test_other_patch_level_returns_zero_and_says_so(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                run(pin_file(directory, "3.14.8\n"), (3, 14, 7)), (0, "python-pin: pin 3.14.8, running 3.14.7\n")
            )

    def test_other_line_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            status, output = run(pin_file(directory, "3.14.8\n"), (3, 13, 9))
        self.assertEqual(status, 2)
        self.assertIn("Python 3.13 is running; .python-version pins the 3.14 line", output)

    def test_unreadable_pin_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            status, output = run(pin_file(directory, "3.14\n"), (3, 14, 8))
        self.assertEqual(status, 2)
        self.assertIn("one full version", output)

    def test_repository_pin_matches_the_running_interpreter(self):
        self.assertEqual(run(python_pin.PIN_FILE, sys.version_info)[0], 0)


if __name__ == "__main__":
    unittest.main()
