"""The plugin repository bot pull request body follows the pull request template.

CodeRabbit flagged PR 67: the body lacked the template's "## Description" and
"## Pre-Merge Verification Checklist" headings, and its paragraph was hard-wrapped
(the forge renders every newline as a line break). CodeRabbit flagged PR 83: the
checklist claimed the dispatched CI run passes `make verify-all`, which ci.yml never runs.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "update-catalog.yml"
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
JOB_NAME_RE = re.compile(r"^    name: (.+)$", re.MULTILINE)
BODY_RE = re.compile(r"^(?P<indent>\s*)body: \|\n(?P<block>(?:(?P=indent)  .*\n|\n)+)", re.MULTILINE)
HEADING_RE = re.compile(r"^## .+$", re.MULTILINE)


def extract_body(workflow_text):
    """Return the create-pull-request body block, dedented."""
    match = BODY_RE.search(workflow_text)
    if not match:
        raise ValueError("update-catalog.yml has no 'body: |' block")
    width = len(match.group("indent")) + 2
    return "\n".join(line[width:] for line in match.group("block").splitlines())


def validate_pr_body(body, template_text):
    """Refuse a body without every template heading or with a hard-wrapped paragraph."""
    for heading in HEADING_RE.findall(template_text):
        if heading not in body.splitlines():
            raise ValueError(f"pull request body lacks template heading {heading!r}")
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        prose = [line for line in lines if not line.startswith(("#", "- ", "<!--"))]
        if len(prose) > 1:
            raise ValueError(f"pull request body hard-wraps a paragraph: {prose[0]!r}")
    return True


def validate_ci_claims(body, ci_text):
    """Refuse a body that omits a CI job name or claims CI runs `make verify-all`."""
    for name in JOB_NAME_RE.findall(ci_text):
        if name not in body:
            raise ValueError(f"pull request body does not name CI job {name!r}")
    for line in body.splitlines():
        if "make verify-all" in line and "does not run `make verify-all`" not in line:
            raise ValueError("pull request body claims CI runs make verify-all")
    return True


class CatalogPrBodyTests(unittest.TestCase):
    def setUp(self):
        self.template = TEMPLATE.read_text(encoding="utf-8")

    def test_workflow_body_follows_template(self):
        body = extract_body(WORKFLOW.read_text(encoding="utf-8"))
        self.assertTrue(validate_pr_body(body, self.template))

    def test_refuse_missing_heading(self):
        body = "## Description\n\nAdds versions.\n"
        with self.assertRaisesRegex(ValueError, "Pre-Merge Verification Checklist"):
            validate_pr_body(body, self.template)

    def test_refuse_hard_wrapped_paragraph(self):
        body = (
            "## Description\n\nAdds published plugin versions after checking,\nsigned provenance.\n\n"
            "## Pre-Merge Verification Checklist\n\n- [ ] item\n"
        )
        with self.assertRaisesRegex(ValueError, "hard-wraps"):
            validate_pr_body(body, self.template)

    def test_workflow_body_names_ci_jobs(self):
        body = extract_body(WORKFLOW.read_text(encoding="utf-8"))
        self.assertTrue(validate_ci_claims(body, CI.read_text(encoding="utf-8")))

    def test_refuse_ci_verify_all_claim(self):
        ci_text = "jobs:\n  checks:\n    name: CI\n"
        body = "- [ ] CI and `make verify-all` pass in the dispatched CI run.\n"
        with self.assertRaisesRegex(ValueError, "claims CI runs make verify-all"):
            validate_ci_claims(body, ci_text)

    def test_refuse_missing_ci_job(self):
        ci_text = "jobs:\n  checks:\n    name: CI\n  scan:\n    name: scanners\n"
        with self.assertRaisesRegex(ValueError, "'scanners'"):
            validate_ci_claims("- [ ] CI passes.\n", ci_text)

    def test_boundary_ci_without_jobs(self):
        self.assertTrue(validate_ci_claims("Nothing to name.\n", "on: push\n"))

    def test_boundary_template_without_headings(self):
        self.assertTrue(validate_pr_body("One line.\n", "no headings here\n"))

    def test_refuse_workflow_without_body(self):
        with self.assertRaisesRegex(ValueError, "no 'body"):
            extract_body("steps:\n  - run: true\n")


if __name__ == "__main__":
    unittest.main()
