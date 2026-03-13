"""SQLite database helpers"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from intel.models import RawItem, EnrichedItem, SuggestedAction


def get_db_path() -> str:
    """Get the database path from config"""
    from intel.config import Config
    config = Config()
    return config.db_path


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Initialize the database schema"""
    if db_path is None:
        db_path = get_db_path()

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_items (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            published_at TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            metadata TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enriched_items (
            id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            topic_tags TEXT NOT NULL,
            urgency TEXT NOT NULL,
            breaking_changes TEXT NOT NULL,
            suggested_actions TEXT NOT NULL,
            relevance_scores TEXT NOT NULL,
            enriched_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deliveries (
            id TEXT PRIMARY KEY,
            subscription_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            delivered_at TEXT NOT NULL,
            delivery_mode TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_outcomes (
            id TEXT PRIMARY KEY,
            payload_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            detail TEXT,
            reported_at TEXT NOT NULL
        )
    """)

    conn.commit()
    return conn


def insert_raw_item(conn: sqlite3.Connection, item: RawItem):
    """Insert a raw item into the database"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO raw_items
        (id, source_id, source_type, url, title, body, published_at, fetched_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.id,
        item.source_id,
        item.source_type,
        item.url,
        item.title,
        item.body,
        item.published_at.isoformat(),
        item.fetched_at.isoformat(),
        json.dumps(item.metadata),
    ))
    conn.commit()


def item_exists(conn: sqlite3.Connection, item_id: str) -> bool:
    """Check if a raw item already exists"""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM raw_items WHERE id = ?", (item_id,))
    return cursor.fetchone() is not None


def insert_enriched_item(conn: sqlite3.Connection, item: EnrichedItem):
    """Insert an enriched item into the database"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO enriched_items
        (id, summary, topic_tags, urgency, breaking_changes, suggested_actions, relevance_scores, enriched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.raw.id,
        item.summary,
        json.dumps(item.topic_tags),
        item.urgency,
        json.dumps(item.breaking_changes),
        json.dumps([{
            "action_id": a.action_id,
            "type": a.type,
            "description": a.description,
            "priority": a.priority,
            "auto_execute": a.auto_execute,
            "params": a.params,
        } for a in item.suggested_actions]),
        json.dumps(item.relevance_scores),
        item.enriched_at.isoformat(),
    ))
    conn.commit()


def get_enriched_item(conn: sqlite3.Connection, item_id: str) -> Optional[dict]:
    """Get enriched item by ID"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM enriched_items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        return None

    return {
        "id": row[0],
        "summary": row[1],
        "topic_tags": json.loads(row[2]),
        "urgency": row[3],
        "breaking_changes": json.loads(row[4]),
        "suggested_actions": json.loads(row[5]),
        "relevance_scores": json.loads(row[6]),
        "enriched_at": row[7],
    }


def insert_delivery(conn: sqlite3.Connection, delivery_id: str, subscription_id: str,
                    item_id: str, delivery_mode: str, status: str):
    """Record a delivery"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO deliveries (id, subscription_id, item_id, delivered_at, delivery_mode, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (delivery_id, subscription_id, item_id, datetime.utcnow().isoformat(), delivery_mode, status))
    conn.commit()


def insert_agent_outcome(conn: sqlite3.Connection, outcome_id: str, payload_id: str,
                         action_id: str, outcome: str, detail: Optional[str] = None):
    """Record an agent outcome"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO agent_outcomes (id, payload_id, action_id, outcome, detail, reported_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (outcome_id, payload_id, action_id, outcome, detail, datetime.utcnow().isoformat()))
    conn.commit()
