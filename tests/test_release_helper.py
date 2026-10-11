"""The pinned helper runner: one commit, read from the workflows, and nothing else ever runs."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import release_helper  # noqa: E402

FIRST = "a" * 40
SECOND = "b" * 40
IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false")


def uses(reference, target="actions/check"):
    return f"      - uses: jellysin/release-helper/{target}@{reference} # v1.2.0\n"


def workflows(directory, **files):
    for name, text in files.items():
        (Path(directory) / f"{name}.yml").write_text(text, encoding="utf-8")
    return Path(directory)


def helper(directory, body="import sys\nprint(' '.join(sys.argv[1:]))\nsys.exit(7)\n"):
    """Create a stand-in helper repository with one commit; return its commit."""
    path = Path(directory)
    (path / "tools.py").write_text(body, encoding="utf-8")
    for arguments in (("init", "--quiet"), ("add", "tools.py"), (*IDENTITY, "commit", "--quiet", "-m", "stand-in")):
        subprocess.run(["git", "-C", str(path), *arguments], check=True, timeout=20, capture_output=True)
    return release_helper.git(path, 20, "rev-parse", "HEAD")


class Pinned(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())

    def test_one_commit_in_every_reference_is_the_pin(self):
        reusable = uses(FIRST, ".github/workflows/release-please.yml")
        self.assertEqual(release_helper.pinned(workflows(self.directory, ci=uses(FIRST), release=reusable)), FIRST)

    def test_this_repository_pins_one_full_commit(self):
        self.assertRegex(release_helper.pinned(release_helper.WORKFLOWS), r"^[0-9a-f]{40}$")

    def test_two_commits_are_refused(self):
        with self.assertRaisesRegex(release_helper.PinError, "different release-helper commits"):
            release_helper.pinned(workflows(self.directory, ci=uses(FIRST), update=uses(SECOND, "actions/catalog")))

    def test_tag_and_short_commit_are_refused(self):
        for reference in ("v1.2.0", "main", FIRST[:39]):
            with self.subTest(reference=reference), self.assertRaisesRegex(release_helper.PinError, "not a full commit"):
                release_helper.pinned(workflows(self.directory, ci=uses(reference)))

    def test_no_reference_is_refused(self):
        with self.assertRaisesRegex(release_helper.PinError, "No workflow"):
            release_helper.pinned(workflows(self.directory, ci="jobs: {}\n"))

    def test_more_files_than_the_bound_are_refused(self):
        files = {f"w{number}": uses(FIRST) for number in range(release_helper.MAX_WORKFLOWS + 1)}
        with self.assertRaisesRegex(release_helper.PinError, "More than"):
            release_helper.pinned(workflows(self.directory, **files))


class Checkout(unittest.TestCase):
    def setUp(self):
        self.source = self.enterContext(tempfile.TemporaryDirectory())
        self.cache = self.enterContext(tempfile.TemporaryDirectory())
        self.pin = helper(self.source)

    def test_fetches_the_pin_once_and_reuses_it(self):
        first = release_helper.checkout(self.pin, self.cache, source=self.source)
        self.assertEqual(release_helper.git(first, 20, "rev-parse", "HEAD"), self.pin)
        self.assertEqual(release_helper.checkout(self.pin, self.cache, source="/nonexistent"), first)

    def test_unknown_commit_is_refused_and_leaves_no_checkout(self):
        with self.assertRaisesRegex(release_helper.PinError, "git fetch failed"):
            release_helper.checkout(FIRST, self.cache, source=self.source)
        self.assertFalse((Path(self.cache) / f"release-helper-{FIRST}").exists())

    def test_checkout_at_another_commit_is_refused(self):
        with self.assertRaisesRegex(release_helper.PinError, "the workflows pin " + FIRST):
            release_helper.verified(self.source, FIRST)

    def test_modified_checkout_is_refused(self):
        (Path(self.source) / "tools.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        with self.assertRaisesRegex(release_helper.PinError, "local changes"):
            release_helper.verified(self.source, self.pin)


class Main(unittest.TestCase):
    def setUp(self):
        self.source = self.enterContext(tempfile.TemporaryDirectory())
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.pin = helper(self.source)
        self.errors = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def run_main(self, reference, environment):
        pins = workflows(self.directory, ci=uses(reference))
        return release_helper.main(["check-policy"], workflows=pins, cache=self.directory, environment=environment)

    def test_returns_the_exit_status_of_the_pinned_helper(self):
        self.assertEqual(self.run_main(self.pin, {"RELEASE_HELPER": self.source}), 7)
        self.assertIn(f"release-helper: {self.pin} in {self.source}", self.errors.getvalue())

    def test_given_checkout_at_another_commit_runs_nothing(self):
        self.assertEqual(self.run_main(FIRST, {"RELEASE_HELPER": self.source}), 2)
        self.assertIn(f"the workflows pin {FIRST}", self.errors.getvalue())

    def test_tag_pin_runs_nothing(self):
        self.assertEqual(self.run_main("v1.2.0", {"RELEASE_HELPER": self.source}), 2)
        self.assertIn("not a full commit", self.errors.getvalue())


if __name__ == "__main__":
    unittest.main()
