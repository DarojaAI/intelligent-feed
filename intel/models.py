"""Intelligence Feed System - Data Models"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RawItem:
    """Source-agnostic normalized content from fetcher"""
    id: str  # SHA-256 of (source_id + url), hex
    source_id: str
    source_type: str  # "rss" | "pypi_api" | "scrape"
    url: str
    title: str
    body: str
    published_at: datetime
    fetched_at: datetime
    metadata: dict = field(default_factory=dict)


@dataclass
class SuggestedAction:
    """Agent-actionable item"""
    action_id: str  # e.g. "act_001"
    type: str  # "test_integration" | "apply_update" | etc.
    description: str
    priority: int  # 1 = highest
    auto_execute: bool
    params: dict = field(default_factory=dict)


@dataclass
class EnrichedItem:
    """RawItem enriched with LLM-generated content"""
    raw: RawItem
    summary: str  # 1-2 sentence LLM summary
    topic_tags: list[str]
    urgency: str  # "low" | "medium" | "high" | "critical"
    breaking_changes: list[str]
    suggested_actions: list[SuggestedAction]
    relevance_scores: dict[str, float]  # subscription_id -> score
    enriched_at: datetime


@dataclass
class DeliveryConfig:
    """Delivery configuration for a subscription"""
    slack_webhook_url: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""


@dataclass
class StructuredConfig:
    """Configuration for structured/research subscriptions (Phase 4)."""
    # Which project to activate: globalbitings | bond-nexus | rag-research | dynamic-worlock
    project: str = ""
    # Domain hint passed to Cognee cognify() (cuisine, finance, defense, etc.)
    domain: str = "general"
    # Entity types to extract (claim_type filter before activation)
    entity_filters: list[str] = field(default_factory=list)
    # Extra key-value config passed to the activator
    activator_config: dict = field(default_factory=dict)


@dataclass
class Subscription:
    """Subscriber configuration"""
    id: str
    name: str
    subscriber_type: str  # "human" | "agent" | "structured"
    topic_filters: list[str]
    relevance_threshold: float = 0.5
    lookback_days: int = 7
    schedule: str = ""  # cron expression
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    # Phase 4 — structured output config
    structured: StructuredConfig = field(default_factory=StructuredConfig)
