"""
GlobalBitings activator — Phase 4.

Pushes confirmed dish/restaurant claims to:
  1. extraction_log.jsonl  (dish knowledge graph seed)
  2. RAGResearchTool.py --sync  (graph conflict detection + provenance)

The claim schema expected from Cognee:
  {
    "claim_text": "Carbonara: Roman dish, guanciale, Pecorino Romano, egg yolk, black pepper",
    "entity_type": "dish",
    "source_url": "https://example.com/blog/carbonara",
    "source_title": "Authentic Roman Carbonara",
    "extracted_at": "2026-04-09T...",
    "domain": "cuisine",
  }
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from intel.activation.base import ActivationResult, BaseActivator

logger = logging.getLogger(__name__)


class GlobalBitingsActivator(BaseActivator):
    project_name = "globalbitings"

    def __init__(
        self,
        extraction_log_path: Optional[str] = None,
        rag_sync_cmd: Optional[str] = None,
        dry_run: bool = False,
    ):
        # Env-var override; default keeps the operator's local checkout layout.
        self.extraction_log_path = Path(
            extraction_log_path
            or os.environ.get(
                "GLOBALBITINGS_EXTRACTION_LOG_PATH",
                "~/GithubProjects/GlobalBitings/data/extraction_log.jsonl",
            )
        ).expanduser()
        self.rag_sync_cmd = (
            rag_sync_cmd
            or os.environ.get(
                "GLOBALBITINGS_RAG_SYNC_CMD",
                "/usr/bin/python3 /home/desktopuser/GithubProjects/GlobalBitings/shapes/RAGResearchTool.py --sync",
            )
        )
        self.dry_run = dry_run

    # ── BaseActivator ────────────────────────────────────────────────────────

    def check_readiness(self) -> ActivationResult:
        issues = []

        if not self.extraction_log_path.exists():
            # The data/ directory might not exist yet; check parent
            parent = self.extraction_log_path.parent
            if not parent.exists():
                issues.append(f"Data directory missing: {parent}")
                logger.warning(f"GlobalBitings data dir not found: {parent}")

        rag_tool = Path(self.rag_sync_cmd.split()[0]).expanduser()
        if not rag_tool.exists():
            issues.append(f"RAGResearchTool.py not found: {rag_tool}")
            logger.warning(f"RAGResearchTool.py not found: {rag_tool}")

        if issues:
            return ActivationResult(
                success=False,
                project=self.project_name,
                claim_count=0,
                error="; ".join(issues),
            )

        return ActivationResult(success=True, project=self.project_name, claim_count=0)

    def activate(self, claims: list[dict]) -> ActivationResult:
        readiness = self.check_readiness()
        if not readiness.success:
            return readiness

        if not claims:
            return ActivationResult(
                success=True,
                project=self.project_name,
                claim_count=0,
                details={"msg": "no claims to activate"},
            )

        # Filter to dish/restaurant/ingredient claims
        relevant = [
            c for c in claims
            if c.get("entity_type") in ("dish", "restaurant", "ingredient", "cuisine")
        ]

        if not relevant:
            return ActivationResult(
                success=True,
                project=self.project_name,
                claim_count=0,
                details={"msg": "no dish/restaurant/ingredient claims in batch"},
            )

        written = self._append_to_extraction_log(relevant)
        sync_result = self._trigger_rag_sync()

        return ActivationResult(
            success=True,
            project=self.project_name,
            claim_count=written,
            output_path=str(self.extraction_log_path),
            details={
                "appended": written,
                "rag_sync": sync_result,
                "entity_types": list({c.get("entity_type") for c in relevant}),
            },
        )

    # ── internal ─────────────────────────────────────────────────────────────

    def _append_to_extraction_log(self, claims: list[dict]) -> int:
        """Append claims to extraction_log.jsonl in the existing schema."""
        self.extraction_log_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        for claim in claims:
            record = {
                "source": claim.get("source_url", ""),
                "source_title": claim.get("source_title", ""),
                "extracted_dish": claim.get("claim_text", ""),
                "entity_type": claim.get("entity_type", "dish"),
                "extracted_at": claim.get("extracted_at", datetime.utcnow().isoformat() + "Z"),
                "status": claim.get("status", "confirmed"),
                "project": "cognify-pipeline",
            }
            lines.append(json.dumps(record))

        with open(self.extraction_log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        logger.info(f"Appended {len(lines)} records to {self.extraction_log_path}")
        return len(lines)

    def _trigger_rag_sync(self) -> dict:
        """Run RAGResearchTool.py --sync to pick up new records."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would run: {self.rag_sync_cmd}")
            return {"dry_run": True, "cmd": self.rag_sync_cmd}

        try:
            result = subprocess.run(
                self.rag_sync_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            outcome = {
                "returncode": result.returncode,
                "stdout": result.stdout[:500],
                "stderr": result.stderr[:500],
            }
            if result.returncode != 0:
                logger.warning(f"RAGResearchTool sync non-zero: {result.stderr[:200]}")
            else:
                logger.info(f"RAGResearchTool sync completed successfully")
            return outcome
        except subprocess.TimeoutExpired:
            logger.error("RAGResearchTool sync timed out after 120s")
            return {"error": "timeout"}
        except Exception as e:
            logger.error(f"RAGResearchTool sync error: {e}")
            return {"error": str(e)}
