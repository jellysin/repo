"""The manifest checks: published versions stay as they were, and every version's download answers."""

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import isolated_git  # noqa: E402

isolated_git.isolate()

import manifest_checks  # noqa: E402

GUID = "2034650d-a290-4a16-b195-89fb44cfb932"
URL = "https://github.com/jellysin/plugin-lastfm/releases/download/v{0}/plugin-lastfm-{0}.zip"
IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false")


def version(number, checksum="0" * 32):
    return {"version": number + ".0", "targetAbi": "12.0.0.0", "checksum": checksum, "sourceUrl": URL.format(number)}


def manifest(*numbers):
    return [{"guid": GUID, "name": "JellySin Last.fm", "versions": [version(number) for number in numbers]}]


class History(unittest.TestCase):
    # Positive: a new version and a new plugin keep every published version as it was.
    def test_additions_pass(self):
        head = manifest("1.1.0", "1.0.0") + [{"guid": "d0973630-1561-4f3a-b26e-664229e6043e", "versions": []}]
        self.assertEqual(manifest_checks.history_findings(manifest("1.0.0"), head), [])

    # Negative: a removed version and a rewritten checksum or download URL are each refused.
    def test_removed_or_rewritten_versions_are_refused(self):
        rewritten = manifest("1.0.0")
        rewritten[0]["versions"][0]["checksum"] = "1" * 32
        moved = manifest("1.0.0")
        moved[0]["versions"][0]["sourceUrl"] = URL.format("9.9.9")
        for head, word in ((manifest(), "removed"), ([], "removed"), (rewritten, "rewritten"), (moved, "rewritten")):
            with self.subTest(head=head):
                self.assertEqual(manifest_checks.history_findings(manifest("1.0.0"), head),
                                 [f"{GUID} 1.0.0.0 was published and is {word}"])

    # Boundary: an empty base publishes nothing, so any head passes; an unchanged manifest passes;
    # a duplicate version or a manifest that is no list of plugins cannot be compared.
    def test_edges(self):
        self.assertEqual(manifest_checks.history_findings([], manifest("1.0.0")), [])
        self.assertEqual(manifest_checks.history_findings(manifest("1.0.0"), copy.deepcopy(manifest("1.0.0"))), [])
        for broken in (manifest("1.0.0", "1.0.0"), {}, [{"versions": []}], [{"guid": GUID}], [{"guid": GUID, "versions": [{}]}]):
            with self.subTest(broken=broken), self.assertRaises(manifest_checks.ManifestError):
                manifest_checks.history_findings(broken, [])


class Releases(unittest.TestCase):
    # Positive: every download answers 200.
    def test_answering_downloads_pass(self):
        self.assertEqual(manifest_checks.release_findings(manifest("1.0.0", "1.1.0"), lambda url: 200), [])

    # Negative: a missing release (404), no answer, and a sourceUrl that is not https are refused.
    def test_missing_downloads_are_refused(self):
        answers = {URL.format("1.0.0"): 404, URL.format("1.1.0"): "no answer (timed out)"}
        findings = manifest_checks.release_findings(manifest("1.0.0", "1.1.0"), answers.get)
        self.assertEqual(findings, [f"{GUID} 1.0.0.0: {URL.format('1.0.0')} answers 404",
                                    f"{GUID} 1.1.0.0: {URL.format('1.1.0')} answers no answer (timed out)"])
        plain = manifest("1.0.0")
        plain[0]["versions"][0]["sourceUrl"] = "http://example.invalid/a.zip"
        self.assertEqual(len(manifest_checks.release_findings(plain, lambda url: 200)), 1)

    # Boundary: an empty manifest asks nothing.
    def test_edges(self):
        asked = []
        self.assertEqual(manifest_checks.release_findings([], asked.append), [])
        self.assertEqual(asked, [])


class Main(unittest.TestCase):
    """The command line against a git repository holding a published manifest."""

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.errors = self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.write(manifest("1.0.0"))
        for arguments in (("init", "--quiet"), ("add", "manifest.json"), (*IDENTITY, "commit", "--quiet", "-m", "base")):
            subprocess.run(["git", "-C", str(self.root), *arguments], check=True, timeout=20, capture_output=True)

    def write(self, value):
        (self.root / "manifest.json").write_text(json.dumps(value), encoding="utf-8")

    def test_history_passes_an_addition_and_refuses_a_removal(self):
        self.write(manifest("1.1.0", "1.0.0"))
        self.assertEqual(manifest_checks.main(["history", "HEAD"], root=self.root), 0)
        self.write(manifest())
        self.assertEqual(manifest_checks.main(["history", "HEAD"], root=self.root), 1)
        self.assertIn("was published and is removed", self.errors.getvalue())

    def test_releases_reports_each_missing_download(self):
        self.assertEqual(manifest_checks.main(["releases"], root=self.root, answer=lambda url: 404), 1)
        self.assertEqual(manifest_checks.main(["releases"], root=self.root, answer=lambda url: 200), 0)

    def test_unreadable_input_and_bad_usage_return_two(self):
        self.assertEqual(manifest_checks.main(["history", "no-such-ref"], root=self.root), 2)
        self.assertEqual(manifest_checks.main(["unknown"], root=self.root), 2)
        self.assertEqual(manifest_checks.main(["releases", "extra"], root=self.root), 2)
        (self.root / "manifest.json").write_text("{", encoding="utf-8")
        self.assertEqual(manifest_checks.main(["releases"], root=self.root), 2)
        self.assertIn("is not JSON", self.errors.getvalue())

    def test_repository_manifest_keeps_its_published_versions(self):
        self.assertEqual(manifest_checks.main(["history", "HEAD"], root=ROOT), 0)


if __name__ == "__main__":
    unittest.main()
