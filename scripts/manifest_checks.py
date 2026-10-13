"""Check manifest.json against what the plugin repository already published and what exists to install.

history:  refuse a manifest that removes or rewrites a version the base branch publishes. Existing
          versions are immutable plugin repository history (README.md); the updater keeps that rule
          for what it writes, this check keeps it for every change, a hand-edited one included.
releases: refuse a manifest version whose download does not answer. A version listed before its
          release could be installed, like the withdrawn 1.0.0 entry removed in 3de34bb (#10),
          sends every server that adds the repository to a missing archive.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "manifest.json"
DEFAULT_BASE = "origin/main"
MAX_VERSIONS = 4096
GIT_SECONDS = 20
HTTP_SECONDS = 30


class ManifestError(Exception):
    """The manifest, or the one it is compared with, cannot be read as plugin repository entries."""


def versions(manifest):
    """Return every version entry of manifest keyed by plugin GUID and version number."""
    if not isinstance(manifest, list):
        raise ManifestError("the manifest is not a list of plugins")
    found = {}
    for plugin in manifest:
        if not isinstance(plugin, dict) or not isinstance(plugin.get("guid"), str):
            raise ManifestError("a plugin entry has no GUID")
        entries = plugin.get("versions")
        if not isinstance(entries, list):
            raise ManifestError(f"plugin {plugin['guid']} has no list of versions")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("version"), str):
                raise ManifestError(f"plugin {plugin['guid']} has a version without a number")
            key = (plugin["guid"], entry["version"])
            if key in found:
                raise ManifestError(f"plugin {key[0]} lists version {key[1]} twice")
            if len(found) >= MAX_VERSIONS:
                raise ManifestError(f"the manifest holds more than {MAX_VERSIONS} versions")
            found[key] = entry
    return found


def history_findings(base, head):
    """Return one line for every version of base that head removes or rewrites."""
    before, after = versions(base), versions(head)
    findings = []
    for (guid, number), entry in sorted(before.items()):
        if (guid, number) not in after:
            findings.append(f"{guid} {number} was published and is removed")
        elif after[(guid, number)] != entry:
            findings.append(f"{guid} {number} was published and is rewritten")
    return findings


def release_findings(manifest, answer):
    """Return one line for every version of manifest whose sourceUrl answer(url) does not report as 200."""
    findings = []
    for (guid, number), entry in sorted(versions(manifest).items()):
        url = entry.get("sourceUrl")
        status = answer(url) if isinstance(url, str) and url.startswith("https://") else "no https sourceUrl"
        if status != 200:
            findings.append(f"{guid} {number}: {url} answers {status}")
    return findings


def head_status(url):
    """Return the HTTP status a HEAD request for url ends with after redirects, or the error that stopped it."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=HTTP_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError) as error:
        return f"no answer ({error})"


def base_manifest(ref, root=ROOT):
    """Return the manifest at ref, read with git."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:{MANIFEST}"],
            capture_output=True, text=True, timeout=GIT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ManifestError(f"git show {ref}:{MANIFEST} did not finish: {error}") from error
    if done.returncode != 0:
        raise ManifestError(f"git show {ref}:{MANIFEST} failed: {done.stderr.strip()}")
    return parse(done.stdout, f"{ref}:{MANIFEST}")


def parse(text, name):
    """Return the JSON value text holds; name says where it came from."""
    try:
        return json.loads(text)
    except ValueError as error:
        raise ManifestError(f"{name} is not JSON: {error}") from error


def main(arguments, root=ROOT, answer=head_status):
    """Run one check; return 0 when it passes, 1 with its findings, 2 when it cannot run."""
    command, rest = (arguments[0], arguments[1:]) if arguments else ("", [])
    try:
        head = parse((root / MANIFEST).read_text(encoding="utf-8"), MANIFEST)
        if command == "history" and len(rest) <= 1:
            findings = history_findings(base_manifest(rest[0] if rest else DEFAULT_BASE, root), head)
        elif command == "releases" and not rest:
            findings = release_findings(head, answer)
        else:
            print("usage: manifest_checks.py history [<base ref>] | releases", file=sys.stderr)
            return 2
    except (ManifestError, OSError) as error:
        print(f"manifest-checks: {error}", file=sys.stderr)
        return 2
    for line in findings:
        print(f"manifest-checks: {line}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
