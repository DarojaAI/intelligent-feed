# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The **Intelligence Feed System** is a scheduled pipeline that monitors technical sources (RSS feeds, PyPI), enriches content using Claude API, and delivers curated updates to human subscribers (Markdown digests) and agent subscribers (JSON payloads).

## Commands

### Running the Pipeline

```bash
# Run the full pipeline once for all subscriptions
python -m intel.scheduler --run-now

# Run only a specific subscription
python -m intel.scheduler --run-now --subscription sub_ethical_ai_human

# Run only the PyPI agent subscription
python -m intel.scheduler --run-now --subscription sub_pypi_agent

# Start the scheduler in production mode (runs on cron schedule from config.yaml)
python -m intel.scheduler
```

### Database

```bash
# Initialize the SQLite database
python -m intel.db --init
```

### Outcomes API (optional)

```bash
# Start FastAPI server for agent outcome callbacks
uvicorn intel.api.outcomes:app --port 8080
```

### Dependencies

```bash
pip install -r requirements.txt
```

### Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_config.py -v

# Run a specific test
python -m pytest tests/test_config.py::test_config_loads -v
```

### Database

```bash
# Initialize database
python -m intel.db --init
# Or using the CLI module
python -m intel.db_cli --init
```

## Architecture

### Data Flow

1. **Scheduler** triggers pipeline runs on cron (default: daily 06:00 UTC)
2. **Fetcher** pulls raw content from RSS feeds and PyPI API, deduplicates by content hash
3. **Enricher** calls Claude API to generate summaries, topic tags, relevance scores, and action hints
4. **Router** matches enriched items to subscriptions by topic filters and relevance threshold
5. **Renderers** output:
   - Human: Markdown digest written to `./output/digests/`
   - Agent: JSON payload written to `./output/agent-payloads/`

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `intel/fetcher.py` | Fetch and normalize content from RSS/PyPI sources |
| `intel/enricher.py` | Call Claude API for item enrichment |
| `intel/router.py` | Match enriched items to subscriptions |
| `intel/scheduler.py` | APScheduler setup and pipeline orchestration |
| `intel/config.py` | Load config.yaml with env var overrides |
| `intel/db.py` | SQLite persistence layer |
| `intel/renderers/human.py` | Markdown digest renderer |
| `intel/renderers/agent.py` | JSON payload renderer |
| `intel/api/outcomes.py` | FastAPI endpoint for agent outcome callbacks |

### Data Models

- **RawItem**: Source-agnostic normalized content from fetcher
- **EnrichedItem**: RawItem + LLM-generated summary, tags, urgency, relevance scores, suggested actions
- **Subscription**: Topic filters, relevance threshold, delivery config
- **SuggestedAction**: Agent-actionable items with priority and auto-execute flag

### Database Schema

SQLite with tables: `raw_items`, `enriched_items`, `deliveries`, `agent_outcomes`

### Configuration

All config in `config.yaml`:
- `pipeline`: db_path, output_dir, log_level, anthropic_model
- `sources`: RSS feed and PyPI package definitions
- `subscriptions`: human and agent subscriber configs with topic_filters and schedules

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `SLACK_WEBHOOK_URL` | No | Slack webhook for human digests |
| `AGENT_WEBHOOK_URL` | No | Webhook for agent payloads |
| `AGENT_WEBHOOK_SECRET` | No | HMAC secret for agent webhook signature |
| `OUTCOMES_API_PORT` | No | FastAPI port (default: 8080) |

## MVP Use Cases

1. **Human: Ethical AI Weekly Digest** — RSS sources → Markdown digest → Slack webhook
2. **Agent: PyPI Package Monitor** — PyPI API → JSON payloads → webhook delivery

## Output Structure

```
./output/
  digests/
    sub_ethical_ai_human_2026-03-13.md
  agent-payloads/
    sub_pypi_agent_<item_id>_2026-03-13.json
  logs/
    run_2026-03-13.log
```
