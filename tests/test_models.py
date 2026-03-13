"""Tests for data models"""

import pytest
from datetime import datetime

from intel.models import RawItem, EnrichedItem, Subscription, DeliveryConfig, SuggestedAction


def test_raw_item_creation():
    """Test creating a RawItem"""
    item = RawItem(
        id="test123",
        source_id="test_source",
        source_type="rss",
        url="https://example.com",
        title="Test Title",
        body="Test body content",
        published_at=datetime.utcnow(),
        fetched_at=datetime.utcnow(),
    )

    assert item.id == "test123"
    assert item.source_id == "test_source"
    assert item.source_type == "rss"


def test_subscription_creation():
    """Test creating a Subscription"""
    delivery = DeliveryConfig(
        slack_webhook_url="https://hooks.slack.com/test",
    )

    sub = Subscription(
        id="sub_test",
        name="Test Subscription",
        subscriber_type="human",
        topic_filters=["ai-safety", "ethical-ai"],
        relevance_threshold=0.5,
        lookback_days=7,
        delivery=delivery,
    )

    assert sub.id == "sub_test"
    assert sub.subscriber_type == "human"
    assert len(sub.topic_filters) == 2
    assert sub.relevance_threshold == 0.5


def test_suggested_action():
    """Test SuggestedAction dataclass"""
    action = SuggestedAction(
        action_id="act_001",
        type="test_integration",
        description="Run tests",
        priority=1,
        auto_execute=True,
        params={"package": "pydantic", "version": "2.0.0"},
    )

    assert action.action_id == "act_001"
    assert action.type == "test_integration"
    assert action.auto_execute is True
    assert action.params["package"] == "pydantic"


def test_enriched_item():
    """Test EnrichedItem"""
    raw = RawItem(
        id="test456",
        source_id="pypi_test",
        source_type="pypi_api",
        url="https://pypi.org/test",
        title="Test Package",
        body="Release notes",
        published_at=datetime.utcnow(),
        fetched_at=datetime.utcnow(),
    )

    action = SuggestedAction(
        action_id="act_001",
        type="apply_update",
        description="Update package",
        priority=1,
        auto_execute=False,
        params={},
    )

    enriched = EnrichedItem(
        raw=raw,
        summary="Test summary",
        topic_tags=["python-packaging", "package-update"],
        urgency="high",
        breaking_changes=["old API removed"],
        suggested_actions=[action],
        relevance_scores={"sub_test": 0.8},
        enriched_at=datetime.utcnow(),
    )

    assert enriched.summary == "Test summary"
    assert enriched.urgency == "high"
    assert len(enriched.suggested_actions) == 1
    assert enriched.relevance_scores["sub_test"] == 0.8
