# Contributing

Create a feature branch from main and open a PR with a Conventional Commit title.
Squash merges are used. The branch ruleset in `.github/rulesets/main.json` declares
required checks with `strict: true`, so a branch must be up to date with main before it merges.

CI uses SHA-pinned shared tooling to validate plugin repository structure, plugin identities,
repository allowlisting, pinned Actions and policy documents. It also runs actionlint and
the tests in `tests/`.

The job `server-check` loads `manifest.json` into a real Jellyfin 12.2 server and fails
when the server withholds an entry, for example a version whose `targetAbi` is above the
server. The same job proves the check in both directions with two generated files: the
server must offer the `floor` fixture and must refuse the `wrong-abi` fixture with its
`does not offer` line. Keep that negative case when changing the job.

## Local gate

```sh
make verify-all
```

The target runs the governance checks, the policy and catalog validation of
[release-helper](https://github.com/jellysin/release-helper), the tests and actionlint.
`Makefile` lists the steps. It needs git, actionlint and a Python interpreter from the
minor line that `.python-version` pins.

The first step, `scripts/python_pin.py`, refuses any other minor line before a check runs
on it. A different patch level passes and is named in the output. Renovate keeps the file
current. In CI the interpreter comes from the release-helper action, which reads its own
`.python-version`; the same step checks that both are on one minor line.

`scripts/release_helper.py` runs the helper at the one commit that all workflows pin, so
that a local run and CI execute the same code. It fetches that commit once into
`.workingdir/cache/` and prints the commit it runs. It refuses to run when the workflows
name a tag, a branch or two different commits. `RELEASE_HELPER=<directory>` selects an
existing checkout instead; the script accepts it only when it is an unmodified checkout of
the pinned commit.

```sh
make server-check
```

This runs the server check on `manifest.json`. It needs Docker and pulls the Jellyfin
image, so it is not part of `make verify-all`; CI runs it on every pull request.

Local manifest updates also require GitHub CLI
for signature verification and a GITHUB_TOKEN/GH_TOKEN for
rate-limited API reads. It downloads data but never runs code from plugin archives.

The updater opens `automation/repository` as a PR, then explicitly dispatches CI.
Its commit is created through the GitHub API with the repository token and is signed
as `github-actions[bot]`, because the main ruleset requires signed commits.
GitHub may also place the PR-triggered run behind its bot-workflow approval gate.
A maintainer reviews and approves that run; a dispatched run alone may not clear
the required PR check. No extra App/PAT or synthetic check is used to evade it.
Do not write directly to main or bypass required checks. A failed update keeps
the previous manifest intact. Resolve the release or allowlist problem and retry
the updater; never replace an already published release asset.

Source releases must have immutable releases enabled before publication. The
plugin repository trusts the approved release workflow, not arbitrary self-declared JSON.
Workflow and allowlist changes require careful review of the trust boundary.

Release-please collects merged changes into version and changelog PRs. Release-please
itself creates no tag and no GitHub release: `release-please-config.json` sets
`skip-github-release: true` and the shared workflow passes the same input. It does not
control individual plugin versions; each plugin owns its own release process.

When a release PR is merged on main, `release-automation.yml` runs release-please with
`prepare-release: true`, which dispatches `prepare-release.yml`. `prepare-release.yml`
creates the exact `v<version>` tag on the merge commit and an unpublished draft release
with the changelog section, then dispatches `release.yml` at the tag.

The release workflow (`release.yml`) runs in three stages:

1. `verify`: calls `ci.yml` under a read-only token to validate the repository gate.
2. `build`: calls `build-signed.yml` to verify tag ancestry against `origin/main`, package
   the source archive via `make dist`, generate provenance and SBOM attestations, sign
   each artifact with cosign (`cosign sign-blob --bundle`), and upload the signed bundle.
3. `publish`: downloads the artifact, verifies cosign signatures and GitHub attestations,
   copies signature bundles to `dist/`, and publishes the immutable release via
   `jellysin/release-helper/actions/publish`.

Published releases carry:

- Source archive (`repo-<version>.tar.gz`)
- `release.json`
- `sbom.spdx.json`
- `checksums.txt`
- A `.sigstore.json` signature bundle per asset file

Adopters verify any downloaded asset with cosign:

```sh
cosign verify-blob \
  --bundle <asset>.sigstore.json \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity "https://github.com/jellysin/repo/.github/workflows/build-signed.yml@refs/tags/<tag>" \
  <asset>
```

Historical releases up to `v1.0.4` carry no assets, provenance, signatures or SBOM.

A merged release PR keeps its `autorelease: pending` label until the tag `v<version>`
names its merge commit, and release-please opens no further release PR while it does.
The shared workflow moves the label to `autorelease: tagged` once that tag exists;
never move it by hand.

`release-please-config.json` sets `last-release-sha` to the merge commit of the last
release PR, now release 1.0.4 (tag `v1.0.4`). The key exists because release 1.0.1 was
withdrawn without a tag and release-please would otherwise have collected the whole
history again. Release-please never ignores this key: after every merged release PR,
move it to that release commit, or the next release PR repeats the same entries.
