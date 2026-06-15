# intelligent-feed

> Scheduled pipeline that monitors technical sources (RSS, PyPI), enriches
> content via Claude API, and delivers curated updates to human (Markdown),
> agent (JSON), and structured (Cognee cognify + project activators)
> subscribers.

This repo is also a **shared activation library**. The activators in
`intel/activation/` are consumed by `DarojaAI/research-orchestrator` to
write per-project artifacts (extraction logs, conventions, knowledge stores).

## Status

| | |
|---|---|
| **Package** | `intelligent-feed` on the [DarojaAI private package index][pypi] |
| **Python** | `>=3.14` |
| **License** | Apache-2.0 |
| **Consumers** | [`DarojaAI/research-orchestrator`][orch] (activators), plus the in-repo `intel/renderers/` pipeline. |

[pypi]: https://pypi.org/project/intelligent-feed/
[orch]: https://github.com/DarojaAI/research-orchestrator

## Install

From the private index (production / CI):

```bash
pip install intelligent-feed>=0.1.0
```

Editable install from a VCS checkout (local development):

```bash
git clone https://github.com/DarojaAI/intelligent-feed
cd intelligent-feed
pip install -e ".[dev]"
```

## Quickstart — using the activators (consumer side)

```python
from intel.activation.factory import get_activator

activator = get_activator("bond-nexus")
result = activator.check_readiness()
if not result.success:
    raise SystemExit(f"not ready: {result.error}")

claims = [...]  # claims produced upstream by the Cognee renderer
result = activator.activate(claims, dry_run=False)
print(result)
```

Supported projects (see `intel/activation/factory.py` for the source of truth):

- `globalbitings`
- `bond-nexus` (alias: `bond_nexus`)
- `rag-research` (alias: `rag_research`)
- `dynamic-worlock` (alias: `dynamic_worlock`)

## Quickstart — running the pipeline (in-repo)

The package still works as a runnable application. The CLI entry point is
unchanged from the pre-packaging layout.

```bash
# 1. set required env vars (see .env.example)
cp .env.example .env
$EDITOR .env

# 2. run the pipeline once
python -m intel.db_cli run-once
```

## Migrating from `INTELLIGENT_FEED_PATH`

Before this package existed, consumers (notably `research-orchestrator`) loaded
the activators via a filesystem `sys.path` injection:

```python
# OLD (in research-orchestrator/app/activation.py)
import os, sys
path = os.environ.get("INTELLIGENT_FEED_PATH")
if path not in sys.path:
    sys.path.insert(0, path)
from intel.activation import factory
```

That pattern is **deprecated**. The new consumer-side code is:

```python
# NEW
from intel.activation.factory import get_activator
```

`research-orchestrator` is being updated in
[`DarojaAI/research-orchestrator#1`][orch-issue] to drop the `sys.path`
injection. The `INTELLIGENT_FEED_PATH` env var is still honored as a
fallback for one release cycle and will be removed in `intelligent-feed`
`0.3.0`.

[orch-issue]: https://github.com/DarojaAI/research-orchestrator/issues/1

## Repository layout

```
intel/
├── activation/    # shared library — per-project activators + factory
│   ├── base.py
│   ├── bondnexus.py
│   ├── dynamic_worlock.py
│   ├── factory.py
│   ├── globalbitings.py
│   └── rag_research.py
├── api/           # FastAPI app
├── renderers/     # human / agent / structured (Cognee) renderers
├── cognify_client.py
├── config.py
├── db.py
├── db_cli.py
├── enricher.py
├── fetcher.py
├── models.py
├── router.py
└── scheduler.py
tests/
```

## Contributing

- Read [`AGENTS.md`](AGENTS.md) — the contract an agent reads when
  working in this repo. Hard rules (env-var path overrides, factory
  registration, no hardcoded target paths, no secrets in commits) live
  there.
- PRs to `main`; CI must pass. Release tags (`vX.Y.Z`) are produced
  automatically by `.github/workflows/release.yml` from conventional
  commit messages.
- See [`CHANGELOG.md`](CHANGELOG.md) for version history.

## License

Copyright 2026 Milan Patel / DarojaAI. Licensed under the
[Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
See [`LICENSE`](LICENSE) for the full text.
