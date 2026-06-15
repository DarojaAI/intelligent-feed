# AGENTS.md — intelligent-feed

> **Repo:** `DarojaAI/intelligent-feed`
> **Category (per `DarojaAI/.github/GOVERNANCE.md`):** Shared Libraries & Templates (5th category, RFC #2 pending)
> **Role:** A scheduled pipeline that monitors technical sources (RSS, PyPI), enriches content via Claude API, and delivers curated updates to human (Markdown), agent (JSON), and structured (Cognee cognify + project activators) subscribers. **Also serves as a shared activation library** for downstream repos (`research-orchestrator` imports activators from here; `globalbitings`, `bond-nexus`, `rag_research_tool`, and `dynamic-worlock` are the activation targets).

This file is the contract an agent reads when working in this repo. It is not a marketing doc.

---

## First Run

If `BOOTSTRAP.md` exists, follow it, then delete it. (None present at time of writing.)

## Session Startup

The runtime will inject `AGENTS.md`, `SOUL.md` (if any), and recent memory. Do not re-read those files unless explicitly asked or the context is missing something.

## Project Quick Context

- **Architecture:** Sources → Fetcher → Enricher → Router → Renderers (human / agent / structured). See `CLAUDE.md` §"Architecture".
- **Phase 4 (structured):** `intel/renderers/structured.py` runs items through Cognee `cognify()`, then routes to per-project activators in `intel/activation/`. See `memory/2026-06-14-intelligent-feed-take.md` in `darojaai_architect` for the full coupling map.
- **Activators** (one per project): `GlobalBitingsActivator`, `BondNexusActivator`, `RagResearchActivator`, `DynamicWorlockActivator`. Each writes to a target repo's data file.
- **Env vars:** `INTELLIGENT_FEED_PATH` is **deprecated** (see "Packaging" below); `*_PATH` env vars per activator (target side; see "Configuration" below).
- **Consumers:** `DarojaAI/research-orchestrator` imports `get_activator()` from the installed `intelligent-feed` package (post-`0.1.0`). The pre-`0.1.0` `INTELLIGENT_FEED_PATH` + `sys.path` injection is still honored as a fallback until `0.3.0`.
- **Tests:** `pytest tests/ -v` (6 test files, ~85% coverage per pre-existing CI). Install with `pip install -e ".[dev]"` (not `pip install -r requirements.txt` — that file is gone as of `0.1.0`).
- **Decisions / lessons:** see `docs/decisions/` if it exists; otherwise in the `darojaai_architect` repo's `memory/` and `OPEN_QUESTIONS.md`.

## Packaging (post-`0.1.0`)

As of `0.1.0` (tracking issue `#2`), this repo is a regular installable
Python package. Consumers (e.g. `research-orchestrator`) install it with
`pip install intelligent-feed>=0.1.0` from the DarojaAI private index
and import `from intel.activation.factory import get_activator`. The
old `INTELLIGENT_FEED_PATH` + `sys.path` injection pattern is deprecated
and will be removed in `0.3.0`. See [`CHANGELOG.md`](CHANGELOG.md) for
the full notes and `README.md` for the install/quickstart.

Build / install:

- `pip install -e ".[dev]"` for an editable install with test deps.
- `pip install .` for a non-editable install.
- The package version is derived from git tags by `setuptools_scm`
  (`pyproject.toml`, `tag_regex = ^v(?P<version>X.Y.Z)$`). Tags are
  produced by `.github/workflows/release.yml` from conventional
  commits; the first release tag is `v0.1.0`.

## House Rules

1. **Don't hardcode target repo paths.** All 4 activators read `~/GithubProjects/<project>/...` paths by default. Override per environment with `<PROJECT>_<FILE>_PATH` env vars (e.g., `BONDNEXUS_CONVENTIONS_PATH`). See Q16 in `darojaai_architect/OPEN_QUESTIONS.md`.
2. **Don't add a new project without updating the factory.** `intel/activation/factory.py` is the registry. Add the activator class + both naming aliases (hyphen and underscore).
3. **Don't add a new activator without an env-var path override.** The Q16 work is the minimum standard; new activators must follow it from day 1.
4. **Don't commit a real token.** `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, etc. are secrets. `.env.example` documents the shape; `.env` is gitignored.
5. **Don't push directly to main.** PR required; CI must pass.
6. **Don't reimplement LLM / Cognee / DB plumbing from scratch.** Use `intel.activation.BaseActivator`, `intel.cognify_client.CogneeClient`, and the existing model classes.
7. **Don't add `INTELLIGENT_FEED_PATH` to new consumer code.** Use `pip install intelligent-feed` and a normal import. The env-var fallback is for the `0.1.0` → `0.3.0` migration window only.
8. **Don't bump the version manually in `pyproject.toml`.** Versions come from git tags via `setuptools_scm`. Bump by writing conventional commits (a `feat:` triggers a minor bump; a `fix:` triggers a patch).

## Configuration

Each activator's target paths are env-var-overridable. The defaults match the operator's local checkout layout (`~/GithubProjects/<project>/...`) for backward compatibility, but production deployments should set the env vars explicitly.

| Activator | Env var | Default |
|---|---|---|
| `GlobalBitingsActivator` | `GLOBALBITINGS_EXTRACTION_LOG_PATH` | `~/GithubProjects/GlobalBitings/data/extraction_log.jsonl` |
| `GlobalBitingsActivator` | `GLOBALBITINGS_RAG_SYNC_CMD` | `/usr/bin/python3 ~/GithubProjects/GlobalBitings/shapes/RAGResearchTool.py --sync` |
| `BondNexusActivator` | `BONDNEXUS_CONVENTIONS_PATH` | `~/GithubProjects/bond-nexus/nexus_poc/conventions/conventions.yaml` |
| `BondNexusActivator` | `BONDNEXUS_MARKET_SOURCES_PATH` | `~/GithubProjects/bond-nexus/docs/MARKET_SOURCES.md` |
| `RagResearchActivator` | `RAG_RESEARCH_TRIPLETS_PATH` | `~/GithubProjects/rag_research_tool/triplets.json` |
| `DynamicWorlockActivator` | `DYNAMIC_WORLOCK_KNOWLEDGE_STORE_PATH` | `~/GithubProjects/dynamic-worlock/data/knowledge_store.json` |
| `DynamicWorlockActivator` | `DYNAMIC_WORLOCK_CONFLICTS_PATH` | `~/GithubProjects/dynamic-worlock/data/conflicts.json` |

## Activation contract (for new activators)

A new project activator must:
1. Subclass `intel.activation.base.BaseActivator`.
2. Set `project_name` (string matching the `project` field in claim records).
3. Implement `check_readiness()` (returns `ActivationResult(success, project, claim_count, error)`).
4. Implement `activate(claims: list[dict])` (returns `ActivationResult`).
5. Accept env-var overrides for any hardcoded paths via `os.environ.get()` in `__init__`.
6. Support `dry_run=True` (per `BaseActivator` convention).
7. Register the class in `intel/activation/factory.py` with both hyphen and underscore aliases.

## Consumers

- `DarojaAI/research-orchestrator` — imports `intel.activation.factory.get_activator` after `pip install intelligent-feed>=0.1.0`. Pre-`0.1.0` deployments use `INTELLIGENT_FEED_PATH` (sys.path injection); the env var is deprecated and will be removed in `0.3.0`. See `research-orchestrator#1` for the consumer-side migration plan.
- `DarojaAI/globalbitings` — receives claims from `GlobalBitingsActivator` (writes to `extraction_log.jsonl`).
- `DarojaAI/bond-nexus` — receives claims from `BondNexusActivator` (writes to `conventions.yaml`).
- `DarojaAI/rag_research_tool` — receives claims from `RagResearchActivator` (writes to `triplets.json`).
- `DarojaAI/dynamic-worlock` — **PRIVATE.** Per the operator (2026-06-14), the repo is intentionally kept for development of a knowledge repository for sporting events. Not visible to the public `gh` token, but it exists. The activator is shipped and will work once the target data files exist at the configured paths (env-var-overridable).

## Related

- `DarojaAI/.github/GOVERNANCE.md` — org governance.
- `DarojaAI/.github/docs/CI-CD-STANDARDS.md` — org CI standards.
- `DarojaAI/.github/docs/AGENTS-TEMPLATE.md` — template this file follows (RFC #1).
- `DarojaAI/darojaai_architect/OPEN_QUESTIONS.md` — org-wide open questions; Q14–Q17 track this repo.
- `DarojaAI/darojaai_architect/memory/2026-06-14-intelligent-feed-take.md` — the deep-read take that led to this AGENTS.md.
- `DarojaAI/research-orchestrator/CLAUDE.md` — consumer side; describes the `INTELLIGENT_FEED_PATH` contract.
- `DarojaAI/rag_research_tool/docs/research-pipeline-plan.md` — original 4-phase plan that Phase 4 of this repo implements.
