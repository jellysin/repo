"""Run release-helper at the one commit the workflows pin, so that local checks and CI run the same code."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
CACHE = ROOT / ".workingdir" / "cache"
SOURCE = "https://github.com/jellysin/release-helper.git"
# Every use of the helper: an action or a reusable workflow, followed by the reference that selects its code.
REFERENCE = re.compile(r"jellysin/release-helper/[^\s@]+@(\S+)")
# The helper's earlier name, which GitHub still resolves: a reference under it would run a helper
# this check never reads, such as the plugin-tooling commit 9efa4a2 (#4) replaced.
OLD_NAME = re.compile(r"jellysin/plugin-tooling/[^\s@]+@\S+")
# Helper commits a fix replaced, with the reason a workflow must not pin them again.
REPLACED = {
    "18035406096fc160acccc0afa7238aa314f0a4aa": "replaced in 9efa4a2 (#4): it does not validate complete release inventories",
}
COMMIT = re.compile(r"[0-9a-f]{40}")
MAX_WORKFLOWS = 64
GIT_SECONDS = 20
FETCH_SECONDS = 120
RUN_SECONDS = 1800


class PinError(Exception):
    """The helper cannot run at exactly the commit the workflows pin."""


def pinned(workflows):
    """Return the one commit all workflows pin; refuse no reference, a tag or branch, two different commits,
    a reference under the helper's old name and a commit a fix replaced."""
    files = sorted(Path(workflows).glob("*.yml"))
    if len(files) > MAX_WORKFLOWS:
        raise PinError(f"More than {MAX_WORKFLOWS} workflow files; the pin is not read from a part of them")
    texts = [path.read_text(encoding="utf-8") for path in files]
    old = sorted({reference for text in texts for reference in OLD_NAME.findall(text)})
    if old:
        raise PinError("Workflows reference jellysin/plugin-tooling, release-helper's old name: " + ", ".join(old))
    found = sorted({reference for text in texts for reference in REFERENCE.findall(text)})
    replaced = [f"{reference} ({REPLACED[reference]})" for reference in found if reference in REPLACED]
    if replaced:
        raise PinError("Workflows pin a replaced release-helper commit: " + ", ".join(replaced))
    if not found:
        raise PinError(f"No workflow in {workflows} references jellysin/release-helper")
    loose = [reference for reference in found if not COMMIT.fullmatch(reference)]
    if loose:
        raise PinError("release-helper reference is not a full commit: " + ", ".join(loose))
    if len(found) > 1:
        raise PinError("Workflows pin different release-helper commits: " + ", ".join(found))
    return found[0]


def git(directory, seconds, *arguments):
    """Run one git command with a deadline and return its trimmed output; a failure names the command."""
    try:
        done = subprocess.run(
            ["git", "-C", str(directory), *arguments], capture_output=True, text=True, timeout=seconds, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PinError(f"git {arguments[0]} did not finish: {error}") from error
    if done.returncode != 0:
        raise PinError(f"git {arguments[0]} failed ({done.returncode}): {done.stderr.strip()}")
    return done.stdout.strip()


def verified(directory, pin):
    """Return the directory when it is an unmodified checkout of the pin; refuse any other state."""
    head = git(directory, GIT_SECONDS, "rev-parse", "HEAD")
    if head != pin:
        raise PinError(f"{directory} is at {head}; the workflows pin {pin}")
    if git(directory, GIT_SECONDS, "status", "--porcelain"):
        raise PinError(f"{directory} has local changes; the workflows pin {pin} unmodified")
    return Path(directory)


def checkout(pin, cache, source=SOURCE):
    """Return a checkout of the pin below the cache directory; fetch that single commit when it is absent."""
    target = Path(cache) / f"release-helper-{pin}"
    if not target.is_dir():
        Path(cache).mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="staging-", dir=cache))
        try:
            git(staging, GIT_SECONDS, "init", "--quiet")
            git(staging, FETCH_SECONDS, "fetch", "--quiet", "--depth", "1", str(source), pin)
            git(staging, GIT_SECONDS, "checkout", "--quiet", "--detach", "FETCH_HEAD")
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return verified(target, pin)


def main(arguments, workflows=WORKFLOWS, cache=CACHE, environment=os.environ):
    """Run the helper's tools.py with the given arguments and return its exit status."""
    try:
        pin = pinned(workflows)
        given = environment.get("RELEASE_HELPER")
        directory = verified(given, pin) if given else checkout(pin, cache)
    except PinError as error:
        print(f"release-helper: {error}", file=sys.stderr)
        return 2
    print(f"release-helper: {pin} in {directory}", file=sys.stderr, flush=True)
    try:
        # An argument list without a shell; the directory is the checkout verified against the pin.
        command = [sys.executable, "-B", str(directory / "tools.py"), *arguments]
        return subprocess.run(command, cwd=ROOT, timeout=RUN_SECONDS, check=False).returncode  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"release-helper: tools.py did not finish: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
