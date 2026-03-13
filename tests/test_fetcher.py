"""Tests for fetcher module"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from intel.fetcher import Fetcher
from intel.models import RawItem


def test_fetcher_initialization():
    """Test fetcher can be initialized"""
    with patch('intel.fetcher.Config') as mock_config:
        mock_config.return_value.db_path = ":memory:"
        mock_config.return_value.sources = []
        mock_config.return_value.tracked_packages = []

        with patch('intel.fetcher.init_db') as mock_db:
            mock_db.return_value = MagicMock()
            fetcher = Fetcher()
            assert fetcher is not None


def test_parse_date_rss_format():
    """Test parsing RSS date format"""
    with patch('intel.fetcher.Config') as mock_config:
        mock_config.return_value.db_path = ":memory:"
        mock_config.return_value.sources = []
        mock_config.return_value.tracked_packages = []

        with patch('intel.fetcher.init_db') as mock_db:
            mock_db.return_value = MagicMock()
            fetcher = Fetcher()

            # Test RSS date format
            result = fetcher._parse_date("Mon, 13 Mar 2026 12:00:00 +0000")
            assert result is not None


def test_parse_date_iso_format():
    """Test parsing ISO date format"""
    with patch('intel.fetcher.Config') as mock_config:
        mock_config.return_value.db_path = ":memory:"
        mock_config.return_value.sources = []
        mock_config.return_value.tracked_packages = []

        with patch('intel.fetcher.init_db') as mock_db:
            mock_db.return_value = MagicMock()
            fetcher = Fetcher()

            # Test ISO format
            result = fetcher._parse_date("2026-03-13T12:00:00+00:00")
            assert result is not None


def test_parse_date_invalid():
    """Test parsing invalid date"""
    with patch('intel.fetcher.Config') as mock_config:
        mock_config.return_value.db_path = ":memory:"
        mock_config.return_value.sources = []
        mock_config.return_value.tracked_packages = []

        with patch('intel.fetcher.init_db') as mock_db:
            mock_db.return_value = MagicMock()
            fetcher = Fetcher()

            result = fetcher._parse_date("invalid date")
            assert result is None
