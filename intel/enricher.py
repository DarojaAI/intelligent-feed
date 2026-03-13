"""LLM enrichment layer - enriches items using Claude API"""

import json
import logging
from datetime import datetime
from typing import Optional

import anthropic

from intel.config import Config
from intel.models import EnrichedItem, RawItem, SuggestedAction

logger = logging.getLogger(__name__)

# Topic vocabulary for human items
HUMAN_TOPICS = [
    "ethical-ai", "ai-safety", "ai-governance", "ai-policy", "bias-fairness",
    "responsible-ai", "ai-incidents", "python-packaging", "package-update",
    "breaking-change", "security", "machine-learning", "llm", "developer-tooling"
]

# Topic vocabulary for agent/PyPI items
AGENT_TOPICS = [
    "python-packaging", "package-update", "breaking-change",
    "security", "deprecation", "performance", "bug-fix"
]

# Action types for agent payloads
ACTION_TYPES = [
    "test_integration", "apply_update", "notify_human",
    "create_ticket", "flag_for_review", "run_eval"
]


class Enricher:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        self.model = self.config.anthropic_model

    def enrich(self, items: list[RawItem], subscription_type: str = "human") -> list[EnrichedItem]:
        """Enrich a list of raw items"""
        enriched = []

        for raw_item in items:
            try:
                if raw_item.source_type == "pypi_api":
                    enriched_item = self._enrich_pypi(raw_item)
                else:
                    enriched_item = self._enrich_human(raw_item)
                enriched.append(enriched_item)
            except Exception as e:
                logger.error(f"Error enriching item {raw_item.id}: {e}")
                continue

        return enriched

    def _enrich_human(self, raw_item: RawItem) -> EnrichedItem:
        """Enrich a human-facing item (RSS article)"""
        prompt = f"""System:
You are an expert technical analyst. Given an article or item, return a JSON object with:
- "summary": string — 1–2 sentence plain-English summary
- "topic_tags": array of strings — relevant topic tags from this controlled vocabulary:
  {json.dumps(HUMAN_TOPICS)}
  Include all that apply. Maximum 5 tags.
- "urgency": string — one of: "low", "medium", "high", "critical"
  low = informational, medium = worth noting, high = action or attention needed soon,
  critical = breaking or time-sensitive
- "breaking_changes": array of strings — list any breaking changes mentioned. Empty array if none.

Return ONLY valid JSON. No markdown fences, no preamble.

User:
Title: {raw_item.title}
Source: {raw_item.source_id}
Published: {raw_item.published_at.isoformat()}
Content: {raw_item.body[:3000]}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        result = json.loads(response.content[0].text)

        return EnrichedItem(
            raw=raw_item,
            summary=result.get("summary", ""),
            topic_tags=result.get("topic_tags", [])[:5],
            urgency=result.get("urgency", "low"),
            breaking_changes=result.get("breaking_changes", []),
            suggested_actions=[],  # Empty for human items
            relevance_scores={},
            enriched_at=datetime.utcnow(),
        )

    def _enrich_pypi(self, raw_item: RawItem) -> EnrichedItem:
        """Enrich a PyPI package release"""
        package = raw_item.metadata.get("package", "")
        version = raw_item.metadata.get("version", "")
        prev_version = raw_item.metadata.get("prev_version", "")

        prompt = f"""System:
You are a software dependency analyst. Given a Python package release, return a JSON object with:
- "summary": string — 1–2 sentence summary of what changed
- "topic_tags": array of strings — from: {json.dumps(AGENT_TOPICS)}
- "urgency": string — one of: "low", "medium", "high", "critical"
  Use "high" if there are breaking changes or deprecations. Use "critical" for security issues.
- "breaking_changes": array of strings — specific breaking changes. Empty array if none.
- "suggested_actions": array of objects, each with:
    - "action_id": string — "act_001", "act_002", etc.
    - "type": string — one of: {json.dumps(ACTION_TYPES)}
    - "description": string — concrete description of the action
    - "priority": integer — 1 is highest
    - "auto_execute": boolean — true only if the action is safe without human review
      (e.g. running tests is safe; merging a PR is not)
    - "params": object — relevant parameters (package, version, etc.)

Return ONLY valid JSON. No markdown fences, no preamble.

User:
Package: {package}
Version: {version}
Previous version: {prev_version}
Release notes / changelog: {raw_item.body[:3000]}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        result = json.loads(response.content[0].text)

        # Convert suggested actions to dataclass
        suggested_actions = []
        for act in result.get("suggested_actions", []):
            suggested_actions.append(SuggestedAction(
                action_id=act.get("action_id", ""),
                type=act.get("type", ""),
                description=act.get("description", ""),
                priority=act.get("priority", 3),
                auto_execute=act.get("auto_execute", False),
                params=act.get("params", {}),
            ))

        return EnrichedItem(
            raw=raw_item,
            summary=result.get("summary", ""),
            topic_tags=result.get("topic_tags", []),
            urgency=result.get("urgency", "low"),
            breaking_changes=result.get("breaking_changes", []),
            suggested_actions=suggested_actions,
            relevance_scores={},
            enriched_at=datetime.utcnow(),
        )

    def score_relevance(self, item: EnrichedItem, subscription) -> float:
        """Compute relevance score for a subscription"""
        matched_tags = set(item.topic_tags) & set(subscription.topic_filters)
        if not matched_tags:
            return 0.0

        tag_score = len(matched_tags) / len(subscription.topic_filters)
        urgency_boost = {"low": 0.0, "medium": 0.05, "high": 0.15, "critical": 0.25}
        return min(1.0, tag_score + urgency_boost.get(item.urgency, 0.0))
