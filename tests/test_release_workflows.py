"""Tests for signed release workflows, pin invariants, and 3D verification."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
NEW_WORKFLOW_FILES = ("release.yml", "build-signed.yml", "prepare-release.yml")

USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)", re.MULTILINE)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_uses_pins(content):
    """Refuse any non-local uses: reference that is not pinned to a 40-hex SHA."""
    for target in USES_RE.findall(content):
        if target.startswith("./"):
            continue
        if "@" not in target:
            raise ValueError(f"Action reference missing @ commit: {target}")
        _, ref = target.split("@", 1)
        if not COMMIT_RE.fullmatch(ref):
            raise ValueError(f"Action reference is not a 40-hex commit SHA: {target}")
    return True


def validate_release_pipeline(content):
    """Enforce verify -> build -> publish pipeline order in release.yml."""
    jobs_match = re.search(r"^jobs:\s*\n(.*)", content, re.MULTILINE | re.DOTALL)
    if not jobs_match:
        raise ValueError("release.yml has no jobs section")
    jobs_text = jobs_match.group(1)

    verify_match = re.search(r"^  verify:\s*\n(.*?)(?=^  [a-z-]+:|\Z)", jobs_text, re.MULTILINE | re.DOTALL)
    build_match = re.search(r"^  build:\s*\n(.*?)(?=^  [a-z-]+:|\Z)", jobs_text, re.MULTILINE | re.DOTALL)
    publish_match = re.search(r"^  publish:\s*\n(.*?)(?=^  [a-z-]+:|\Z)", jobs_text, re.MULTILINE | re.DOTALL)

    if not verify_match or not build_match or not publish_match:
        raise ValueError("release.yml missing one of required jobs: verify, build, publish")

    build_body = build_match.group(1)
    if not re.search(r"^\s+needs:\s*verify\b", build_body, re.MULTILINE):
        raise ValueError("build job does not depend on verify job")
    if "uses: ./.github/workflows/build-signed.yml" not in build_body:
        raise ValueError("build job does not use build-signed.yml")

    publish_body = publish_match.group(1)
    if not re.search(r"^\s+needs:\s*build\b", publish_body, re.MULTILINE):
        raise ValueError("publish job does not depend on build job")
    return True


def validate_workflow_permissions(content):
    """Enforce workflow-level contents: read and ensure write permissions are job-scoped."""
    top_perm = re.search(r"^permissions:\s*\n((?:  [a-z-]+:\s+[a-z]+\n?)+)", content, re.MULTILINE)
    if not top_perm:
        raise ValueError("Workflow missing top-level permissions block")
    top_text = top_perm.group(1)
    if ": write" in top_text:
        raise ValueError(f"Top-level permissions must not grant write: {top_text.strip()}")
    if "contents: read" not in top_text:
        raise ValueError("Top-level permissions must declare contents: read")

    for line in content.splitlines():
        if re.search(r":\s*write\b", line):
            indent = len(line) - len(line.lstrip())
            if indent < 4:
                raise ValueError(f"Write permission must be indented inside a job: {line.strip()}")
    return True


class ReleaseWorkflowsPositiveTests(unittest.TestCase):
    """Positive 3D tests for release workflows, pins, and step sequencing."""

    def test_all_workflow_uses_pinned_to_40_hex_sha(self):
        for filename in NEW_WORKFLOW_FILES:
            content = (WORKFLOWS / filename).read_text(encoding="utf-8")
            self.assertTrue(validate_uses_pins(content))

    def test_release_pipeline_sequence(self):
        content = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        self.assertTrue(validate_release_pipeline(content))

    def test_publish_job_copy_step_after_verify_step(self):
        content = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        verify_pos = content.find("cosign verify-blob")
        copy_pos = content.find("cp -n signatures/*.sigstore.json dist/")
        publish_pos = content.find("uses: jellysin/release-helper/actions/publish")

        self.assertNotEqual(verify_pos, -1, "cosign verify-blob step not found")
        self.assertNotEqual(copy_pos, -1, "copy bundles step not found")
        self.assertNotEqual(publish_pos, -1, "publish action step not found")
        self.assertLess(verify_pos, copy_pos, "verify step must precede copy step")
        self.assertLess(copy_pos, publish_pos, "copy step must precede publish action")

    def test_publish_action_specifies_signer_workflow_and_kind(self):
        content = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        self.assertIn("signer-workflow: .github/workflows/build-signed.yml", content)
        self.assertIn("kind: source", content)


class ReleaseWorkflowsNegativeTests(unittest.TestCase):
    """Negative 3D tests verifying refusal of defective workflow configurations."""

    def test_refuse_unpinned_action_reference(self):
        defective = "jobs:\n  run:\n    steps:\n      - uses: actions/checkout@v4\n"
        with self.assertRaisesRegex(ValueError, "not a 40-hex commit SHA"):
            validate_uses_pins(defective)

    def test_refuse_short_commit_sha(self):
        defective = "jobs:\n  run:\n    steps:\n      - uses: actions/checkout@3d3c42e\n"
        with self.assertRaisesRegex(ValueError, "not a 40-hex commit SHA"):
            validate_uses_pins(defective)

    def test_refuse_publish_preceding_verify(self):
        defective = (
            "jobs:\n"
            "  verify:\n"
            "    uses: ./.github/workflows/ci.yml\n"
            "  build:\n"
            "    uses: ./.github/workflows/build-signed.yml\n"
            "  publish:\n"
            "    needs: verify\n"
        )
        with self.assertRaisesRegex(ValueError, "build job does not depend on verify job"):
            validate_release_pipeline(defective)

    def test_refuse_publish_without_build_dependency(self):
        defective = (
            "jobs:\n"
            "  verify:\n"
            "    uses: ./.github/workflows/ci.yml\n"
            "  build:\n"
            "    needs: verify\n"
            "    uses: ./.github/workflows/build-signed.yml\n"
            "  publish:\n"
            "    needs: verify\n"
        )
        with self.assertRaisesRegex(ValueError, "publish job does not depend on build job"):
            validate_release_pipeline(defective)


class ReleaseWorkflowsBoundaryTests(unittest.TestCase):
    """Boundary 3D tests enforcing read-only workflow permissions and job-scoped writes."""

    def test_all_new_workflows_have_read_only_top_level_permissions(self):
        for filename in NEW_WORKFLOW_FILES:
            content = (WORKFLOWS / filename).read_text(encoding="utf-8")
            self.assertTrue(validate_workflow_permissions(content))

    def test_ci_workflow_has_read_only_top_level_permissions(self):
        content = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertTrue(validate_workflow_permissions(content))

    def test_refuse_workflow_level_write_permission(self):
        defective = (
            "name: Defective\n"
            "permissions:\n"
            "  contents: write\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-24.04\n"
        )
        with self.assertRaisesRegex(ValueError, "Top-level permissions must not grant write"):
            validate_workflow_permissions(defective)

    def test_refuse_missing_contents_read_at_top_level(self):
        defective = (
            "name: Defective\n"
            "permissions:\n"
            "  issues: read\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-24.04\n"
        )
        with self.assertRaisesRegex(ValueError, "Top-level permissions must declare contents: read"):
            validate_workflow_permissions(defective)


if __name__ == "__main__":
    unittest.main()
