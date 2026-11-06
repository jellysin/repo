"""The plugin repository bot pull request body follows the pull request template.

CodeRabbit flagged PR 67: the body lacked the template's "## Description" and
"## Pre-Merge Verification Checklist" headings, and its paragraph was hard-wrapped
(the forge renders every newline as a line break).
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "update-catalog.yml"
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
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

    def test_boundary_template_without_headings(self):
        self.assertTrue(validate_pr_body("One line.\n", "no headings here\n"))

    def test_refuse_workflow_without_body(self):
        with self.assertRaisesRegex(ValueError, "no 'body"):
            extract_body("steps:\n  - run: true\n")


if __name__ == "__main__":
    unittest.main()
