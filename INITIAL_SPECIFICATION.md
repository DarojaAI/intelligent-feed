# Intelligence Feed System — Build Specification

**Version:** 1.0  
**Date:** 2026-03-13  
**Target:** Claude Code initial build  
**Priority scope:** Two MVP use cases (see §2)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [MVP Scope & Prioritisation](#2-mvp-scope--prioritisation)
3. [Architecture](#3-architecture)
4. [Data Models](#4-data-models)
5. [Component Specifications](#5-component-specifications)
6. [Payload Schemas](#6-payload-schemas)
7. [Delivery Modes](#7-delivery-modes)
8. [Configuration & Subscriptions](#8-configuration--subscriptions)
9. [Tech Stack](#9-tech-stack)
10. [Directory Structure](#10-directory-structure)
11. [Environment Variables](#11-environment-variables)
12. [Running the System](#12-running-the-system)
13. [Future Extensibility](#13-future-extensibility)

---

## 1. System Overview

The **Intelligence Feed System** is a scheduled pipeline that monitors technical sources across the internet, enriches raw content using an LLM, and delivers curated updates to two classes of subscriber:

- **Human subscribers** receive a readable digest (email/Slack/Markdown file) summarising what happened and why it matters.
- **Agent subscribers** receive a structured JSON payload with action hints they can act on autonomously or escalate to a human.

The system is source-agnostic by design. New sources, topics, and subscriber types can be added without restructuring the core pipeline.

### Core principles

- **Pull-based, scheduled** — the pipeline runs on a cron schedule (default: daily at 06:00 UTC). No real-time streaming in v1.
- **Idempotent** — every item is content-hashed on ingest; re-fetching the same content produces no duplicate deliveries.
- **Dual-mode output** — the same enriched item can fan out to both human and agent subscribers simultaneously.
- **Feedback loop** — agents report outcomes back to the system; this data improves relevance scoring over time.
- **Self-describing payloads** — agent payloads carry enough context that the agent can decide and act without additional lookups.

---

## 2. MVP Scope & Prioritisation

Build the following two use cases end-to-end before adding anything else.

### Use Case 1 — Human: Ethical AI Weekly Digest

| Field | Value |
|---|---|
| Subscriber type | Human |
| Topic | Ethical AI |
| Sources | RSS feeds from major AI labs, policy organisations, academic preprint servers, and tech news outlets (see §5.1) |
| Lookback window | 7 days |
| Schedule | Weekly, Monday 07:00 UTC |
| Delivery | Markdown file written to `./output/digests/` + optional Slack webhook |
| Output format | Structured Markdown digest with executive summary, categorised items, and source links |

**What "ethical AI" covers for filtering purposes:**

- AI safety and alignment research
- AI governance, policy, and regulation
- Bias, fairness, and accountability in AI systems
- Responsible AI deployment practices
- AI rights and societal impact commentary
- Notable incidents or controversies involving AI systems

### Use Case 2 — Agent: PyPI Package Update Monitor

| Field | Value |
|---|---|
| Subscriber type | AI agent |
| Topic | Python package releases on PyPI |
| Sources | PyPI RSS feed, PyPI JSON API per tracked package |
| Lookback window | 24 hours |
| Schedule | Daily, 06:00 UTC |
| Delivery | JSON payload file written to `./output/agent-payloads/` + optional webhook POST |
| Output format | Structured JSON per the agent payload schema (see §6.2) |

**Tracked packages for MVP** (configurable in `config.yaml`):

```
pydantic, fastapi, anthropic, langchain, openai, httpx, 
sqlalchemy, alembic, pytest, ruff, mypy, uvicorn
```

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      SOURCES LAYER                       │
│  RSS/Atom feeds │ PyPI RSS │ PyPI JSON API │ Web scrape  │
└────────────────────────┬────────────────────────────────┘
                         │ raw fetch
┌────────────────────────▼────────────────────────────────┐
│                     INGEST LAYER                         │
│  1. Fetch & normalise raw items                          │
│  2. Deduplicate by content hash                          │
│  3. Persist to local SQLite store                        │
└────────────────────────┬────────────────────────────────┘
                         │ new items only
┌────────────────────────▼────────────────────────────────┐
│                  AI ENRICHMENT LAYER                     │
│  Claude API (claude-sonnet-4-20250514)                   │
│  - Summarise item (1–2 sentences)                        │
│  - Classify topic tags                                   │
│  - Score relevance per subscription                      │
│  - Identify breaking changes / urgency (agent use)       │
│  - Generate action hints (agent use)                     │
└────────────────────────┬────────────────────────────────┘
                         │ enriched items
┌────────────────────────▼────────────────────────────────┐
│               SUBSCRIPTION ROUTER                        │
│  Match enriched items → subscribers by topic filter      │
│  Fan out to: human delivery | agent delivery             │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
┌──────────────▼──────────┐  ┌────────────▼──────────────┐
│    HUMAN DELIVERY        │  │    AGENT DELIVERY          │
│  Render Markdown digest  │  │  Serialise JSON payload    │
│  Write to ./output/      │  │  Write to ./output/        │
│  POST to Slack webhook   │  │  POST to agent webhook     │
└──────────────────────────┘  └───────────────────────────┘
```

### Data flow summary

1. The **scheduler** (`scheduler.py`) triggers pipeline runs on cron.
2. The **fetcher** (`fetcher.py`) pulls raw content from each configured source, normalises it into a common `RawItem` struct, and passes new items (not seen before) to the enrichment step.
3. The **enricher** (`enricher.py`) batches items and calls the Claude API to produce an `EnrichedItem` for each.
4. The **router** (`router.py`) loads the subscription registry and matches each `EnrichedItem` to one or more subscriptions.
5. The **human renderer** (`renderers/human.py`) aggregates matched items for a human subscription into a Markdown digest.
6. The **agent renderer** (`renderers/agent.py`) converts each matched item into an agent JSON payload.
7. Both renderers write their output to `./output/` and optionally POST to a configured webhook.

---

## 4. Data Models

All models use Python dataclasses. SQLite (via the `sqlite3` stdlib module) is used for persistence. No ORM in v1.

### 4.1 RawItem

Produced by the fetcher. Source-agnostic normalised representation.

```python
@dataclass
class RawItem:
    id: str                  # SHA-256 of (source_id + url), hex
    source_id: str           # e.g. "pypi_rss", "anthropic_blog"
    source_type: str         # enum: "rss" | "pypi_api" | "scrape"
    url: str
    title: str
    body: str                # full text or best available excerpt
    published_at: datetime   # UTC; parsed from feed or HTTP headers
    fetched_at: datetime     # UTC; time of this fetch
    metadata: dict           # source-specific extras (e.g. pypi version, author)
```

### 4.2 EnrichedItem

Produced by the enricher. Extends RawItem with LLM-generated fields.

```python
@dataclass
class EnrichedItem:
    raw: RawItem
    summary: str             # 1–2 sentence LLM summary
    topic_tags: list[str]    # e.g. ["ethical-ai", "governance", "eu-ai-act"]
    urgency: str             # enum: "low" | "medium" | "high" | "critical"
    breaking_changes: list[str]   # empty list if none
    suggested_actions: list[SuggestedAction]  # empty for human-only items
    relevance_scores: dict[str, float]  # subscription_id → 0.0–1.0
    enriched_at: datetime
```

### 4.3 SuggestedAction

Used in agent payloads only.

```python
@dataclass
class SuggestedAction:
    action_id: str           # e.g. "act_001"
    type: str                # enum: see §6.2
    description: str
    priority: int            # 1 = highest
    auto_execute: bool       # True = agent may act without approval
    params: dict             # action-specific parameters
```

### 4.4 Subscription

Loaded from `config.yaml`. Describes a single subscriber and their filters.

```python
@dataclass
class Subscription:
    id: str                  # e.g. "sub_ethical_ai_human"
    name: str
    subscriber_type: str     # enum: "human" | "agent"
    topic_filters: list[str] # topic tags that qualify an item for this sub
    relevance_threshold: float  # minimum score to include (default 0.5)
    lookback_days: int
    delivery: DeliveryConfig
```

### 4.5 SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS raw_items (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    published_at TEXT NOT NULL,   -- ISO 8601
    fetched_at TEXT NOT NULL,
    metadata TEXT NOT NULL        -- JSON blob
);

CREATE TABLE IF NOT EXISTS enriched_items (
    id TEXT PRIMARY KEY,          -- same as raw_items.id
    summary TEXT NOT NULL,
    topic_tags TEXT NOT NULL,     -- JSON array
    urgency TEXT NOT NULL,
    breaking_changes TEXT NOT NULL,  -- JSON array
    suggested_actions TEXT NOT NULL, -- JSON array
    relevance_scores TEXT NOT NULL,  -- JSON object
    enriched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY,          -- ULID
    subscription_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    delivery_mode TEXT NOT NULL,  -- "file" | "webhook"
    status TEXT NOT NULL          -- "ok" | "failed"
);

CREATE TABLE IF NOT EXISTS agent_outcomes (
    id TEXT PRIMARY KEY,          -- ULID
    payload_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    outcome TEXT NOT NULL,        -- "executed" | "skipped" | "escalated" | "failed"
    detail TEXT,                  -- free-text from agent
    reported_at TEXT NOT NULL
);
```

---

## 5. Component Specifications

### 5.1 Fetcher (`fetcher.py`)

The fetcher is responsible for pulling content from sources and returning a list of `RawItem` objects containing only items not already in the database.

#### Source definitions (MVP)

Each source is declared in `config.yaml` under `sources:`. Built-in source types:

**`rss`** — parses an RSS/Atom feed. Uses `feedparser`.

```yaml
- id: anthropic_blog
  type: rss
  url: https://www.anthropic.com/rss.xml
  topic_hint: ethical-ai

- id: deepmind_blog
  type: rss
  url: https://deepmind.google/blog/rss.xml
  topic_hint: ethical-ai

- id: mit_ai_ethics
  type: rss
  url: https://aiethics.mit.edu/feed/
  topic_hint: ethical-ai

- id: ai_now_institute
  type: rss
  url: https://ainowinstitute.org/feed
  topic_hint: ethical-ai

- id: partnership_on_ai
  type: rss
  url: https://partnershiponai.org/feed/
  topic_hint: ethical-ai

- id: ieee_spectrum_ai
  type: rss
  url: https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss
  topic_hint: ethical-ai

- id: pypi_rss
  type: rss
  url: https://pypi.org/rss/updates.xml
  topic_hint: python-packaging
```

**`pypi_package`** — calls the PyPI JSON API for a specific package. Returns the latest release metadata.

```yaml
- id: pypi_pydantic
  type: pypi_package
  package: pydantic
  topic_hint: python-packaging
```

One source entry per tracked package (generated programmatically from the `tracked_packages` list in config).

#### Fetcher behaviour

- Fetch all configured sources.
- Parse each item into `RawItem`.
- Compute `id = sha256(source_id + url)`.
- Query the database: skip items whose `id` already exists in `raw_items`.
- Return only new items.
- On HTTP errors: log the error, skip the source, do not crash the pipeline.
- Respect `lookback_days` from the matching subscription: discard items with `published_at` older than `now - lookback_days`.

### 5.2 Enricher (`enricher.py`)

Calls the Anthropic API to enrich each `RawItem` into an `EnrichedItem`.

#### Batching

- Process items in batches of 10 (configurable).
- Use a single Claude API call per item (not batched into one call — each item needs its own structured response).
- Implement exponential backoff with 3 retries on API errors.

#### Claude prompt — Human item enrichment

```
System:
You are an expert technical analyst. Given an article or item, return a JSON object with:
- "summary": string — 1–2 sentence plain-English summary
- "topic_tags": array of strings — relevant topic tags from this controlled vocabulary: 
  [ethical-ai, ai-safety, ai-governance, ai-policy, bias-fairness, responsible-ai, 
   ai-incidents, python-packaging, package-update, breaking-change, security, 
   machine-learning, llm, developer-tooling]
  Include all that apply. Maximum 5 tags.
- "urgency": string — one of: "low", "medium", "high", "critical"
  low = informational, medium = worth noting, high = action or attention needed soon, 
  critical = breaking or time-sensitive
- "breaking_changes": array of strings — list any breaking changes mentioned. Empty array if none.

Return ONLY valid JSON. No markdown fences, no preamble.

User:
Title: {title}
Source: {source_id}
Published: {published_at}
Content: {body[:3000]}
```

#### Claude prompt — Agent item enrichment (PyPI)

```
System:
You are a software dependency analyst. Given a Python package release, return a JSON object with:
- "summary": string — 1–2 sentence summary of what changed
- "topic_tags": array of strings — from: [python-packaging, package-update, breaking-change, 
  security, deprecation, performance, bug-fix]
- "urgency": string — one of: "low", "medium", "high", "critical"
  Use "high" if there are breaking changes or deprecations. Use "critical" for security issues.
- "breaking_changes": array of strings — specific breaking changes. Empty array if none.
- "suggested_actions": array of objects, each with:
    - "action_id": string — "act_001", "act_002", etc.
    - "type": string — one of: "test_integration", "apply_update", "notify_human", 
      "create_ticket", "flag_for_review", "run_eval"
    - "description": string — concrete description of the action
    - "priority": integer — 1 is highest
    - "auto_execute": boolean — true only if the action is safe without human review 
      (e.g. running tests is safe; merging a PR is not)
    - "params": object — relevant parameters (package, version, etc.)

Return ONLY valid JSON. No markdown fences, no preamble.

User:
Package: {package_name}
Version: {version}
Previous version: {prev_version}
Release notes / changelog: {body[:3000]}
```

#### Relevance scoring

After obtaining the enriched tags and urgency, compute a relevance score for each active subscription:

```python
def score_relevance(item: EnrichedItem, subscription: Subscription) -> float:
    matched_tags = set(item.topic_tags) & set(subscription.topic_filters)
    if not matched_tags:
        return 0.0
    tag_score = len(matched_tags) / len(subscription.topic_filters)
    urgency_boost = {"low": 0.0, "medium": 0.05, "high": 0.15, "critical": 0.25}
    return min(1.0, tag_score + urgency_boost.get(item.urgency, 0.0))
```

### 5.3 Router (`router.py`)

Loads all subscriptions from config and matches enriched items to them.

```python
def route(items: list[EnrichedItem], subscriptions: list[Subscription]) -> dict[str, list[EnrichedItem]]:
    """Returns a mapping of subscription_id → list of matching EnrichedItems."""
    result = defaultdict(list)
    for item in items:
        for sub in subscriptions:
            score = item.relevance_scores.get(sub.id, 0.0)
            if score >= sub.relevance_threshold:
                result[sub.id].append(item)
    return result
```

### 5.4 Human Renderer (`renderers/human.py`)

Generates a Markdown digest from a list of enriched items for a human subscription.

#### Digest structure

```markdown
# Ethical AI — Weekly Digest
*Week of 2026-03-09 to 2026-03-13 · {N} items*

---

## Executive Summary

{2–3 sentence LLM-generated overview of the week's themes, written fresh from the 
 set of item summaries. One additional Claude API call per digest.}

---

## Highlights

{Items with urgency = high or critical, sorted by relevance score descending}

### {Item title}
**Source:** {source_id} · **Published:** {date} · **Urgency:** 🔴 High  
**Tags:** `ethical-ai` `ai-governance`

{summary}

[Read more →]({url})

---

## All Items This Week

{All remaining items, grouped by first topic tag, urgency medium and low}

### AI Governance & Policy

#### {title}
...

---

*Generated by Intelligence Feed System · {run_id} · {timestamp}*
*To change your subscription preferences, edit config.yaml*
```

#### Executive summary prompt

```
System:
You are a strategic analyst writing for a technically literate but non-specialist audience.
Given a list of article summaries from this week, write a 2–3 sentence executive summary 
that identifies the most important themes and why they matter. Be concrete, not vague. 
Return plain text only — no markdown, no bullet points.

User:
{json.dumps([item.summary for item in items])}
```

#### Output

- Write digest to `./output/digests/{subscription_id}_{run_date}.md`.
- If `delivery.slack_webhook_url` is set, POST to the Slack webhook using the Block Kit format (title block + truncated summary block + link to full file).

### 5.5 Agent Renderer (`renderers/agent.py`)

Serialises each enriched item into a standalone agent payload JSON file per item.

- Write each payload to `./output/agent-payloads/{subscription_id}_{item_id}_{run_date}.json`.
- If `delivery.webhook_url` is set, POST the payload as JSON with `Content-Type: application/json`.
- If the POST fails, write to file anyway and log the failure. Do not retry in v1.

---

## 6. Payload Schemas

### 6.1 Human Digest (Markdown)

See §5.4 for the full template. No formal JSON schema — the output is a rendered Markdown file.

### 6.2 Agent JSON Payload

Every agent payload conforms to this schema. All fields are required unless marked optional.

```json
{
  "schema_version": "1.0",
  "id": "upd_<ulid>",
  "created_at": "<ISO 8601 UTC>",
  "pipeline_run": "run_<YYYY-MM-DD>",

  "event": {
    "type": "<package_update | article | vulnerability | model_release | api_change | deprecation>",
    "source": "<source_id>",
    "title": "<string>",
    "summary": "<1–2 sentence LLM summary>",
    "url": "<string>",
    "raw_content_ref": "<optional: file path or S3 URI to full raw item>"
  },

  "relevance": {
    "score": "<float 0.0–1.0>",
    "urgency": "<low | medium | high | critical>",
    "topics": ["<tag>", "..."],
    "matched_subscription": "<subscription_id>",
    "relevance_reason": "<optional string: why this matched>"
  },

  "suggested_actions": [
    {
      "action_id": "act_001",
      "type": "<test_integration | apply_update | notify_human | create_ticket | flag_for_review | run_eval>",
      "description": "<string>",
      "priority": 1,
      "auto_execute": true,
      "params": {
        "<key>": "<value>"
      }
    }
  ],

  "context": {
    "breaking_changes": ["<string>", "..."],
    "prev_version": "<optional string>",
    "new_version": "<optional string>",
    "migration_guide_url": "<optional string>",
    "affected_repos": "<optional: list of known affected repos>",
    "additional_notes": "<optional string>"
  },

  "callbacks": {
    "report_outcome": "<optional: URL to POST agent outcome report>",
    "acknowledge": "<optional: URL to POST acknowledgement>",
    "escalate": "<optional: URL to POST escalation request>"
  }
}
```

#### Example — pydantic 2.8.0 release

```json
{
  "schema_version": "1.0",
  "id": "upd_01J9XK2M4PQRSTUVWXYZ",
  "created_at": "2026-03-13T06:00:00Z",
  "pipeline_run": "run_2026-03-13",

  "event": {
    "type": "package_update",
    "source": "pypi_pydantic",
    "title": "pydantic 2.8.0 released",
    "summary": "Adds model_rebuild() performance improvements and deprecates the v1 compatibility layer, which will be removed in 2.9.",
    "url": "https://pypi.org/project/pydantic/2.8.0/"
  },

  "relevance": {
    "score": 0.91,
    "urgency": "high",
    "topics": ["python-packaging", "package-update", "breaking-change", "deprecation"],
    "matched_subscription": "sub_pypi_agent",
    "relevance_reason": "Package is in tracked list; deprecation affects v1 compat layer used in known projects."
  },

  "suggested_actions": [
    {
      "action_id": "act_001",
      "type": "test_integration",
      "description": "Run test suite against pydantic 2.8.0 in a sandboxed environment",
      "priority": 1,
      "auto_execute": true,
      "params": {
        "package": "pydantic",
        "version": "2.8.0",
        "install_cmd": "pip install pydantic==2.8.0",
        "test_cmd": "pytest tests/"
      }
    },
    {
      "action_id": "act_002",
      "type": "notify_human",
      "description": "Alert engineering team: v1 compat layer deprecated, migration required before 2.9",
      "priority": 2,
      "auto_execute": false,
      "params": {
        "channel": "slack",
        "mention": "@eng-platform",
        "urgency": "high"
      }
    }
  ],

  "context": {
    "breaking_changes": [
      "v1 compatibility layer deprecated; scheduled for removal in pydantic 2.9"
    ],
    "prev_version": "2.7.4",
    "new_version": "2.8.0",
    "migration_guide_url": "https://docs.pydantic.dev/2.8/migration/",
    "affected_repos": [],
    "additional_notes": ""
  },

  "callbacks": {
    "report_outcome": null,
    "acknowledge": null,
    "escalate": null
  }
}
```

---

## 7. Delivery Modes

### 7.1 File delivery (always on)

All output is written to disk regardless of other delivery settings. This ensures the system works with no external dependencies.

```
./output/
  digests/
    sub_ethical_ai_human_2026-03-13.md
  agent-payloads/
    sub_pypi_agent_<item_id>_2026-03-13.json
  logs/
    run_2026-03-13.log
```

### 7.2 Slack webhook (human subscriptions, optional)

Set `delivery.slack_webhook_url` in the subscription config. The renderer POSTs a Slack Block Kit message:

```json
{
  "blocks": [
    {
      "type": "header",
      "text": { "type": "plain_text", "text": "🧠 Ethical AI — Weekly Digest" }
    },
    {
      "type": "section",
      "text": { "type": "mrkdwn", "text": "*{N} items this week*\n{executive_summary}" }
    },
    {
      "type": "section",
      "text": { "type": "mrkdwn", "text": "*Highlights:*\n{top 3 item titles with links}" }
    },
    {
      "type": "context",
      "elements": [{ "type": "mrkdwn", "text": "Full digest: `output/digests/{filename}`" }]
    }
  ]
}
```

### 7.3 Webhook delivery (agent subscriptions, optional)

Set `delivery.webhook_url` in the subscription config. The renderer POSTs each agent payload as `application/json`. A shared secret can be set via `delivery.webhook_secret` — if set, include an `X-Intel-Signature: sha256=<hmac>` header.

### 7.4 Agent outcome callbacks

When an agent processes a payload and reports back (via `callbacks.report_outcome`), the system receives a POST to `/api/outcomes`. In v1, implement this as a simple FastAPI endpoint that writes to the `agent_outcomes` table. The endpoint is optional — the system functions without it.

Expected outcome report body:

```json
{
  "payload_id": "upd_01J9XK2M4P...",
  "action_id": "act_001",
  "outcome": "executed",
  "detail": "Tests passed: 47/47. No failures against pydantic 2.8.0."
}
```

---

## 8. Configuration & Subscriptions

All configuration lives in a single `config.yaml` file at the project root.

```yaml
pipeline:
  db_path: ./data/intel.db
  output_dir: ./output
  log_level: INFO
  anthropic_model: claude-sonnet-4-20250514
  enrichment_batch_size: 10

sources:
  - id: anthropic_blog
    type: rss
    url: https://www.anthropic.com/rss.xml
    topic_hint: ethical-ai

  - id: mit_ai_ethics
    type: rss
    url: https://aiethics.mit.edu/feed/
    topic_hint: ethical-ai

  - id: ai_now_institute
    type: rss
    url: https://ainowinstitute.org/feed
    topic_hint: ethical-ai

  - id: ieee_spectrum_ai
    type: rss
    url: https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss
    topic_hint: ethical-ai

  - id: pypi_rss
    type: rss
    url: https://pypi.org/rss/updates.xml
    topic_hint: python-packaging

tracked_packages:
  - pydantic
  - fastapi
  - anthropic
  - langchain
  - openai
  - httpx
  - sqlalchemy
  - alembic
  - pytest
  - ruff
  - mypy
  - uvicorn

subscriptions:
  - id: sub_ethical_ai_human
    name: Ethical AI Weekly Digest
    subscriber_type: human
    topic_filters:
      - ethical-ai
      - ai-safety
      - ai-governance
      - ai-policy
      - bias-fairness
      - responsible-ai
      - ai-incidents
    relevance_threshold: 0.4
    lookback_days: 7
    schedule: "0 7 * * 1"   # Monday 07:00 UTC
    delivery:
      slack_webhook_url: ""  # set via env var SLACK_WEBHOOK_URL or leave blank

  - id: sub_pypi_agent
    name: PyPI Package Monitor
    subscriber_type: agent
    topic_filters:
      - python-packaging
      - package-update
      - breaking-change
      - security
      - deprecation
    relevance_threshold: 0.3
    lookback_days: 1
    schedule: "0 6 * * *"   # Daily 06:00 UTC
    delivery:
      webhook_url: ""        # set via env var AGENT_WEBHOOK_URL or leave blank
      webhook_secret: ""     # set via env var AGENT_WEBHOOK_SECRET or leave blank
```

---

## 9. Tech Stack

| Layer | Library / Tool | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| HTTP client | `httpx` | async-capable, used for feed fetching and webhook delivery |
| Feed parsing | `feedparser` | handles RSS and Atom |
| LLM API | `anthropic` SDK | `claude-sonnet-4-20250514` |
| Database | `sqlite3` (stdlib) | no ORM; raw SQL via helper module |
| Scheduling | `APScheduler` | in-process cron scheduler; or run via OS cron + CLI entrypoint |
| Config | `PyYAML` | `config.yaml` |
| ID generation | `python-ulid` | for payload and delivery IDs |
| Outcome API | `fastapi` + `uvicorn` | optional; only needed if agents will POST outcomes back |
| Logging | `logging` (stdlib) | structured logs to file and stdout |

### Dependencies (`requirements.txt`)

```
anthropic>=0.25.0
feedparser>=6.0.11
httpx>=0.27.0
PyYAML>=6.0.1
APScheduler>=3.10.4
python-ulid>=2.0.0
fastapi>=0.111.0
uvicorn>=0.29.0
```

---

## 10. Directory Structure

```
intel-feed/
├── config.yaml                  # all configuration
├── requirements.txt
├── .env                         # secrets (never commit)
├── README.md
│
├── intel/                       # main package
│   ├── __init__.py
│   ├── models.py                # RawItem, EnrichedItem, Subscription, etc.
│   ├── db.py                    # SQLite helpers (init_db, insert, query)
│   ├── fetcher.py               # source fetching + normalisation
│   ├── enricher.py              # Claude API enrichment
│   ├── router.py                # subscription matching
│   ├── scheduler.py             # APScheduler setup + run loop
│   ├── config.py                # config.yaml loader + env var overlay
│   ├── renderers/
│   │   ├── __init__.py
│   │   ├── human.py             # Markdown digest renderer
│   │   └── agent.py             # JSON payload renderer
│   └── api/
│       ├── __init__.py
│       └── outcomes.py          # FastAPI outcome callback endpoint (optional)
│
├── data/
│   └── intel.db                 # SQLite database (gitignored)
│
├── output/
│   ├── digests/                 # human Markdown digests
│   ├── agent-payloads/          # agent JSON payloads
│   └── logs/                   # run logs
│
└── tests/
    ├── test_fetcher.py
    ├── test_enricher.py
    ├── test_router.py
    └── test_renderers.py
```

---

## 11. Environment Variables

Secrets are never stored in `config.yaml`. Use a `.env` file or inject via the environment.

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `SLACK_WEBHOOK_URL` | No | Slack incoming webhook for human digest delivery |
| `AGENT_WEBHOOK_URL` | No | Webhook URL to POST agent payloads to |
| `AGENT_WEBHOOK_SECRET` | No | HMAC secret for agent webhook signature header |
| `OUTCOMES_API_PORT` | No | Port for the outcomes FastAPI server (default: 8080) |

Load these in `intel/config.py` using `os.environ` with clear error messages for missing required vars.

---

## 12. Running the System

### One-off run (CLI, recommended for initial dev)

```bash
# Run the full pipeline once for all subscriptions
python -m intel.scheduler --run-now

# Run only a specific subscription
python -m intel.scheduler --run-now --subscription sub_ethical_ai_human

# Run only the PyPI agent subscription
python -m intel.scheduler --run-now --subscription sub_pypi_agent
```

### Scheduled mode (production)

```bash
# Start the APScheduler-based run loop (reads cron from config.yaml)
python -m intel.scheduler
```

### Outcomes API (optional)

```bash
# Start the FastAPI server for receiving agent outcome callbacks
uvicorn intel.api.outcomes:app --port 8080
```

### Database initialisation

```bash
python -m intel.db --init
```

---

## 13. Future Extensibility

The following are explicitly **out of scope for v1** but should not be architecturally blocked:

- **Additional source types** — Twitter/X API, arXiv API, Hacker News, company changelogs via GitHub Releases API. Add by implementing a new fetcher class with a common interface.
- **Additional subscriber types** — currently human and agent. A future `webhook_only` type (no rendering, raw enriched items) could support downstream systems.
- **Semantic topic matching** — v1 uses tag intersection. Replace `score_relevance()` with an embedding-based similarity search (e.g. using the Anthropic embeddings API) for fuzzier, more powerful matching.
- **Web UI** — a simple read-only dashboard showing recent runs, item counts, and delivery status. FastAPI + Jinja2 templates on top of the existing SQLite store.
- **Multi-agent feedback loop** — once `agent_outcomes` table has data, feed it back into the enrichment prompt to improve relevance scoring and action suggestions over time.
- **Digest formats** — email (via SMTP or SendGrid), PDF, or a hosted web page alongside the Markdown file.
- **Rate limiting & cost tracking** — track Claude API token usage per run and surface in logs; add a configurable daily token budget.
- **Source health monitoring** — detect and alert on sources that consistently return errors or empty feeds.

---

*End of specification.*