"""release-please-config.json sets no last-release-sha and a template-shaped PR body.

With last-release-sha set, the pinned release-helper check refuses every release PR head: the PR
raises the manifest version before its tag exists (CI run 41946879498 on release PR 72).
Release-please finds the last release from the manifest version's tag instead.

CodeRabbit flagged release PR 72: its body lacked the pull request template's "## Description"
and "## Pre-Merge Verification Checklist" sections. Release-please renders the body as
header, a "---" line, the notes, a "---" line and footer (release-please 17.6.0,
src/util/pull-request-body.ts), so the template headings go into pull-request-header and
pull-request-footer.
"""

import json
import unittest
from pathlib import Path

from test_catalog_pr_body import CI, TEMPLATE, validate_ci_claims, validate_pr_body

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "release-please-config.json"
FORBIDDEN = "last-release-sha"
NOTES_DELIMITER = "---"


def validate_release_please_config(text):
    """Refuse a config that sets last-release-sha at top level or in any package."""
    config = json.loads(text)
    if not isinstance(config, dict):
        raise TypeError("release-please-config.json is not an object")
    if FORBIDDEN in config:
        raise ValueError(f"release-please-config.json sets {FORBIDDEN}")
    packages = config.get("packages", {})
    if not isinstance(packages, dict):
        raise TypeError("release-please-config.json packages is not an object")
    for path, package in packages.items():
        if isinstance(package, dict) and FORBIDDEN in package:
            raise ValueError(f"release-please-config.json package {path!r} sets {FORBIDDEN}")
    return True


def validate_release_pr_body(text, template_text, ci_text):
    """Refuse a config whose release PR header and footer do not follow the PR template."""
    config = json.loads(text)
    if not isinstance(config, dict):
        raise TypeError("release-please-config.json is not an object")
    parts = []
    for key in ("pull-request-header", "pull-request-footer"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"release-please-config.json sets no {key}")
        if NOTES_DELIMITER in value.splitlines():
            raise ValueError(f"release-please-config.json {key} holds the notes delimiter line")
        parts.append(value.strip())
    body = "\n\n".join(parts)
    validate_pr_body(body, template_text)
    validate_ci_claims(parts[1], ci_text)
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
        with self.assertRaisesRegex(TypeError, "not an object"):
            validate_release_please_config("[]")

    def test_refuse_non_object_packages(self):
        with self.assertRaisesRegex(TypeError, "packages is not an object"):
            validate_release_please_config(json.dumps({"packages": ["."]}))



class ReleasePrBodyTests(unittest.TestCase):
    def setUp(self):
        self.template = TEMPLATE.read_text(encoding="utf-8")
        self.ci = CI.read_text(encoding="utf-8")
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def check(self, config):
        return validate_release_pr_body(json.dumps(config), self.template, self.ci)

    def test_repository_config_follows_template(self):
        self.assertTrue(self.check(self.config))

    def test_refuse_missing_header(self):
        config = dict(self.config)
        del config["pull-request-header"]
        with self.assertRaisesRegex(ValueError, "sets no pull-request-header"):
            self.check(config)

    def test_refuse_footer_without_checklist_heading(self):
        config = dict(self.config, **{"pull-request-footer": "- [x] The title follows Conventional Commits."})
        with self.assertRaisesRegex(ValueError, "lacks template heading"):
            self.check(config)

    def test_refuse_notes_delimiter_in_header(self):
        config = dict(self.config, **{"pull-request-header": "## Description\n---\nRelease."})
        with self.assertRaisesRegex(ValueError, "notes delimiter"):
            self.check(config)

    def test_refuse_footer_without_ci_job(self):
        footer = "## Pre-Merge Verification Checklist\n\n- [x] The title follows Conventional Commits."
        config = dict(self.config, **{"pull-request-footer": footer})
        with self.assertRaisesRegex(ValueError, "does not name CI job"):
            self.check(config)

    def test_boundary_blank_header_is_missing(self):
        config = dict(self.config, **{"pull-request-header": "   "})
        with self.assertRaisesRegex(ValueError, "sets no pull-request-header"):
            self.check(config)


if __name__ == "__main__":
    unittest.main()
