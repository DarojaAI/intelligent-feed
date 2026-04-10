"""
DynamicWorlock activator — Phase 4.

Pushes confirmed defense/conOps claims to the dynamic-worlock knowledge store:
  1. Structured JSON knowledge records
  2. Conflict detection report (cross-claim contradictions)
  3. (Future) Word doc generation

Expected claim schema from Cognee:
  {
    "claim_text": "Program X depends_on Program Y, ownership: A, delivery: 2027",
    "entity_type": "dependency",
    "source_url": "https://...",
    "domain": "defense",
  }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from intel.activation.base import ActivationResult, BaseActivator

logger = logging.getLogger(__name__)


class DynamicWorlockActivator(BaseActivator):
    project_name = "dynamic-worlock"

    def __init__(
        self,
        knowledge_store_path: str = "~/GithubProjects/dynamic-worlock/data/knowledge_store.json",
        conflicts_path: str = "~/GithubProjects/dynamic-worlock/data/conflicts.json",
        dry_run: bool = False,
    ):
        self.knowledge_store_path = Path(knowledge_store_path).expanduser()
        self.conflicts_path = Path(conflicts_path).expanduser()
        self.dry_run = dry_run

    # ── BaseActivator ────────────────────────────────────────────────────────

    def check_readiness(self) -> ActivationResult:
        issues = []
        # knowledge_store.json is created by _write_knowledge_records() — non-blocking
        if issues:
            logger.warning("DynamicWorlock readiness issues: " + "; ".join(issues))
            return ActivationResult(
                success=False,
                project=self.project_name,
                claim_count=0,
                error="; ".join(issues),
            )
        return ActivationResult(success=True, project=self.project_name, claim_count=0)

    def activate(self, claims: list[dict]) -> ActivationResult:
        # Filter to defense/conops relevant entity types
        relevant = [
            c for c in claims
            if c.get("entity_type") in (
                "dependency",
                "department",
                "deliverable",
                "policy",
                "program",
                "stakeholder",
            )
        ]

        if not relevant:
            return ActivationResult(
                success=True,
                project=self.project_name,
                claim_count=0,
                details={"msg": "no dependency/policy/program claims in batch"},
            )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would write {len(relevant)} records")
            return ActivationResult(
                success=True,
                project=self.project_name,
                claim_count=len(relevant),
                details={"dry_run": True},
            )

        written = self._write_knowledge_records(relevant)
        conflicts = self._detect_conflicts(relevant)

        return ActivationResult(
            success=True,
            project=self.project_name,
            claim_count=written,
            output_path=str(self.knowledge_store_path),
            details={
                "written": written,
                "conflicts_detected": len(conflicts),
                "entity_types": list({c.get("entity_type") for c in relevant}),
            },
        )

    # ── internal ─────────────────────────────────────────────────────────────

    def _write_knowledge_records(self, claims: list[dict]) -> int:
        """Write claims as structured knowledge records."""
        if self.knowledge_store_path.exists():
            with open(self.knowledge_store_path, "r", encoding="utf-8") as f:
                store = json.load(f)
        else:
            store = {"records": [], "metadata": {}}

        existing_ids = {r.get("record_id") for r in store.get("records", [])}

        new_records = []
        for claim in claims:
            record = self._claim_to_record(claim)
            if record["record_id"] not in existing_ids:
                new_records.append(record)

        store["records"].extend(new_records)
        store["metadata"]["last_updated"] = datetime.utcnow().isoformat() + "Z"
        store["metadata"]["source"] = "cognify-pipeline"

        self.knowledge_store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.knowledge_store_path, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)

        logger.info(f"Wrote {len(new_records)} new records to {self.knowledge_store_path}")
        return len(new_records)

    def _claim_to_record(self, claim: dict) -> dict:
        import hashlib
        record_id = hashlib.sha256(
            claim.get("claim_text", "").encode()
        ).hexdigest()[:16]

        return {
            "record_id": f"dw_{record_id}",
            "entity_type": claim.get("entity_type", "unknown"),
            "claim_text": claim.get("claim_text", ""),
            "source": claim.get("source_url", ""),
            "source_title": claim.get("source_title", ""),
            "domain": claim.get("domain", "defense"),
            "extracted_at": claim.get("extracted_at", ""),
            "status": claim.get("status", "confirmed"),
            "added_by": "cognify-pipeline",
        }

    def _detect_conflicts(self, claims: list[dict]) -> list[dict]:
        """
        Detect potential contradictions between claims.

        Groups claims by entity_type and checks for overlapping entities
        with different claim_text — flags as potential conflicts.
        """
        # Simple conflict detection: same entity mentioned with different claims
        entity_claims: dict[str, list[dict]] = {}
        for claim in claims:
            text = claim.get("claim_text", "")
            # Extract entity name (before first colon, or first word)
            entity, _, _ = text.partition(":")
            entity = entity.strip().lower()
            if not entity:
                entity = text.split()[0].lower() if text else "unknown"

            if entity not in entity_claims:
                entity_claims[entity] = []
            entity_claims[entity].append(claim)

        conflicts = []
        for entity, claim_list in entity_claims.items():
            if len(claim_list) > 1:
                # Check if they differ significantly (simple heuristic)
                texts = [c.get("claim_text", "") for c in claim_list]
                if len(set(texts)) > 1:  # Same entity, different claims
                    conflicts.append({
                        "entity": entity,
                        "conflicting_claims": claim_list,
                        "conflict_type": "multiple_claims",
                    })

        if conflicts:
            conflicts_data = {
                "detected_at": datetime.utcnow().isoformat() + "Z",
                "total_conflicts": len(conflicts),
                "conflicts": conflicts,
            }
            self.conflicts_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.conflicts_path, "w", encoding="utf-8") as f:
                json.dump(conflicts_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Detected {len(conflicts)} conflicts, written to {self.conflicts_path}")

        return conflicts
