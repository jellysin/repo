# Contributing

Create a feature branch from main and open a PR with a Conventional Commit title.
Squash merges are used. The branch ruleset in `.github/rulesets/main.json` declares
required checks with `strict: true`, so a branch must be up to date with main before it merges.

CI uses SHA-pinned shared tooling to validate plugin repository structure, plugin identities,
repository allowlisting, pinned Actions and policy documents. It also runs
actionlint. Locally, use a checkout of the exact tooling commit pinned in CI:

```sh
python ../release-helper/tools.py validate-catalog
python ../release-helper/tools.py check-policy
actionlint
```

Run these commands in `repo`. Local manifest updates also require GitHub CLI
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

Release-please collects merged changes into version and changelog PRs. Merging such a
PR creates no tag and no GitHub release, because the shared workflow sets
`skip-github-release`. It does not control individual plugin versions; each plugin
owns its own release process.
