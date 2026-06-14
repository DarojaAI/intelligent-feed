# Intelligence Feed System

A scheduled pipeline that monitors technical sources (RSS feeds, PyPI), enriches content using Claude API, and delivers curated updates to human subscribers (Markdown digests) and AI agent subscribers (JSON payloads).

## Features

- **Dual delivery modes**: Human-readable Markdown digests and agent-actionable JSON payloads
- **Source-agnostic**: Add new sources without restructuring the core pipeline
- **Idempotent**: Content hashing prevents duplicate deliveries
- **Relevance scoring**: LLM-powered topic matching and urgency detection

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Initialize database
python -m intel.db --init

# Run pipeline once
python -m intel.scheduler --run-now
```

## Configuration

Edit `config.yaml` to modify:
- Sources (RSS feeds, PyPI packages)
- Subscriptions (topic filters, schedules, delivery options)
- Pipeline settings (batch size, model, output paths)

## Architecture

```
Sources → Fetcher → Enricher → Router → Renderers
                    ↓
              (Claude API)
```

See `CLAUDE.md` for detailed architecture documentation.

## MVP Use Cases

1. **Ethical AI Weekly Digest** — Monitors AI ethics RSS feeds, delivers Markdown digest
2. **PyPI Package Monitor** — Tracks Python package releases, delivers JSON payloads to agents

## Output

```
./output/
  digests/          # Human Markdown digests
  agent-payloads/   # Agent JSON payloads
  logs/             # Run logs
```

## Testing

```bash
python -m pytest tests/ -v
```

## Shared library contract

`intelligent-feed` is **also** a shared activation library. Per-project activators live in `intel/activation/` and ship with this repo. Other DarojaAI repos consume them.

### Consumers

- `DarojaAI/research-orchestrator` — imports `intel.activation.factory.get_activator` via the `INTELLIGENT_FEED_PATH` env var. Clone this repo to a local path and export `INTELLIGENT_FEED_PATH=/path/to/intelligent-feed`.
- `DarojaAI/globalbitings`, `bond-nexus`, `rag_research_tool` — receive activated claims in their data files.
- `DarojaAI/dynamic-worlock` — **repo does not currently exist** (see `DarojaAI/darojaai_architect/OPEN_QUESTIONS.md` Q14). Activator is shipped but unused.

### Configuration

Each activator's target paths default to `~/GithubProjects/<project>/...` (operator's local checkout layout). Override per environment with env vars:

| Activator | Env var |
|---|---|
| `GlobalBitingsActivator` | `GLOBALBITINGS_EXTRACTION_LOG_PATH`, `GLOBALBITINGS_RAG_SYNC_CMD` |
| `BondNexusActivator` | `BONDNEXUS_CONVENTIONS_PATH`, `BONDNEXUS_MARKET_SOURCES_PATH` |
| `RagResearchActivator` | `RAG_RESEARCH_TRIPLETS_PATH` |
| `DynamicWorlockActivator` | `DYNAMIC_WORLOCK_KNOWLEDGE_STORE_PATH`, `DYNAMIC_WORLOCK_CONFLICTS_PATH` |

See `AGENTS.md` for the full contract that consumers and contributors should follow.

## License

MIT. See `LICENSE`.
