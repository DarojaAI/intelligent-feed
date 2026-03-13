"""Tests for router module"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from intel.router import Router
from intel.models import EnrichedItem, RawItem, Subscription, DeliveryConfig
from datetime import datetime


def test_router_initialization():
    """Test router can be initialized"""
    with patch('intel.router.Config') as mock_config:
        mock_config.return_value = MagicMock()
        router = Router()
        assert router is not None


def test_route_filters_by_threshold():
    """Test that routing filters by relevance threshold"""
    with patch('intel.router.Config') as mock_config:
        mock_config.return_value = MagicMock()

    with patch('intel.router.Enricher') as mock_enricher:
        mock_enricher_instance = MagicMock()
        mock_enricher_instance.score_relevance = lambda item, sub: 0.8 if sub.id == "sub_high" else 0.3
        mock_enricher.return_value = mock_enricher_instance

        router = Router()

        # Create mock items and subscriptions
        raw = RawItem(
            id="test1", source_id="test", source_type="rss",
            url="http://test.com", title="Test", body="Body",
            published_at=datetime.utcnow(), fetched_at=datetime.utcnow()
        )

        item = EnrichedItem(
            raw=raw, summary="Test", topic_tags=["ai-safety"],
            urgency="high", breaking_changes=[], suggested_actions=[],
            relevance_scores={}, enriched_at=datetime.utcnow()
        )

        sub_high = Subscription(
            id="sub_high", name="High Threshold", subscriber_type="human",
            topic_filters=["ai-safety"], relevance_threshold=0.7
        )

        sub_low = Subscription(
            id="sub_low", name="Low Threshold", subscriber_type="human",
            topic_filters=["ai-safety"], relevance_threshold=0.2
        )

        result = router.route([item], [sub_high, sub_low])

        # Should match both (0.8 >= 0.7 and 0.8 >= 0.2)
        assert "sub_high" in result
        assert "sub_low" in result


def test_route_for_subscription():
    """Test routing for a single subscription"""
    with patch('intel.router.Config') as mock_config:
        mock_config.return_value = MagicMock()

    with patch('intel.router.Enricher') as mock_enricher:
        mock_enricher_instance = MagicMock()
        mock_enricher_instance.score_relevance = lambda item, sub: 0.8
        mock_enricher.return_value = mock_enricher_instance

        router = Router()

        raw = RawItem(
            id="test1", source_id="test", source_type="rss",
            url="http://test.com", title="Test", body="Body",
            published_at=datetime.utcnow(), fetched_at=datetime.utcnow()
        )

        item = EnrichedItem(
            raw=raw, summary="Test", topic_tags=["ai-safety"],
            urgency="high", breaking_changes=[], suggested_actions=[],
            relevance_scores={}, enriched_at=datetime.utcnow()
        )

        sub = Subscription(
            id="sub_test", name="Test", subscriber_type="human",
            topic_filters=["ai-safety"], relevance_threshold=0.5
        )

        result = router.route_for_subscription([item], sub)

        assert len(result) == 1
        assert result[0].raw.id == "test1"
