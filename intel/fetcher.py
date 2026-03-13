"""Source fetcher - fetches and normalizes content from RSS and PyPI sources"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import feedparser
import httpx

from intel.config import Config
from intel.db import init_db
from intel.models import RawItem

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.db_conn = init_db(self.config.db_path)

    def fetch_all(self, lookback_days: int = 7) -> list[RawItem]:
        """Fetch new items from all configured sources"""
        all_items = []

        # Fetch from RSS sources
        for source in self.config.sources:
            if source.get("type") == "rss":
                items = self._fetch_rss(source, lookback_days)
                all_items.extend(items)

        # Fetch from PyPI package sources (generated from tracked_packages)
        for package in self.config.tracked_packages:
            source = {
                "id": f"pypi_{package}",
                "type": "pypi_package",
                "package": package,
                "topic_hint": "python-packaging",
            }
            items = self._fetch_pypi_package(source)
            all_items.extend(items)

        return all_items

    def _fetch_rss(self, source: dict, lookback_days: int) -> list[RawItem]:
        """Fetch from an RSS/Atom feed"""
        items = []
        try:
            feed = feedparser.parse(source["url"])
            logger.info(f"Fetched {len(feed.entries)} items from {source['id']}")

            cutoff = datetime.utcnow() - timedelta(days=lookback_days)

            for entry in feed.entries:
                # Generate unique ID from source + url
                url = entry.get("link", "")
                item_id = hashlib.sha256(f"{source['id']}{url}".encode()).hexdigest()

                # Skip if already in database
                from intel.db import item_exists
                if item_exists(self.db_conn, item_id):
                    continue

                # Parse published date
                published_at = self._parse_date(entry.get("published", ""))
                if published_at and published_at < cutoff:
                    continue

                # Extract body content
                body = entry.get("summary", "") or entry.get("description", "")
                if hasattr(entry, "content"):
                    body = entry.content[0].value

                raw_item = RawItem(
                    id=item_id,
                    source_id=source["id"],
                    source_type="rss",
                    url=url,
                    title=entry.get("title", "Untitled"),
                    body=body[:10000],  # Limit body size
                    published_at=published_at or datetime.utcnow(),
                    fetched_at=datetime.utcnow(),
                    metadata={
                        "topic_hint": source.get("topic_hint", ""),
                    },
                )
                items.append(raw_item)

        except Exception as e:
            logger.error(f"Error fetching RSS {source['id']}: {e}")

        return items

    def _fetch_pypi_package(self, source: dict) -> list[RawItem]:
        """Fetch latest release from PyPI JSON API"""
        items = []
        package = source.get("package")
        url = f"https://pypi.org/pypi/{package}/json"

        try:
            response = httpx.get(url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"PyPI API returned {response.status_code} for {package}")
                return items

            data = response.json()
            info = data.get("info", {})

            # Generate unique ID
            version = info.get("version", "")
            item_id = hashlib.sha256(f"{source['id']}{version}".encode()).hexdigest()

            # Skip if already in database
            from intel.db import item_exists
            if item_exists(self.db_conn, item_id):
                return items

            # Get release notes
            body = info.get("summary", "")
            if info.get("description"):
                body = f"{body}\n\n{info['description']}"

            # Parse release date
            release_date = info.get("release_date")
            if release_date:
                published_at = datetime.fromisoformat(release_date)
            else:
                published_at = datetime.utcnow()

            raw_item = RawItem(
                id=item_id,
                source_id=source["id"],
                source_type="pypi_api",
                url=f"https://pypi.org/project/{package}/{version}/",
                title=f"{package} {version} released",
                body=body[:10000],
                published_at=published_at,
                fetched_at=datetime.utcnow(),
                metadata={
                    "package": package,
                    "version": version,
                    "topic_hint": source.get("topic_hint", ""),
                },
            )
            items.append(raw_item)

        except Exception as e:
            logger.error(f"Error fetching PyPI {package}: {e}")

        return items

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats"""
        if not date_str:
            return None

        # Try common RSS date formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def save_items(self, items: list[RawItem]):
        """Save new items to database"""
        from intel.db import insert_raw_item
        for item in items:
            insert_raw_item(self.db_conn, item)
        logger.info(f"Saved {len(items)} new items to database")
