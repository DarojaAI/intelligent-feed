# Changelog

All notable changes to `intelligent-feed` are documented here. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions are derived from git tags by `setuptools_scm` — see
[`pyproject.toml`](pyproject.toml). The first release is `0.1.0`; the
exact version of any subsequent release is determined by the commit
history since the previous tag, following the
[Conventional Commits](https://www.conventionalcommits.org/) preset used
by the release workflow.

## [Unreleased]

### Changed
- Migrating to installable Python package (preparing for `0.1.0`).
  See the `0.1.0` entry below for the public-facing details.

## [0.1.0] — Packaging release

### Added
- `pyproject.toml` defining the `intelligent-feed` distribution. The
  package version is derived from git tags via `setuptools_scm`
  (`tag_regex = ^v(?P<version>X.Y.Z)$`).
- `README.md` documenting install, quickstart, and the
  `INTELLIGENT_FEED_PATH` deprecation path.
- `CHANGELOG.md` (this file).
- `.github/workflows/release.yml` invoking
  `DarojaAI/infra-actions/.github/workflows/reusable-semantic-release.yml@v1.3.0`
  with conventional-commits → `vX.Y.Z` tag bumping. The first tag this
  workflow produces is `v0.1.0`.
- `.pre-commit-config.yaml` (mirrors the devnexus-common setup) so the
  existing `reusable-pre-commit.yml` call from `ci.yml` has hooks to run.

### Changed
- License: MIT → **Apache-2.0**. The MIT license is replaced in-place by
  the new Apache 2.0 text; downstream consumers should review their
  NOTICE obligations.
- CI now installs via `pip install -e ".[dev]"` instead of
  `pip install -r requirements.txt`. The pip cache key switched from
  `**/requirements*.txt` to `pyproject.toml` to match.
- CI adds a Python 3.14 job to validate the new `requires-python` floor.
  The existing 3.11 job is preserved.
- Python floor raised from "unspecified" to `>=3.14`. Downstream consumers
  (`research-orchestrator` and friends) must run on 3.14+ to use the
  packaged release.

### Deprecated
- The `INTELLIGENT_FEED_PATH` env var and the `sys.path` injection
  pattern in `research-orchestrator/app/activation.py` is **deprecated**.
  Consumers should switch to `from intel.activation.factory import
  get_activator` after `pip install intelligent-feed>=0.1.0`. The env
  var will continue to be honored as a fallback until `0.3.0` and removed
  in that release or later. See
  [`DarojaAI/research-orchestrator#1`](https://github.com/DarojaAI/research-orchestrator/issues/1)
  for the consumer-side migration.

### Removed
- `requirements.txt`. The contents are now declared in `pyproject.toml`
  under `[project] dependencies`. Use `pip install -e ".[dev]"` for an
  editable install with test dependencies.

## Reference

- Tracking issue: [`DarojaAI/intelligent-feed#2`](https://github.com/DarojaAI/intelligent-feed/issues/2).
- The pre-packaging contract is documented in [`AGENTS.md`](AGENTS.md).
- The Q15-17 hardening work (env-var path overrides, AGENTS.md, CI,
  LICENSE) was merged in PR #1 immediately before this release.
- Mirror of the same packaging shape:
  [`DarojaAI/devnexus-common`](https://github.com/DarojaAI/devnexus-common)
  (`pyproject.toml` + `reusable-semantic-release.yml` + `setuptools_scm`).
