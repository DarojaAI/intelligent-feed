"""
Cognee client wrapper — Phase 4 infrastructure.

Architecture (per research-pipeline-plan.md):
  - VecStore:  pgvector (PostgreSQL) — shared with relational DB
  - GraphStore: Neo4j (optional)
  - RelStore:  PostgreSQL (SQLite dev fallback)
  - LLM:       OpenRouter via LiteLLM custom endpoint

Env vars required (set via CogneeConfig or directly):
  # LLM — OpenRouter
    LLM_PROVIDER=custom
    LLM_MODEL=openrouter/<model>         e.g. openrouter/google/gemini-2.0-flash
    LLM_ENDPOINT=https://openrouter.ai/api/v1
    LLM_API_KEY=<key>

  # Embeddings (OpenAI fallback or OpenRouter-compatible)
    EMBEDDING_PROVIDER=openai
    EMBEDDING_MODEL=openai/text-embedding-3-small
    EMBEDDING_API_KEY=<key>

  # Relational DB + pgvector (same Postgres instance)
    DB_PROVIDER=postgres
    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=cognee
    DB_USERNAME=postgres
    DB_PASSWORD=<pw>

  # Graph store (optional)
    GRAPH_DATABASE_PROVIDER=neo4j
    GRAPH_DATABASE_URL=bolt://localhost:7687
    GRAPH_DATABASE_USERNAME=neo4j
    GRAPH_DATABASE_PASSWORD=<pw>

Usage:
    config = CogneeConfig()           # reads from env, OpenRouter defaults
    client = CogneeClient(config)

    client.setup()                   # set env vars from config
    result = client.cognify(documents=["..."], domain="finance")

    client.add(claims=[...], project="bond-nexus")
    results = client.search("day count conventions Brazil", project="bond-nexus")
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema — shared with activation layer
# ---------------------------------------------------------------------------

CLAIMS_SCHEMA = {
    "claim_id": str,
    "source_url": str,
    "source_title": str,
    "claim_text": str,
    "entity_type": str,  # "convention" | "rule" | "ingredient" | "entity"
    "project": str,      # "globalbitings" | "bond-nexus" | "rag-research" | "dynamic-worlock"
    "domain": str,       # "cuisine" | "finance" | "defense" | etc.
    "extracted_at": str,  # ISO-8601
    "status": str,       # "confirmed" | "corrected" | "disputed"
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CogneeConfig:
    """
    Cognee backend + LLM configuration.

    All values can be overridden via environment variables. This class
    provides a typed, discoverable interface and sets env vars before
    Cognee is called (Cognee reads env vars directly, not constructor args).

    Defaults target:
      - LLM:  OpenRouter + LiteLLM custom endpoint
      - Vec:  pgvector (PostgreSQL)
      - Rel:  PostgreSQL (same instance)
      - Graph: Neo4j (optional)
    """

    # ── LLM — OpenRouter via LiteLLM custom endpoint ───────────────────────
    # LLMProvider choices: openai | anthropic | gemini | ollama | custom
    llm_provider: str = "custom"           # LLM_PROVIDER
    # Model name with LiteLLM prefix.
    # OpenRouter format: openrouter/<model-slug>
    # Examples:
    #   openrouter/google/gemini-2.0-flash
    #   openrouter/anthropic/claude-3.5-sonnet
    #   openrouter/openai/gpt-4o-mini
    llm_model: str = "openrouter/google/gemini-2.0-flash"
    llm_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    llm_endpoint: str = "https://openrouter.ai/api/v1"  # LLM_ENDPOINT
    llm_temperature: float = 0.0  # LLM_TEMPERATURE

    # ── Embeddings ─────────────────────────────────────────────────────────
    embedding_provider: str = "openai"  # EMBEDDING_PROVIDER
    embedding_model: str = "openai/text-embedding-3-small"  # EMBEDDING_MODEL
    embedding_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    embedding_dimensions: int = 1536  # EMBEDDING_DIMENSIONS

    # ── Relational DB + pgvector (same Postgres instance) ───────────────────
    db_provider: str = "postgres"  # DB_PROVIDER
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "cognee")
    db_username: str = os.getenv("DB_USERNAME", "postgres")
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))

    # ── Vector store ──────────────────────────────────────────────────────
    # VECTOR_DB_PROVIDER: lancedb | pgvector | qdrant | chromadb | ...
    vector_db_provider: str = "pgvector"  # VECTOR_DB_PROVIDER
    # For pgvector this is optional — inherits from DB_* above
    vector_db_url: str = ""  # VECTOR_DB_URL

    # ── Graph store (optional) ─────────────────────────────────────────────
    graph_db_provider: str = "neo4j"  # GRAPH_DATABASE_PROVIDER
    graph_db_url: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")  # GRAPH_DATABASE_URL
    graph_db_username: str = os.getenv("NEO4J_USER", "neo4j")
    graph_db_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))

    # ── Dev fallback: SQLite when Postgres is unavailable ───────────────────
    # Set rel_db_path for SQLite fallback (used only when db_provider=sqlite)
    rel_db_path: str = "./data/cognee_rel.db"

    def apply_to_env(self) -> None:
        """
        Set all Cognee-relevant environment variables from this config.

        Call this before running cognify() — Cognee reads env vars directly.
        """
        # LLM
        os.environ["LLM_PROVIDER"] = self.llm_provider
        os.environ["LLM_MODEL"] = self.llm_model
        os.environ["LLM_API_KEY"] = self.llm_api_key
        os.environ["LLM_ENDPOINT"] = self.llm_endpoint
        os.environ["LLM_TEMPERATURE"] = str(self.llm_temperature)

        # Embeddings
        os.environ["EMBEDDING_PROVIDER"] = self.embedding_provider
        os.environ["EMBEDDING_MODEL"] = self.embedding_model
        os.environ["EMBEDDING_API_KEY"] = self.embedding_api_key
        os.environ["EMBEDDING_DIMENSIONS"] = str(self.embedding_dimensions)

        # Relational DB
        os.environ["DB_PROVIDER"] = self.db_provider
        os.environ["DB_HOST"] = self.db_host
        os.environ["DB_PORT"] = str(self.db_port)
        os.environ["DB_NAME"] = self.db_name
        os.environ["DB_USERNAME"] = self.db_username
        os.environ["DB_PASSWORD"] = self.db_password

        # Vector store
        os.environ["VECTOR_DB_PROVIDER"] = self.vector_db_provider
        if self.vector_db_url:
            os.environ["VECTOR_DB_URL"] = self.vector_db_url

        # Graph store
        os.environ["GRAPH_DATABASE_PROVIDER"] = self.graph_db_provider
        os.environ["GRAPH_DATABASE_URL"] = self.graph_db_url
        os.environ["GRAPH_DATABASE_USERNAME"] = self.graph_db_username
        os.environ["GRAPH_DATABASE_PASSWORD"] = self.graph_db_password

        # Cognee system dirs
        os.environ.setdefault("DATA_ROOT_DIRECTORY", ".cognee_data")
        os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", ".cognee_system")

        logger.debug("Cognee env vars applied from CogneeConfig")


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class CogneeClient:
    """
    Thin Cognee wrapper for the research pipeline.

    Responsibilities:
      1. Apply CogneeConfig → env vars before each cognify() call
      2. Provide add() / search() / record_feedback() via the relational store
      3. Manage the feedback loop (Phase 3 ←→ Phase 4)

    The actual cognify() extraction is handled by Cognee's pipeline.
    """

    def __init__(self, config: Optional[CogneeConfig] = None):
        self.config = config or CogneeConfig()
        self._cognify_available = False
        self._cognify_module = None
        self._rel_client: Optional[sqlite3.Connection] = None
        self._pg_conn: Any = None
        self._check_cognify()

    # ── private ────────────────────────────────────────────────────────────

    def _check_cognify(self):
        try:
            import cognify
            self._cognify_available = True
            self._cognify_module = cognify
            logger.info("Cognee installed — Phase 4 extraction ready")
        except ImportError:
            logger.warning(
                "Cognee not installed. Run: pip install 'cognee[postgres]' openrouter"
                "\nPhase 4 extraction will be available after install."
            )

    def _init_rel_store(self) -> sqlite3.Connection:
        """
        Initialise the relational store.

        Uses PostgreSQL when DB_PROVIDER=postgres (production).
        Falls back to SQLite when DB_PROVIDER=sqlite (dev/local).
        """
        if self._rel_client is not None:
            return self._rel_client

        if self.config.db_provider == "postgres":
            # Try to connect to Postgres for the claims/feedback tables
            try:
                import psycopg2
                self._pg_conn = psycopg2.connect(
                    host=self.config.db_host,
                    port=self.config.db_port,
                    dbname=self.config.db_name,
                    user=self.config.db_username,
                    password=self.config.db_password,
                )
                # Use the PG connection directly for claims
                self._rel_client = self._pg_conn
                self._pg_conn.autocommit = True
                self._ensure_pg_tables()
                logger.info(
                    f"PostgreSQL relational store ready — "
                    f"{self.config.db_host}:{self.config.db_port}/{self.config.db_name}"
                )
                return self._rel_client
            except ImportError:
                logger.warning("psycopg2 not installed; falling back to SQLite")
            except Exception as e:
                logger.warning(f"Postgres unavailable ({e}); falling back to SQLite")

        # SQLite fallback
        Path(self.config.rel_db_path).parent.mkdir(parents=True, exist_ok=True)
        self._rel_client = sqlite3.connect(
            self.config.rel_db_path, check_same_thread=False
        )
        self._ensure_sqlite_tables()
        logger.info(f"SQLite relational store ready at {self.config.rel_db_path}")
        return self._rel_client

    def _ensure_sqlite_tables(self):
        self._rel_client.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                claim_id      TEXT PRIMARY KEY,
                source_url    TEXT,
                source_title  TEXT,
                claim_text    TEXT NOT NULL,
                entity_type   TEXT,
                project       TEXT NOT NULL,
                domain        TEXT,
                extracted_at  TEXT,
                status        TEXT DEFAULT 'confirmed',
                created_at    TEXT DEFAULT (datetime('now')),
                updated_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        self._rel_client.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id         TEXT,
                verdict          TEXT,
                evidence         TEXT,
                corrected_claim TEXT,
                created_at       TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
            )
        """)
        self._rel_client.commit()

    def _ensure_pg_tables(self):
        cur = self._pg_conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                claim_id      TEXT PRIMARY KEY,
                source_url    TEXT,
                source_title  TEXT,
                claim_text    TEXT NOT NULL,
                entity_type   TEXT,
                project       TEXT NOT NULL,
                domain        TEXT,
                extracted_at  TEXT,
                status        TEXT DEFAULT 'confirmed',
                created_at    TIMESTAMP DEFAULT NOW(),
                updated_at    TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id               SERIAL PRIMARY KEY,
                claim_id         TEXT,
                verdict          TEXT,
                evidence         TEXT,
                corrected_claim  TEXT,
                created_at       TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
            )
        """)
        cur.execute("SELECT 1")  # flush
        self._pg_conn.commit()

    # ── public ─────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        Apply configuration to the environment.

        Must be called before cognify() — Cognee reads env vars directly.
        Safe to call multiple times (idempotent).
        """
        self.config.apply_to_env()

    def cognify(
        self,
        documents: list[str],
        domain: str = "general",
        project: str = "default",
        *,
        extract_entities: bool = True,
        extract_relationships: bool = True,
    ) -> dict[str, Any]:
        """
        Run Cognee's cognify() pipeline on raw text documents.

        Env vars must be set before calling this — call self.setup() first,
        or ensure LLM_*, DB_*, VECTOR_DB_PROVIDER, etc. are in os.environ.

        Args:
            documents: List of raw text strings (blog body, article, etc.)
            domain: Domain hint for extraction prompts (cuisine, finance, defense…)
            project: Project namespace for claim routing (globalbitings, bond-nexus…)
            extract_entities: Whether to extract named entities
            extract_relationships: Whether to extract relationships

        Returns:
            Cognee pipeline result dict with extracted entities + relationships

        Raises:
            RuntimeError: If Cognee is not installed
        """
        if not self._cognify_available:
            raise RuntimeError(
                "Cognee not installed. Run:\n"
                "  pip install 'cognee[postgres]'\n"
                "  # then set env vars (or use CogneeConfig.setup()):\n"
                "  export LLM_PROVIDER=custom\n"
                "  export LLM_MODEL=openrouter/google/gemini-2.0-flash\n"
                "  export LLM_ENDPOINT=https://openrouter.ai/api/v1\n"
                "  export LLM_API_KEY=<your-key>\n"
            )

        self.setup()  # ensure env vars are current

        pipeline_config = dict(
            documents=documents,
            extract_entities=extract_entities,
            extract_relationships=extract_relationships,
            # task is Cognee's domain-hint parameter
            task=domain,
        )

        logger.info(
            f"Running cognify() — {len(documents)} docs, domain={domain}, "
            f"project={project}, llm={self.config.llm_model}"
        )

        result = self._cognify_module.cognify(**pipeline_config)
        result["_project"] = project
        result["_domain"] = domain
        return result

    def add(
        self,
        claims: list[dict],
        project: str,
        status: str = "confirmed",
    ) -> list[str]:
        """
        Write structured claims to the relational store.

        Args:
            claims: List of claim dicts following CLAIMS_SCHEMA
            project: Project namespace
            status: Initial status (confirmed | corrected | disputed)

        Returns:
            List of claim_ids written
        """
        rel = self._init_rel_store()
        written = []

        for claim in claims:
            claim_id = claim.get("claim_id") or self._make_claim_id(claim)
            if self.config.db_provider == "postgres":
                cur = rel.cursor()
                cur.execute(
                    """
                    INSERT INTO claims
                      (claim_id, source_url, source_title, claim_text,
                       entity_type, project, domain, extracted_at, status, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (claim_id) DO UPDATE SET
                      source_url    = EXCLUDED.source_url,
                      source_title  = EXCLUDED.source_title,
                      claim_text    = EXCLUDED.claim_text,
                      entity_type   = EXCLUDED.entity_type,
                      domain        = EXCLUDED.domain,
                      extracted_at  = EXCLUDED.extracted_at,
                      status       = EXCLUDED.status,
                      updated_at   = NOW()
                    """,
                    (
                        claim_id,
                        claim.get("source_url", ""),
                        claim.get("source_title", ""),
                        claim["claim_text"],
                        claim.get("entity_type", "unknown"),
                        project,
                        claim.get("domain", ""),
                        claim.get("extracted_at", ""),
                        status,
                    ),
                )
            else:
                rel.execute(
                    """
                    INSERT OR REPLACE INTO claims
                      (claim_id, source_url, source_title, claim_text,
                       entity_type, project, domain, extracted_at, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        claim_id,
                        claim.get("source_url", ""),
                        claim.get("source_title", ""),
                        claim["claim_text"],
                        claim.get("entity_type", "unknown"),
                        project,
                        claim.get("domain", ""),
                        claim.get("extracted_at", ""),
                        status,
                    ),
                )
            written.append(claim_id)

        if self.config.db_provider != "postgres":
            rel.commit()

        logger.info(f"Added {len(written)} claims to {project} ({self.config.db_provider})")
        return written

    def record_feedback(
        self,
        claim_id: str,
        verdict: str,
        evidence: str = "",
        corrected_claim: str = "",
    ) -> None:
        """Record Phase 3 feedback on a claim (confirmed / corrected / disputed)."""
        rel = self._init_rel_store()
        if self.config.db_provider == "postgres":
            cur = rel.cursor()
            cur.execute(
                "INSERT INTO feedback (claim_id, verdict, evidence, corrected_claim) "
                "VALUES (%s, %s, %s, %s)",
                (claim_id, verdict, evidence, corrected_claim),
            )
            cur.execute(
                "UPDATE claims SET status = %s, updated_at = NOW() WHERE claim_id = %s",
                (verdict, claim_id),
            )
            rel.commit()
        else:
            rel.execute(
                "INSERT INTO feedback (claim_id, verdict, evidence, corrected_claim) VALUES (?, ?, ?, ?)",
                (claim_id, verdict, evidence, corrected_claim),
            )
            rel.execute(
                "UPDATE claims SET status = ?, updated_at = datetime('now') WHERE claim_id = ?",
                (verdict, claim_id),
            )
            rel.commit()
        logger.info(f"Feedback: claim={claim_id}, verdict={verdict}")

    def search(
        self,
        query: str,
        project: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Full-text search across stored claims (keyword match on claim_text).

        For semantic/vector search, Cognee's cognify search() handles that —
        this method is for the activation layer to quickly retrieve
        structured records by keyword.

        Args:
            query: Keyword to search in claim_text
            project: Optional namespace filter
            limit: Max results

        Returns:
            List of matching claim dicts
        """
        rel = self._init_rel_store()
        cols = [
            "claim_id", "source_url", "source_title", "claim_text",
            "entity_type", "project", "domain", "extracted_at", "status",
        ]

        if self.config.db_provider == "postgres":
            cur = rel.cursor()
            if project:
                cur.execute(
                    f"SELECT {','.join(cols)} FROM claims "
                    "WHERE project = %s AND claim_text ILIKE %s "
                    "ORDER BY updated_at DESC LIMIT %s",
                    (project, f"%{query}%", limit),
                )
            else:
                cur.execute(
                    f"SELECT {','.join(cols)} FROM claims "
                    "WHERE claim_text ILIKE %s "
                    "ORDER BY updated_at DESC LIMIT %s",
                    (f"%{query}%", limit),
                )
            rows = cur.fetchall()
        else:
            if project:
                rows = rel.execute(
                    f"SELECT {','.join(cols)} FROM claims "
                    "WHERE project = ? AND claim_text LIKE ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (project, f"%{query}%", limit),
                ).fetchall()
            else:
                rows = rel.execute(
                    f"SELECT {','.join(cols)} FROM claims "
                    "WHERE claim_text LIKE ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()

        return [dict(zip(cols, row)) for row in rows]

    def get_claims_by_project(self, project: str) -> list[dict]:
        """Return all confirmed claims for a project (for activation)."""
        rel = self._init_rel_store()
        cols = [
            "claim_id", "source_url", "source_title", "claim_text",
            "entity_type", "project", "domain", "extracted_at", "status",
        ]

        if self.config.db_provider == "postgres":
            cur = rel.cursor()
            cur.execute(
                f"SELECT {','.join(cols)} FROM claims "
                "WHERE project = %s AND status = 'confirmed' "
                "ORDER BY updated_at DESC",
                (project,),
            )
            rows = cur.fetchall()
        else:
            rows = rel.execute(
                f"SELECT {','.join(cols)} FROM claims "
                "WHERE project = ? AND status = 'confirmed' "
                "ORDER BY updated_at DESC",
                (project,),
            ).fetchall()

        return [dict(zip(cols, row)) for row in rows]

    def close(self):
        """Close open connections."""
        if self._rel_client:
            self._rel_client.close()
            self._rel_client = None
        if self._pg_conn:
            self._pg_conn.close()
            self._pg_conn = None

    # ── utils ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_claim_id(claim: dict) -> str:
        import hashlib, json
        body = json.dumps(claim, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_cognify_client: Optional[CogneeClient] = None


def get_cognify_client() -> CogneeClient:
    global _cognify_client
    if _cognify_client is None:
        _cognify_client = CogneeClient()
    return _cognify_client
