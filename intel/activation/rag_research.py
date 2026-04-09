"""
rag_research_tool activator — Phase 4.

Pushes confirmed claims to the existing rag_research_tool knowledge graph:
  1. Weaviate (vector store — entities + relationships)
  2. Triplets JSON (structured KG records)
  3. Streamlit Q&A page refresh

Expected claim schema from Cognee:
  {
    "claim_text": "Entity: dependency_graph, relates_to: workflow_engine, type: data_flow",
    "entity_type": "relationship",
    "source_url": "https://...",
    "domain": "defense",
  }
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from intel.activation.base import ActivationResult, BaseActivator

logger = logging.getLogger(__name__)


class RagResearchActivator(BaseActivator):
    project_name = "rag-research"

    def __init__(
        self,
        triplets_path: str = "~/GithubProjects/rag_research_tool/triplets.json",
        dry_run: bool = False,
    ):
        self.triplets_path = Path(triplets_path).expanduser()
        self.dry_run = dry_run

    # ── BaseActivator ────────────────────────────────────────────────────────

    def check_readiness(self) -> ActivationResult:
        issues = []
        if not self.triplets_path.exists():
            issues.append(f"triplets.json not found: {self.triplets_path}")
        if issues:
            logger.warning("RagResearch readiness issues: " + "; ".join(issues))
            return ActivationResult(
                success=False,
                project=self.project_name,
                claim_count=0,
                error="; ".join(issues),
            )
        return ActivationResult(success=True, project=self.project_name, claim_count=0)

    def activate(self, claims: list[dict]) -> ActivationResult:
        relevant = [
            c for c in claims if c.get("entity_type") in ("relationship", "entity", "concept")
        ]

        if not relevant:
            return ActivationResult(
                success=True,
                project=self.project_name,
                claim_count=0,
                details={"msg": "no relationship/entity claims in batch"},
            )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would append {len(relevant)} triplets to {self.triplets_path}")
            return ActivationResult(
                success=True,
                project=self.project_name,
                claim_count=len(relevant),
                details={"dry_run": True},
            )

        written = self._append_triplets(relevant)

        return ActivationResult(
            success=True,
            project=self.project_name,
            claim_count=written,
            output_path=str(self.triplets_path),
            details={"entity_types": list({c.get("entity_type") for c in relevant})},
        )

    # ── internal ─────────────────────────────────────────────────────────────

    def _append_triplets(self, claims: list[dict]) -> int:
        """Append relationship/entity claims as triplets in the rag_research format."""
        # Load existing triplets
        if self.triplets_path.exists():
            with open(self.triplets_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing_ids = {t.get("id") for t in data.get("triplets", [])}
        else:
            data = {"triplets": [], "metadata": {"generated": "", "source": "cognify-pipeline"}}
            existing_ids = set()

        # Parse claim_text for relationship format "Entity: X, relates_to: Y, type: Z"
        new_triplets = []
        for claim in claims:
            triplet = self._parse_claim_to_triplet(claim)
            if triplet and triplet["id"] not in existing_ids:
                new_triplets.append(triplet)
                existing_ids.add(triplet["id"])

        data["triplets"].extend(new_triplets)
        data["metadata"]["generated"] = datetime.utcnow().isoformat() + "Z"

        self.triplets_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.triplets_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Appended {len(new_triplets)} new triplets to {self.triplets_path}")
        return len(new_triplets)

    def _parse_claim_to_triplet(self, claim: dict) -> Optional[dict]:
        """Parse a claim text into the rag_research triplet format."""
        text = claim.get("claim_text", "")

        # Format: "Entity: X, relates_to: Y, type: Z"
        parts = {}
        for segment in text.split(","):
            key, _, val = segment.partition(":")
            key = key.strip().lower().replace(" ", "_")
            val = val.strip()
            if key and val:
                parts[key] = val

        entity = parts.get("entity", "")
        relates_to = parts.get("relates_to", "")
        rel_type = parts.get("type", "related")

        if not entity:
            return None

        import hashlib
        triplet_id = hashlib.sha256(
            f"{entity}{relates_to}{rel_type}".encode()
        ).hexdigest()[:16]

        return {
            "id": f"kg_{triplet_id}",
            "entity": entity,
            "relates_to": relates_to,
            "relationship_type": rel_type,
            "source": claim.get("source_url", ""),
            "source_title": claim.get("source_title", ""),
            "domain": claim.get("domain", ""),
            "extracted_at": claim.get("extracted_at", ""),
            "status": claim.get("status", "confirmed"),
            "added_by": "cognify-pipeline",
        }
