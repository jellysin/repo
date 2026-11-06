"""release-please-config.json sets no last-release-sha.

With the key set, the pinned release-helper check refuses every release PR head: the PR raises
the manifest version before its tag exists (CI run 41946879498 on release PR 72). Release-please
finds the last release from the manifest version's tag instead.
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "release-please-config.json"
FORBIDDEN = "last-release-sha"


def validate_release_please_config(text):
    """Refuse a config that sets last-release-sha at top level or in any package."""
    config = json.loads(text)
    if not isinstance(config, dict):
        raise ValueError("release-please-config.json is not an object")
    if FORBIDDEN in config:
        raise ValueError(f"release-please-config.json sets {FORBIDDEN}")
    packages = config.get("packages", {})
    if not isinstance(packages, dict):
        raise ValueError("release-please-config.json packages is not an object")
    for path, package in packages.items():
        if isinstance(package, dict) and FORBIDDEN in package:
            raise ValueError(f"release-please-config.json package {path!r} sets {FORBIDDEN}")
    return True


class ReleasePleaseConfigTests(unittest.TestCase):
    def test_repository_config_sets_no_last_release_sha(self):
        self.assertTrue(validate_release_please_config(CONFIG.read_text(encoding="utf-8")))

    def test_refuse_top_level_last_release_sha(self):
        text = json.dumps({FORBIDDEN: "7091eef3c4b24215cc621f3a0ac5485507ac6e57", "packages": {".": {}}})
        with self.assertRaisesRegex(ValueError, "sets last-release-sha"):
            validate_release_please_config(text)

    def test_refuse_package_last_release_sha(self):
        text = json.dumps({"packages": {".": {FORBIDDEN: "7091eef3c4b24215cc621f3a0ac5485507ac6e57"}}})
        with self.assertRaisesRegex(ValueError, "package '.' sets last-release-sha"):
            validate_release_please_config(text)

    def test_boundary_config_without_packages(self):
        self.assertTrue(validate_release_please_config(json.dumps({"release-type": "simple"})))

    def test_refuse_non_object_config(self):
        with self.assertRaisesRegex(ValueError, "not an object"):
            validate_release_please_config("[]")


if __name__ == "__main__":
    unittest.main()
