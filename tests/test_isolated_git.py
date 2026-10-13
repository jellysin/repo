"""A push from a linked worktree whose hook runs git in a temporary repository leaves the pushing repository alone."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import isolated_git

isolated_git.isolate()

TESTS = Path(__file__).resolve().parent
IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false")
# What a test does inside the hook: isolate, then build a repository with one commit, the way the test modules do.
HOOK_TEST = f"""
import subprocess, sys, tempfile
sys.path.insert(0, {str(TESTS)!r})
import isolated_git
isolated_git.isolate()
with tempfile.TemporaryDirectory() as path:
    open(path + "/stand-in", "w").close()
    for arguments in (("init", "--quiet"), ("add", "stand-in"), (*{IDENTITY!r}, "commit", "--quiet", "-m", "stand-in")):
        subprocess.run(["git", "-C", path, *arguments], check=True, timeout=20, capture_output=True)
"""


def git(directory, *arguments):
    done = subprocess.run(["git", "-C", str(directory), *arguments], check=False, timeout=60, capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"git {arguments[0]} failed ({done.returncode}): {done.stderr.strip()}")
    return done.stdout.strip()


class PushFromLinkedWorktree(unittest.TestCase):
    def setUp(self):
        base = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.main, self.worktree, remote = base / "main", base / "worktree", base / "remote.git"
        git(base, "init", "--quiet", "--bare", str(remote))
        git(base, "init", "--quiet", "--initial-branch=main", str(self.main))
        (self.main / "file").write_text("base\n", encoding="utf-8")
        git(self.main, "add", "file")
        git(self.main, *IDENTITY, "commit", "--quiet", "-m", "base")
        git(self.main, "remote", "add", "origin", str(remote))
        git(self.main, "worktree", "add", "--quiet", "-b", "topic", str(self.worktree))
        hooks = base / "hooks"
        hooks.mkdir()
        (hooks / "hook_test.py").write_text(HOOK_TEST, encoding="utf-8")
        (hooks / "pre-push").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{hooks / "hook_test.py"}"\n', encoding="utf-8")
        (hooks / "pre-push").chmod(0o755)
        git(self.main, "config", "core.hooksPath", str(hooks))

    def test_the_hook_commit_stays_in_its_temporary_repository(self):
        tip = git(self.worktree, "rev-parse", "HEAD")
        git(self.worktree, "push", "--quiet", "origin", "topic")
        self.assertEqual(git(self.worktree, "rev-parse", "HEAD"), tip)
        self.assertEqual(git(self.main, "rev-parse", "main"), tip)
        self.assertEqual(git(self.main, "config", "--bool", "core.bare"), "false")
        self.assertEqual(git(self.worktree, "status", "--porcelain"), "")

    def test_isolate_removes_every_git_variable_and_nothing_else(self):
        environment = {"GIT_DIR": "a", "GIT_WORK_TREE": "b", "GIT_INDEX_FILE": "c", "PATH": "d", "XGIT_DIR": "e"}
        isolated_git.isolate(environment)
        self.assertEqual(environment, {"PATH": "d", "XGIT_DIR": "e"})


class EveryModuleIsolates(unittest.TestCase):
    def test_every_test_module_that_runs_git_isolates_first(self):
        for path in sorted(TESTS.glob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            if '"git"' in text or "release_helper" in text or "manifest_checks" in text:
                with self.subTest(module=path.name):
                    self.assertIn("\nisolated_git.isolate()\n", text)


if __name__ == "__main__":
    unittest.main()
