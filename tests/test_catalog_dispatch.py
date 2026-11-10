"""Workflows reporting required status checks run on pull_request.

Catalog bot PR 67 waited for approval of its held pull_request runs; dispatched
runs never count toward required checks. The ci.yml dispatch stays an early
signal, once per head commit because a second run cancels the first.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULESET = ROOT / ".github" / "rulesets" / "main.json"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
CI = WORKFLOWS_DIR / "ci.yml"
CODEQL = WORKFLOWS_DIR / "codeql.yml"
CATALOG = WORKFLOWS_DIR / "update-catalog.yml"


def required_contexts(ruleset_text):
    """Return the context strings of the required_status_checks rule in the ruleset JSON."""
    data = json.loads(ruleset_text)
    contexts = []
    for rule in data.get("rules", []):
        if rule.get("type") == "required_status_checks":
            for check in rule.get("parameters", {}).get("required_status_checks", []):
                contexts.append(check["context"])
    return contexts


def matrix_lines(job_body, matrix_line_match):
    """Return the non-blank, non-comment lines indented under a job's bare 'matrix:' line."""
    matrix_indent = len(matrix_line_match.group(0)) - len(matrix_line_match.group(0).lstrip())
    lines = []
    for line in job_body[matrix_line_match.end():].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= matrix_indent:
            break
        lines.append(line)
    return lines


def matrix_values(job_id, job_body):
    """Return a job's matrix values, or None without a matrix; raise ValueError naming the job for any other shape.

    Only one axis written as an inline list under a bare 'matrix:' line is read.
    """
    matrix_line_match = re.search(r"^[ \t]+matrix:[ \t]*(.*)$", job_body, re.MULTILINE)
    if not matrix_line_match:
        return None
    rest = matrix_line_match.group(1).strip()
    if rest:
        raise ValueError(f"job {job_id!r} matrix must be a bare 'matrix:' line, got {rest!r}")
    lines = matrix_lines(job_body, matrix_line_match)
    if len(lines) != 1:
        raise ValueError(f"job {job_id!r} matrix must hold exactly one axis as an inline list, got {len(lines)} lines")
    axis_match = re.match(r"^[ \t]*([a-zA-Z0-9_-]+):[ \t]*\[(.*?)\][ \t]*$", lines[0])
    if not axis_match:
        raise ValueError(f"job {job_id!r} matrix axis must be an inline list: {lines[0].strip()!r}")
    axis_key = axis_match.group(1)
    if axis_key in ("include", "exclude"):
        raise ValueError(f"job {job_id!r} matrix cannot use {axis_key!r} axis")
    values = [v.strip().strip("'\"") for v in axis_match.group(2).split(",") if v.strip()]
    if not values:
        raise ValueError(f"job {job_id!r} matrix axis {axis_key!r} has empty list")
    return values


def workflow_contexts(workflow_text):
    """Return the status check contexts reported by a workflow's jobs; raise ValueError on an unreadable matrix."""
    jobs_match = re.search(r"^jobs:\s*\n(.*)", workflow_text, re.MULTILINE | re.DOTALL)
    if not jobs_match:
        return []
    jobs_text = jobs_match.group(1)
    job_splits = list(re.finditer(r"^  ([a-zA-Z0-9_-]+):\s*$", jobs_text, re.MULTILINE))
    contexts = []
    for i, match in enumerate(job_splits):
        job_id = match.group(1)
        end = job_splits[i + 1].start() if i + 1 < len(job_splits) else len(jobs_text)
        job_body = jobs_text[match.end():end]
        name_match = re.search(r"^    name:[ \t]*(.+)$", job_body, re.MULTILINE)
        base_name = name_match.group(1).strip() if name_match else job_id
        values = matrix_values(job_id, job_body)
        if values is None:
            contexts.append(base_name)
        else:
            contexts.extend(f"{base_name} ({val})" for val in values)
    return contexts


def validate_required_checks(ruleset_text, workflows, catalog_text):
    """Refuse if any required check lacks pull_request or catalog dispatches invalid workflows."""
    required = required_contexts(ruleset_text)
    if not required:
        return True
    contexts_by_file = {}
    set_aside = {}
    for fname, text in workflows.items():
        try:
            contexts_by_file[fname] = workflow_contexts(text)
        except ValueError as err:
            set_aside[fname] = str(err)

    required_workflows = {}
    for context in required:
        matching = [fname for fname, ctxs in contexts_by_file.items() if context in ctxs]
        if not matching:
            msg = f"no workflow reports required status check context {context!r}"
            if set_aside:
                details = "; ".join(f"{fname}: {reason}" for fname, reason in sorted(set_aside.items()))
                msg += f" (set aside: {details})"
            raise ValueError(msg)
        for fname in matching:
            if fname not in required_workflows:
                required_workflows[fname] = context

    for fname in sorted(required_workflows):
        wtext = workflows[fname]
        context = required_workflows[fname]
        on_match = re.search(r"^on:\s*(.*?)(?=^[a-z-]+:|\Z)", wtext, re.MULTILINE | re.DOTALL)
        if not on_match or not re.search(r"^\s*pull_request:", on_match.group(1), re.MULTILINE):
            raise ValueError(f"{fname} reports required check {context!r} but does not run on pull_request")

    for match in re.finditer(r"\bgh\s+workflow\s+run\s+([^\s]+)", catalog_text):
        name = match.group(1)
        if name != "ci.yml":
            raise ValueError(
                f"catalog workflow dispatches {name}; only ci.yml is dispatched, and dispatched runs never count toward required checks"
            )

    pattern = rf"\bgh\s+workflow\s+run\s+{re.escape('ci.yml')}\b.*--ref\s+automation/repository"
    if not re.search(pattern, catalog_text, re.MULTILINE):
        raise ValueError("catalog workflow does not dispatch ci.yml")

    runs_pattern = rf"actions/workflows/{re.escape('ci.yml')}/runs\?event=workflow_dispatch&head_sha="
    if not re.search(runs_pattern, catalog_text):
        raise ValueError(
            "catalog workflow dispatches ci.yml without checking for a dispatched run of the head commit"
        )
    return True


class CatalogDispatchTests(unittest.TestCase):
    def setUp(self):
        """Load the repository ruleset, every workflow definition, and the catalog workflow text."""
        self.ruleset = RULESET.read_text(encoding="utf-8")
        self.ci_text = CI.read_text(encoding="utf-8")
        self.codeql_text = CODEQL.read_text(encoding="utf-8")
        self.catalog_text = CATALOG.read_text(encoding="utf-8")
        self.workflows = {path.name: path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS_DIR.glob("*.yml"))}

    def test_repository_files_pass(self):
        """Repository ruleset, workflows, and catalog dispatch pass validation."""
        self.assertTrue(validate_required_checks(self.ruleset, self.workflows, self.catalog_text))

    def test_refuse_catalog_with_codeql_dispatch(self):
        """A catalog workflow dispatching codeql.yml is refused naming codeql.yml."""
        planted = (
            self.catalog_text
            + '\n          gh workflow run codeql.yml --repo "$GITHUB_REPOSITORY" --ref automation/repository\n'
        )
        with self.assertRaisesRegex(ValueError, r"^catalog workflow dispatches codeql\.yml; only ci\.yml is dispatched"):
            validate_required_checks(self.ruleset, self.workflows, planted)

    def test_refuse_codeql_without_pull_request(self):
        """A workflow reporting required checks that lacks pull_request is refused."""
        planted_codeql = "\n".join(
            line for line in self.codeql_text.splitlines() if "pull_request:" not in line
        )
        workflows = dict(self.workflows, **{"codeql.yml": planted_codeql})
        with self.assertRaisesRegex(
            ValueError, r"codeql\.yml reports required check.*does not run on pull_request"
        ):
            validate_required_checks(self.ruleset, workflows, self.catalog_text)

    def test_refuse_codeql_with_pull_request_target(self):
        """A workflow using pull_request_target instead of pull_request is refused."""
        planted_codeql = self.codeql_text.replace("pull_request:", "pull_request_target:")
        workflows = dict(self.workflows, **{"codeql.yml": planted_codeql})
        with self.assertRaisesRegex(
            ValueError, r"codeql\.yml reports required check.*does not run on pull_request"
        ):
            validate_required_checks(self.ruleset, workflows, self.catalog_text)

    def test_refuse_catalog_without_ci_dispatch(self):
        """A catalog workflow missing the ci.yml dispatch line is refused naming ci.yml."""
        planted = "\n".join(
            line for line in self.catalog_text.splitlines() if "gh workflow run ci.yml" not in line
        )
        with self.assertRaisesRegex(ValueError, "does not dispatch ci\\.yml"):
            validate_required_checks(self.ruleset, self.workflows, planted)

    def test_refuse_catalog_without_ci_run_check(self):
        """A catalog workflow dispatching ci.yml without checking its head commit runs is refused."""
        planted = "\n".join(
            line for line in self.catalog_text.splitlines() if "ci.yml/runs" not in line
        )
        with self.assertRaisesRegex(
            ValueError,
            r"dispatches ci\.yml without checking for a dispatched run of the head commit",
        ):
            validate_required_checks(self.ruleset, self.workflows, planted)

    def test_refuse_unreported_required_context(self):
        """A required status check context not provided by any workflow is refused naming it."""
        planted_ci = self.ci_text.replace("name: server-check", "name: unrequired-check")
        workflows = dict(self.workflows, **{"ci.yml": planted_ci})
        with self.assertRaisesRegex(ValueError, "server-check"):
            validate_required_checks(self.ruleset, workflows, self.catalog_text)

    def test_boundary_empty_ruleset_passes(self):
        """A ruleset with no required_status_checks rule passes with arbitrary workflows."""
        empty_ruleset = json.dumps({"rules": [{"type": "deletion"}]})
        self.assertTrue(validate_required_checks(empty_ruleset, {}, "no-op"))

    def test_matrix_expansion_for_codeql(self):
        """Matrix expansion for codeql.yml yields exactly analyze (python) and analyze (actions)."""
        self.assertEqual(workflow_contexts(self.codeql_text), ["analyze (python)", "analyze (actions)"])

    def test_workflow_contexts_refuses_include_matrix(self):
        """A matrix defining an include axis raises ValueError naming the job id."""
        workflow = "jobs:\n  build:\n    strategy:\n      matrix:\n        include:\n          - os: ubuntu\n"
        with self.assertRaisesRegex(ValueError, r"\bbuild\b"):
            workflow_contexts(workflow)

    def test_workflow_contexts_refuses_two_key_matrix(self):
        """A matrix defining more than one axis raises ValueError naming the job id."""
        workflow = (
            "jobs:\n  test:\n    strategy:\n      matrix:\n"
            "        os: [ubuntu, macos]\n        arch: [x64, arm64]\n"
        )
        with self.assertRaisesRegex(ValueError, r"\btest\b"):
            workflow_contexts(workflow)

    def test_workflow_contexts_refuses_block_list_matrix(self):
        """A matrix axis written as a YAML block list raises ValueError naming the job id."""
        workflow = (
            "jobs:\n  lint:\n    strategy:\n      matrix:\n"
            "        tool:\n          - ruff\n          - actionlint\n"
        )
        with self.assertRaisesRegex(ValueError, r"\blint\b"):
            workflow_contexts(workflow)

    def test_workflow_contexts_refuses_expression_and_empty_matrix(self):
        """An expression matrix and an empty inline list both raise ValueError naming the job id."""
        expression = "jobs:\n  gen:\n    strategy:\n      matrix: ${{ fromJSON(needs.plan.outputs.m) }}\n"
        with self.assertRaisesRegex(ValueError, r"'gen' matrix must be a bare 'matrix:' line"):
            workflow_contexts(expression)
        empty = "jobs:\n  gen:\n    strategy:\n      matrix:\n        os: []\n"
        with self.assertRaisesRegex(ValueError, r"'gen' matrix axis 'os' has empty list"):
            workflow_contexts(empty)

    def test_refuse_required_check_with_invalid_matrix(self):
        """A workflow providing a required check with an invalid matrix is set aside and refused."""
        block_list_codeql = (
            "name: CodeQL\n"
            "on:\n"
            "  pull_request:\n"
            "jobs:\n"
            "  analyze:\n"
            "    strategy:\n"
            "      matrix:\n"
            "        language:\n"
            "          - python\n"
            "          - actions\n"
        )
        workflows = dict(self.workflows, **{"codeql.yml": block_list_codeql})
        with self.assertRaisesRegex(
            ValueError, r"no workflow reports required status check context 'analyze \(python\)'.*codeql\.yml"
        ):
            validate_required_checks(self.ruleset, workflows, self.catalog_text)

    def test_platforms_workflow_matrix_raises(self):
        """The platforms.yml workflow has an include matrix, so workflow_contexts raises."""
        platforms_text = self.workflows["platforms.yml"]
        with self.assertRaisesRegex(ValueError, r"\bverify-all\b"):
            workflow_contexts(platforms_text)


if __name__ == "__main__":
    unittest.main()
