"""Tests for renderer modules"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json

from intel.renderers.human import HumanRenderer
from intel.renderers.agent import AgentRenderer
from intel.models import EnrichedItem, RawItem, Subscription, DeliveryConfig
from datetime import datetime


def test_human_renderer_initialization():
    """Test human renderer can be initialized"""
    with patch('intel.renderers.human.Config') as mock_config:
        mock_config.return_value.output_dir = "./output"
        mock_config.return_value.anthropic_api_key = None

        renderer = HumanRenderer()
        assert renderer is not None


def test_human_renderer_format_item():
    """Test formatting a single item"""
    with patch('intel.renderers.human.Config') as mock_config:
        mock_config.return_value.output_dir = "./output"
        mock_config.return_value.anthropic_api_key = None

        renderer = HumanRenderer()

        raw = RawItem(
            id="test1", source_id="test_source", source_type="rss",
            url="http://test.com", title="Test Article",
            body="Article body content", published_at=datetime(2026, 3, 13),
            fetched_at=datetime.utcnow()
        )

        item = EnrichedItem(
            raw=raw, summary="This is a test summary",
            topic_tags=["ai-safety", "ethical-ai"], urgency="high",
            breaking_changes=[], suggested_actions=[],
            relevance_scores={"sub_test": 0.8}, enriched_at=datetime.utcnow()
        )

        lines = renderer._format_item(item, "sub_test")

        assert "### Test Article" in lines[0]
        assert "ai-safety" in " ".join(lines)
        assert "Urgency:" in " ".join(lines)


def test_agent_renderer_initialization():
    """Test agent renderer can be initialized"""
    with patch('intel.renderers.agent.Config') as mock_config:
        mock_config.return_value.output_dir = "./output"

        renderer = AgentRenderer()
        assert renderer is not None


def test_agent_renderer_build_payload():
    """Test building agent payload"""
    with patch('intel.renderers.agent.Config') as mock_config:
        mock_config.return_value.output_dir = "./output"

        renderer = AgentRenderer()

        raw = RawItem(
            id="abc123def456", source_id="pypi_pydantic", source_type="pypi_api",
            url="https://pypi.org/project/pydantic/2.0.0/",
            title="pydantic 2.0.0 released", body="Release notes",
            published_at=datetime.utcnow(), fetched_at=datetime.utcnow(),
            metadata={"package": "pydantic", "version": "2.0.0"}
        )

        item = EnrichedItem(
            raw=raw, summary="Pydantic 2.0.0 adds new features",
            topic_tags=["python-packaging", "package-update", "breaking-change"],
            urgency="high", breaking_changes=["Old API removed"],
            suggested_actions=[],
            relevance_scores={"sub_pypi": 0.9}, enriched_at=datetime.utcnow()
        )

        sub = Subscription(
            id="sub_pypi", name="PyPI Monitor", subscriber_type="agent",
            topic_filters=["python-packaging"], relevance_threshold=0.5
        )

        payload = renderer._build_payload(sub, item, "2026-03-13")

        assert payload["schema_version"] == "1.0"
        assert payload["event"]["type"] == "package_update"
        assert payload["event"]["source"] == "pypi_pydantic"
        assert payload["relevance"]["score"] == 0.9
        assert payload["relevance"]["urgency"] == "high"
        assert "breaking_changes" in payload["context"]


def test_agent_renderer_build_payload_article():
    """Test building agent payload for article"""
    with patch('intel.renderers.agent.Config') as mock_config:
        mock_config.return_value.output_dir = "./output"

        renderer = AgentRenderer()

        raw = RawItem(
            id="xyz789", source_id="anthropic_blog", source_type="rss",
            url="https://anthropic.com/blog/new-ai-safety",
            title="New AI Safety Research", body="Blog post content",
            published_at=datetime.utcnow(), fetched_at=datetime.utcnow()
        )

        item = EnrichedItem(
            raw=raw, summary="Anthropic releases new safety research",
            topic_tags=["ai-safety", "ethical-ai"], urgency="medium",
            breaking_changes=[], suggested_actions=[],
            relevance_scores={"sub_ethical": 0.7}, enriched_at=datetime.utcnow()
        )

        sub = Subscription(
            id="sub_ethical", name="Ethical AI", subscriber_type="human",
            topic_filters=["ethical-ai"], relevance_threshold=0.5
        )

        payload = renderer._build_payload(sub, item, "2026-03-13")

        # Article type should be inferred
        assert payload["event"]["type"] == "article"
