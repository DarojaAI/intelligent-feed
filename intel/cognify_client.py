"""
Cognee client wrapper — Phase 4 infrastructure.

Initializes Cognee with configurable backends:
  - VecStore: Weaviate (default) | in-memory
  - GraphStore: Neo4j (optional) | in-memory
  - RelStore: SQLite (default, file-based)

Usage:
    client = CogneeClient()                        # defaults: Weaviate + SQLite
    client = CogneeClient(vec_store="weaviate")   # explicit
    client = CogneeClient(vec_store="inmemory")  # no Weaviate needed

    # Run extraction on documents
    result = client.cognify(documents=["..."], domain="finance")

    # Add verified claims to the graph
    client.add(claims=[...], project="bond-nexus")

    # Query the graph
    results = client.search("day count conventions Brazil", project="bond-nexus")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

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
    "extracted_at": str, # ISO-8601
    "status": str,      # "confirmed" | "corrected" | "disputed"
}


@dataclass
class CogneeConfig:
    """Cognee backend configuration."""

    # Vector store
    vec_store: str = "weaviate"  # "weaviate" | "inmemory"
    weaviate_url: str = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    weaviate_api_key: str = os.getenv("WEAVIATE_API_KEY", "")

    # Graph store
    graph_store: str = "neo4j"   # "neo4j" | "inmemory"
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")

    # Relational store (feedback + structured records)
    rel_store: str = "sqlite"   # always sqlite for now
    rel_db_path: str = os.getenv("COGNEE_REL_DB", "./data/cognee_rel.db")

    # LLM
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class CogneeClient:
    """
    Thin wrapper around Cognee that:
      1. Initialises backends from CogneeConfig
      2. Provides a stable `cognify()` interface for extraction
      3. Provides `add()` / `search()` / `query()` for the activation layer
      4. Manages the feedback store (RelStore) for claim status

    Backends are only initialised when first accessed (lazy).
    """

    def __init__(self, config: Optional[CogneeConfig] = None):
        self.config = config or CogneeConfig()
        self._cognify_available = False
        self._cognify_module = None
        self._vec_client = None
        self._graph_client = None
        self._rel_client = None
        self._check_cognify()

    # ── private ──────────────────────────────────────────────────────────────

    def _check_cognify(self):
        try:
            import cognify
            self._cognify_available = True
            self._cognify_module = cognify
            logger.info("Cognee installed — Phase 4 extraction ready")
        except ImportError:
            logger.warning(
                "Cognee not installed. Install with: pip install cognify[weaviate]"
                "Phase 4 extraction will be available after install."
            )

    def _init_vec_client(self):
        """Lazily initialise the vector store client."""
        if self._vec_client is not None:
            return self._vec_client

        if self.config.vec_store == "weaviate":
            try:
                import weaviate
                auth = (
                    weaviate.AuthApiKey(self.config.weaviate_api_key)
                    if self.config.weaviate_api_key
                    else None
                )
                self._vec_client = weaviate.Client(
                    url=self.config.weaviate_url,
                    auth_client_secret=auth,
                )
                logger.info(f"Weaviate vector store ready at {self.config.weaviate_url}")
            except ImportError:
                logger.error("Weaviate not installed. Run: pip install weaviate")
                raise

        elif self.config.vec_store == "inmemory":
            # Cognee's in-memory vector store is used directly via cognify()
            self._vec_client = "inmemory"
            logger.info("In-memory vector store active")

        return self._vec_client

    def _init_rel_client(self):
        """Lazily initialise the relational store (SQLite)."""
        if self._rel_client is not None:
            return self._rel_client

        Path(self.config.rel_db_path).parent.mkdir(parents=True, exist_ok=True)

        import sqlite3
        self._rel_client = sqlite3.connect(self.config.rel_db_path, check_same_thread=False)
        self._rel_client.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                claim_id    TEXT PRIMARY KEY,
                source_url  TEXT,
                source_title TEXT,
                claim_text  TEXT NOT NULL,
                entity_type TEXT,
                project     TEXT NOT NULL,
                domain      TEXT,
                extracted_at TEXT,
                status      TEXT DEFAULT 'confirmed',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        self._rel_client.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id    TEXT,
                verdict     TEXT,   -- confirmed | corrected | disputed
                evidence    TEXT,
                corrected_claim TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (claim_id) REFERENCES claims(claim_id)
            )
        """)
        self._rel_client.commit()
        logger.info(f"Relational store ready at {self.config.rel_db_path}")
        return self._rel_client

    # ── public — cognify() extraction ────────────────────────────────────────

    def cognify(
        self,
        documents: list[str],
        domain: str = "general",
        project: str = "default",
        extract_entities: bool = True,
        extract_relationships: bool = True,
        llm_provider: str = "openai",
    ) -> dict[str, Any]:
        """
        Run Cognee's cognify() on a list of raw text documents.

        Returns Cognee's pipeline result dict with extracted entities,
        relationships, and graph data.

        Args:
            documents: List of raw text strings (e.g. blog body, article)
            domain: Domain hint for the extraction prompt (cuisine, finance, defense…)
            project: Project namespace (globalbitings, bond-nexus, rag-research…)
            extract_entities: Whether to extract named entities
            extract_relationships: Whether to extract relationships between entities
            llm_provider: "openai" or "anthropic"

        Requires: Cognee installed + LLM API key
        """
        if not self._cognify_available:
            raise RuntimeError(
                "Cognee is not installed. Run: pip install 'cognify[weaviate]'"
            )

        import cognify

        # Build the pipeline config
        pipeline_config = {
            "documents": documents,
            "llm_provider": llm_provider,
            "llm_api_key": (
                self.config.openai_api_key or self.config.anthropic_api_key
            ),
            "extract_entities": extract_entities,
            "extract_relationships": extract_relationships,
            # Cognee uses domain to tune extraction prompts
            "task": domain,
        }

        if self.config.vec_store == "weaviate":
            pipeline_config["vector_store"] = {
                "class": "WeaviateVectorStore",
                "url": self.config.weaviate_url,
                "api_key": self.config.weaviate_api_key,
            }

        logger.info(
            f"Running cognify() — {len(documents)} docs, domain={domain}, project={project}"
        )
        result = cognify(**pipeline_config)

        # Tag result with project context for activation layer
        result["_project"] = project
        result["_domain"] = domain

        return result

    # ── public — add() storage ───────────────────────────────────────────────

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
        rel = self._init_rel_client()
        written = []

        for claim in claims:
            claim_id = claim.get("claim_id") or self._make_claim_id(claim)
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

        rel.commit()
        logger.info(f"Added {len(written)} claims to {project}")
        return written

    def record_feedback(
        self,
        claim_id: str,
        verdict: str,
        evidence: str = "",
        corrected_claim: str = "",
    ) -> None:
        """Record feedback on a claim (used by Phase 3 correction loop)."""
        rel = self._init_rel_client()
        rel.execute(
            "INSERT INTO feedback (claim_id, verdict, evidence, corrected_claim) VALUES (?, ?, ?, ?)",
            (claim_id, verdict, evidence, corrected_claim),
        )
        rel.execute(
            "UPDATE claims SET status = ?, updated_at = datetime('now') WHERE claim_id = ?",
            (verdict, claim_id),
        )
        rel.commit()
        logger.info(f"Feedback recorded: claim={claim_id}, verdict={verdict}")

    # ── public — search ───────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        project: Optional[str] = None,
        limit: int = 10,
        search_type: str = "semantic",
    ) -> list[dict]:
        """
        Search stored claims.

        Args:
            query: Free-text query
            project: Optional namespace filter
            limit: Max results
            search_type: "semantic" | "keyword" | "hybrid"

        Returns:
            List of matching claim dicts
        """
        rel = self._init_rel_client()

        if project:
            rows = rel.execute(
                """
                SELECT claim_id, source_url, source_title, claim_text,
                       entity_type, project, domain, extracted_at, status
                FROM claims
                WHERE project = ?
                  AND claim_text LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project, f"%{query}%", limit),
            ).fetchall()
        else:
            rows = rel.execute(
                """
                SELECT claim_id, source_url, source_title, claim_text,
                       entity_type, project, domain, extracted_at, status
                FROM claims
                WHERE claim_text LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (f"%{query}%", limit),
            ).fetchall()

        cols = [
            "claim_id", "source_url", "source_title", "claim_text",
            "entity_type", "project", "domain", "extracted_at", "status",
        ]
        return [dict(zip(cols, row)) for row in rows]

    def get_claims_by_project(self, project: str) -> list[dict]:
        """Return all confirmed claims for a project (for activation)."""
        rel = self._init_rel_client()
        rows = rel.execute(
            """
            SELECT claim_id, source_url, source_title, claim_text,
                   entity_type, project, domain, extracted_at, status
            FROM claims
            WHERE project = ? AND status = 'confirmed'
            ORDER BY updated_at DESC
            """,
            (project,),
        ).fetchall()
        cols = [
            "claim_id", "source_url", "source_title", "claim_text",
            "entity_type", "project", "domain", "extracted_at", "status",
        ]
        return [dict(zip(cols, row)) for row in rows]

    # ── utils ────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_claim_id(claim: dict) -> str:
        import hashlib, json
        body = json.dumps(claim, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:24]

    def export_conventions_yaml(self, project: str = "bond-nexus") -> dict:
        """
        Export confirmed claims for a project as a conventions-style dict.
        Used by bond-nexus activation to regenerate conventions.yaml.
        """
        claims = self.get_claims_by_project(project)
        conventions = {}
        for c in claims:
            entity_type = c["entity_type"]
            if entity_type not in conventions:
                conventions[entity_type] = []
            conventions[entity_type].append({
                "source": c["source_url"],
                "source_title": c["source_title"],
                "claim": c["claim_text"],
            })
        return conventions

    def close(self):
        """Close open connections."""
        if self._rel_client:
            self._rel_client.close()
            self._rel_client = None
        if self._vec_client and hasattr(self._vec_client, "close"):
            self._vec_client.close()
            self._vec_client = None


# ---------------------------------------------------------------------------
# Singleton for use across the pipeline
# ---------------------------------------------------------------------------
_cognify_client: Optional[CogneeClient] = None


def get_cognify_client() -> CogneeClient:
    global _cognify_client
    if _cognify_client is None:
        _cognify_client = CogneeClient()
    return _cognify_client
