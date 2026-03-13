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
