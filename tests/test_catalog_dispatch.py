"""The catalog bot pull request dispatches workflows providing every required status check.

Catalog bot PR 67 never received required CodeQL checks because codeql.yml lacked
workflow_dispatch and update-catalog.yml only dispatched ci.yml, leaving the pull request
blocked from 2026-10-19 until approved by hand on 2026-11-10.
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


def workflow_contexts(workflow_text):
    """Return the status check contexts reported by a workflow's jobs."""
    jobs_match = re.search(r"^jobs:\s*\n(.*)", workflow_text, re.MULTILINE | re.DOTALL)
    if not jobs_match:
        return []
    jobs_text = jobs_match.group(1)
    job_splits = list(re.finditer(r"^  ([a-zA-Z0-9_-]+):\s*$", jobs_text, re.MULTILINE))
    contexts = []
    for i, match in enumerate(job_splits):
        job_id = match.group(1)
        start = match.end()
        end = job_splits[i + 1].start() if i + 1 < len(job_splits) else len(jobs_text)
        job_body = jobs_text[start:end]
        name_match = re.search(r"^    name:\s*(.+)$", job_body, re.MULTILINE)
        base_name = name_match.group(1).strip() if name_match else job_id
        matrix_match = re.search(r"^\s+matrix:\s*\n\s+[a-zA-Z0-9_-]+:\s*\[(.*?)\]", job_body, re.MULTILINE)
        if matrix_match:
            values = [v.strip().strip("'\"") for v in matrix_match.group(1).split(",") if v.strip()]
            for val in values:
                contexts.append(f"{base_name} ({val})")
        else:
            contexts.append(base_name)
    return contexts


def validate_dispatch(ruleset_text, workflows, catalog_text):
    """Refuse if any required check is unreported or its workflow lacks dispatch in catalog_text."""
    required = required_contexts(ruleset_text)
    contexts_by_file = {fname: workflow_contexts(text) for fname, text in workflows.items()}
    dispatched_workflows = set()
    for context in required:
        matching = [fname for fname, ctxs in contexts_by_file.items() if context in ctxs]
        if not matching:
            raise ValueError(f"no workflow reports required status check context {context!r}")
        dispatched_workflows.update(matching)

    for fname in sorted(dispatched_workflows):
        wtext = workflows[fname]
        on_match = re.search(r"^on:\s*(.*?)(?=^[a-z-]+:|\Z)", wtext, re.MULTILINE | re.DOTALL)
        if not on_match or not re.search(r"^\s*workflow_dispatch:", on_match.group(1), re.MULTILINE):
            raise ValueError(f"{fname} lacks workflow_dispatch in on: block")
        pattern = rf"^\s*gh\s+workflow\s+run\s+{re.escape(fname)}\b.*--ref\s+automation/repository"
        if not re.search(pattern, catalog_text, re.MULTILINE):
            raise ValueError(f"catalog workflow does not dispatch {fname}")
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
        self.assertTrue(validate_dispatch(self.ruleset, self.workflows, self.catalog_text))

    def test_refuse_catalog_without_codeql_dispatch(self):
        """A catalog workflow missing the codeql.yml dispatch line is refused naming codeql.yml."""
        planted = "\n".join(
            line for line in self.catalog_text.splitlines() if "codeql.yml" not in line
        )
        with self.assertRaisesRegex(ValueError, "does not dispatch codeql\\.yml"):
            validate_dispatch(self.ruleset, self.workflows, planted)

    def test_refuse_codeql_without_workflow_dispatch(self):
        """A workflow providing required checks that lacks workflow_dispatch is refused."""
        planted_codeql = "\n".join(
            line for line in self.codeql_text.splitlines() if "workflow_dispatch" not in line
        )
        workflows = dict(self.workflows, **{"codeql.yml": planted_codeql})
        with self.assertRaisesRegex(ValueError, "codeql\\.yml lacks workflow_dispatch"):
            validate_dispatch(self.ruleset, workflows, self.catalog_text)

    def test_refuse_unreported_required_context(self):
        """A required status check context not provided by any workflow is refused naming it."""
        planted_ci = self.ci_text.replace("name: server-check", "name: unrequired-check")
        workflows = dict(self.workflows, **{"ci.yml": planted_ci})
        with self.assertRaisesRegex(ValueError, "server-check"):
            validate_dispatch(self.ruleset, workflows, self.catalog_text)

    def test_boundary_empty_ruleset_passes(self):
        """A ruleset with no required_status_checks rule passes with arbitrary workflows."""
        empty_ruleset = json.dumps({"rules": [{"type": "deletion"}]})
        self.assertTrue(validate_dispatch(empty_ruleset, {}, "no-op"))

    def test_matrix_expansion_for_codeql(self):
        """Matrix expansion for codeql.yml yields exactly analyze (python) and analyze (actions)."""
        self.assertEqual(workflow_contexts(self.codeql_text), ["analyze (python)", "analyze (actions)"])


if __name__ == "__main__":
    unittest.main()
