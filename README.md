# JellySin Plugin Repository

<!-- praetor:readme-governance:start -->
[![HISS Adopted][praetor-hiss-badge]][praetor-hiss-agents]

Praetor manages this repository's declared governance policy. This managed
block records adoption state; it is not a verification certificate.

**Verification**: `make verify-all` runs the repository's configured
verification cascade.

**HISS Audit**: `praetorctl audit` enforces policy, generated-surface
integrity, and the debt ratchet.

**Context Sync**: `praetorctl compile-context --verify` verifies every
generated agent context against `AGENTS.md`.

**Debt Baseline**: `.standards-baseline.json` anchors the debt ratchet at
0 recorded infractions; audit forbids growth.

[praetor-hiss-badge]: https://img.shields.io/badge/Standards-HISS%20Adopted-blue
[praetor-hiss-agents]: https://github.com/jellysin/repo/blob/HEAD/AGENTS.md
<!-- praetor:readme-governance:end -->

JellySin: Jellyfin plus sin, a little temptation for your media server; said JELLY-sin.

One plugin repository for JellySin's independent Jellyfin 12 plugins. Add this URL
in Jellyfin's plugin repository settings:

```text
https://raw.githubusercontent.com/jellysin/repo/main/manifest.json
```

The plugin repository lists one plugin,
[JellySin Last.fm](https://github.com/jellysin/plugin-lastfm), with its 0.x
releases. Every listed version passed the checks described below: an allowlisted
signer, verified provenance and a real Jellyfin server that offers it.

## Publication

An allowlist binds each plugin GUID to one public source repository and the one
workflow that signs its release artifacts: `.github/workflows/release.yml` or the
reusable `.github/workflows/build-signed.yml` that release-helper also approves.
When enabled, the updater is configured
for minutes 17 and 47 each hour and supports manual dispatch. GitHub scheduled
runs can be delayed; this is a polling interval, not a publication latency guarantee.

Pinned shared tooling verifies the actual GitHub-signed provenance of all four
release artifacts against the repository, workflow, commit and tag. Releases must
be immutable. The ZIP's SHA-256, Jellyfin MD5, size, member paths, permissions,
file allowlist and CRC are checked before any plugin repository file changes.

CI also loads `manifest.json` into a real Jellyfin 12.2 server and fails when the
server does not offer an entry. Validation of the file's form cannot show that: a
server silently drops a version whose `targetAbi` is above its own version.

The updater opens a PR using only this repository's GITHUB_TOKEN and explicitly
dispatches CI on its branch. Required checks and normal PR review/merge behavior
apply. Plugin source repositories have no write access here, and no release App
or personal access token is needed.

## Adding a plugin

Submit a PR adding a unique GUID, repository, and approved workflow to `plugins.json`.
Review the source repository and publication workflow before adding that trust.
The source must use the release metadata contract in
[release-helper](https://github.com/jellysin/release-helper). The Last.fm descriptor
is the first allowlisted plugin; no Last.fm-specific behavior exists in the updater.

Existing versions are immutable plugin repository history. Do not replace checksums, edit
download URLs, or remove old compatible versions to repair an upload. Publish a
new version instead. A failed verification leaves the entire plugin repository unchanged.

EUPL-1.2 covers this repository's source and documentation. See CONTRIBUTING.md.
