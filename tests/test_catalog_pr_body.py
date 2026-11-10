"""The plugin repository bot pull request body follows the pull request template.

CodeRabbit flagged PR 67: the body lacked the template's "## Description" and
"## Pre-Merge Verification Checklist" headings, and its paragraph was hard-wrapped
(the forge renders every newline as a line break). CodeRabbit flagged PR 83: the
checklist claimed the dispatched CI run passes `make verify-all`, which ci.yml never runs.
"""

import re
import unittest
from pathlib import Path

from test_catalog_dispatch import workflow_contexts

ROOT = Path(__file__).resolve().parent.parent

WORKFLOW = ROOT / ".github" / "workflows" / "update-catalog.yml"
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
CODEQL = ROOT / ".github" / "workflows" / "codeql.yml"
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


def checklist_section(body):
    """Return text from '## Pre-Merge Verification Checklist' to the next '## ' heading or end."""
    lines = body.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## Pre-Merge Verification Checklist"):
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "".join(lines[start:end])


def validate_ci_claims(body, ci_text):
    """Refuse a body that omits a CI job name or claims CI runs `make verify-all`."""
    checklist = checklist_section(body)
    for name in JOB_NAME_RE.findall(ci_text):
        if name not in checklist:
            raise ValueError(f"pull request body does not name CI job {name!r} in the checklist")
    for line in body.splitlines():
        if "make verify-all" in line and "does not run `make verify-all`" not in line:
            raise ValueError("pull request body claims CI runs make verify-all")
    return True


def validate_codeql_claims(body, codeql_text):
    """Refuse a body that omits any check context reported by CodeQL."""
    checklist = checklist_section(body)
    for context in workflow_contexts(codeql_text):
        if context not in checklist:
            raise ValueError(f"pull request body does not name CodeQL context {context!r} in the checklist")
    return True


def validate_gate_claims(body):
    """Refuse a body that describes dispatched runs as gates or omits pull request gate claims."""
    checklist = checklist_section(body)
    if not checklist:
        raise ValueError("pull request body has no Pre-Merge Verification Checklist")
    for line in checklist.splitlines():
        if "dispatch" in line and "does not count toward the required checks" not in line:
            raise ValueError(f"checklist line describes a dispatched run as a required check: {line}")
    if "runs of this pull request pass" not in checklist:
        raise ValueError("checklist does not name the pull request runs as the gate")
    return True


class CatalogPrBodyTests(unittest.TestCase):
    def setUp(self):
        """Load the pull request template."""
        self.template = TEMPLATE.read_text(encoding="utf-8")

    def test_workflow_body_follows_template(self):
        """The workflow body follows all template headings and paragraph formatting."""
        body = extract_body(WORKFLOW.read_text(encoding="utf-8"))
        self.assertTrue(validate_pr_body(body, self.template))

    def test_refuse_missing_heading(self):
        """A pull request body missing a required heading is refused."""
        body = "## Description\n\nAdds versions.\n"
        with self.assertRaisesRegex(ValueError, "Pre-Merge Verification Checklist"):
            validate_pr_body(body, self.template)

    def test_refuse_hard_wrapped_paragraph(self):
        """A pull request body that hard-wraps a prose paragraph is refused."""
        body = (
            "## Description\n\nAdds published plugin versions after checking,\nsigned provenance.\n\n"
            "## Pre-Merge Verification Checklist\n\n- [ ] item\n"
        )
        with self.assertRaisesRegex(ValueError, "hard-wraps"):
            validate_pr_body(body, self.template)

    def test_workflow_body_names_ci_jobs(self):
        """The workflow body names every CI job in the checklist."""
        body = extract_body(WORKFLOW.read_text(encoding="utf-8"))
        self.assertTrue(validate_ci_claims(body, CI.read_text(encoding="utf-8")))

    def test_workflow_body_names_codeql_jobs(self):
        """The workflow body names every CodeQL check context."""
        body = extract_body(WORKFLOW.read_text(encoding="utf-8"))
        self.assertTrue(validate_codeql_claims(body, CODEQL.read_text(encoding="utf-8")))

    def test_workflow_body_gate_claims(self):
        """The workflow PR body passes gate claims validation."""
        body = extract_body(WORKFLOW.read_text(encoding="utf-8"))
        self.assertTrue(validate_gate_claims(body))

    def test_refuse_previous_checklist_line(self):
        """The previous checklist line describing dispatched runs as gates is refused."""
        previous = (
            "- [ ] The CI and CodeQL runs this workflow dispatches on this branch pass: "
            "the CI job (workflow lint, interpreter pin, repository tests, manifest and "
            "allowlist checks), server-check, scanners, governance (praetor), and the CodeQL "
            "jobs analyze (python) and analyze (actions); the required checks block the "
            "merge until they do. It does not run `make verify-all`, which stays a local check."
        )
        body = f"## Pre-Merge Verification Checklist\n\n{previous}\n"
        with self.assertRaisesRegex(
            ValueError, r"checklist line describes a dispatched run as a required check"
        ):
            validate_gate_claims(body)

    def test_refuse_checklist_without_pull_request_runs(self):
        """A checklist without the pull request runs phrase is refused."""
        body = "## Pre-Merge Verification Checklist\n\n- [ ] Other checks pass.\n"
        with self.assertRaisesRegex(
            ValueError, "checklist does not name the pull request runs as the gate"
        ):
            validate_gate_claims(body)

    def test_refuse_body_without_checklist_heading(self):
        """A body with no checklist heading is refused."""
        body = "## Description\n\nRuns tests.\n"
        with self.assertRaisesRegex(
            ValueError, "pull request body has no Pre-Merge Verification Checklist"
        ):
            validate_gate_claims(body)

    def test_boundary_dispatch_in_description_only_passes(self):
        """Dispatch named in Description only plus a valid checklist passes."""
        body = (
            "## Description\n\n"
            "This workflow explicitly dispatches CI on the branch.\n\n"
            "## Pre-Merge Verification Checklist\n\n"
            "- [ ] The CI and CodeQL runs of this pull request pass.\n"
        )
        self.assertTrue(validate_gate_claims(body))

    def test_refuse_missing_codeql_context(self):
        """A pull request body omitting a CodeQL matrix context is refused."""
        codeql_text = "jobs:\n  analyze:\n    strategy:\n      matrix:\n        language: [python, actions]\n"
        body = "## Pre-Merge Verification Checklist\n\n- [ ] analyze (python) passes.\n"
        with self.assertRaisesRegex(ValueError, "'analyze \\(actions\\)'"):
            validate_codeql_claims(body, codeql_text)

    def test_refuse_codeql_context_in_description_only(self):
        """CodeQL contexts named in Description but missing in the checklist are refused."""
        codeql_text = "jobs:\n  analyze:\n    strategy:\n      matrix:\n        language: [python, actions]\n"
        body = (
            "## Description\n\nRuns analyze (python) and analyze (actions).\n\n"
            "## Pre-Merge Verification Checklist\n\n- [ ] analyze (python) passes.\n"
        )
        with self.assertRaisesRegex(ValueError, "'analyze \\(actions\\)'"):
            validate_codeql_claims(body, codeql_text)

    def test_refuse_ci_verify_all_claim(self):
        """A pull request body claiming CI runs make verify-all is refused."""
        ci_text = "jobs:\n  checks:\n    name: CI\n"
        body = "## Pre-Merge Verification Checklist\n\n- [ ] CI and `make verify-all` pass in the dispatched CI run.\n"
        with self.assertRaisesRegex(ValueError, "claims CI runs make verify-all"):
            validate_ci_claims(body, ci_text)

    def test_refuse_missing_ci_job(self):
        """A pull request body omitting a CI job name is refused."""
        ci_text = "jobs:\n  checks:\n    name: CI\n  scan:\n    name: scanners\n"
        body = "## Pre-Merge Verification Checklist\n\n- [ ] CI passes.\n"
        with self.assertRaisesRegex(ValueError, "'scanners'"):
            validate_ci_claims(body, ci_text)

    def test_refuse_ci_job_in_description_only(self):
        """CI jobs named in Description but missing in the checklist are refused."""
        ci_text = "jobs:\n  checks:\n    name: CI\n  scan:\n    name: scanners\n"
        body = (
            "## Description\n\nRuns CI and scanners.\n\n"
            "## Pre-Merge Verification Checklist\n\n- [ ] CI passes.\n"
        )
        with self.assertRaisesRegex(ValueError, "'scanners'"):
            validate_ci_claims(body, ci_text)

    def test_boundary_later_heading_ends_checklist(self):
        """A heading after the checklist ends the section; names under later headings are refused."""
        ci_text = "jobs:\n  checks:\n    name: CI\n  scan:\n    name: scanners\n"
        body = (
            "## Pre-Merge Verification Checklist\n\n- [ ] CI passes.\n\n"
            "## Later\n\n- [ ] scanners passes.\n"
        )
        with self.assertRaisesRegex(ValueError, "'scanners'"):
            validate_ci_claims(body, ci_text)

    def test_boundary_ci_without_jobs(self):
        """A CI workflow without jobs passes job validation."""
        self.assertTrue(validate_ci_claims("Nothing to name.\n", "on: push\n"))

    def test_boundary_template_without_headings(self):
        """A template without headings passes body validation."""
        self.assertTrue(validate_pr_body("One line.\n", "no headings here\n"))

    def test_refuse_workflow_without_body(self):
        """A workflow text without a body block raises ValueError."""
        with self.assertRaisesRegex(ValueError, "no 'body"):
            extract_body("steps:\n  - run: true\n")


if __name__ == "__main__":
    unittest.main()
