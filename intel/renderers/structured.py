"""
StructuredRenderer — Phase 4 integration for intelligent-feed.

Wires the pipeline's EnrichedItems → Cognee cognify() → activation handlers.

Usage in config.yaml:
  subscriptions:
    - id: sub_globalbitings_research
      name: GlobalBitings Research Pipeline
      subscriber_type: structured
      structured:
        project: globalbitings
        domain: cuisine
        entity_filters: [dish, restaurant, ingredient]
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from intel.activation.factory import get_activator
from intel.cognify_client import get_cognify_client
from intel.config import Config
from intel.models import EnrichedItem, Subscription

logger = logging.getLogger(__name__)


class StructuredRenderer:
    """
    Phase 4 renderer that:
      1. Takes matched EnrichedItems from the router
      2. Runs each through Cognee cognify() for structured extraction
      3. Stores results via Cognee add()
      4. Routes to project-specific activation handlers
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._cognify = None

    @property
    def cognify_client(self):
        if self._cognify is None:
            self._cognify = get_cognify_client()
        return self._cognify

    def render(
        self,
        subscription: Subscription,
        items: list[EnrichedItem],
        run_id: str,
    ) -> list[str]:
        """
        Run structured extraction on matched items and activate to project.

        Returns list of output paths (activator-specific).
        """
        if subscription.subscriber_type != "structured":
            raise ValueError(
                f"StructuredRenderer called with subscriber_type={subscription.subscriber_type!r}. "
                f"Only 'structured' is supported."
            )

        project = subscription.structured.project
        domain = subscription.structured.domain
        entity_filters = subscription.structured.entity_filters

        logger.info(
            f"[StructuredRenderer] project={project}, domain={domain}, "
            f"items={len(items)}, entity_filters={entity_filters}"
        )

        output_paths = []

        # ── Step 1: Build raw text documents from EnrichedItems ──────────────
        documents = []
        for item in items:
            doc = self._enriched_item_to_doc(item)
            documents.append(doc)

        # ── Step 2: Run cognify() ─────────────────────────────────────────────
        try:
            cognify_result = self.cognify_client.cognify(
                documents=documents,
                domain=domain,
                project=project,
                extract_entities=True,
                extract_relationships=True,
            )
        except RuntimeError as e:
            # Cognee not installed — log and skip gracefully
            logger.warning(f"cognify() skipped: {e}")
            cognify_result = {"_project": project, "_domain": domain}

        # ── Step 3: Extract claims from cognify result ─────────────────────────
        claims = self._extract_claims_from_result(cognify_result, items)

        # Filter by entity type if configured
        if entity_filters:
            claims = [c for c in claims if c.get("entity_type") in entity_filters]
            logger.info(f"Filtered to {len(claims)} claims matching entity_filters={entity_filters}")

        if not claims:
            logger.info(f"No claims extracted for {project} in run {run_id}")
            return output_paths

        # ── Step 4: Add to Cognee relational store ───────────────────────────
        claim_ids = self.cognify_client.add(claims=claims, project=project)
        logger.info(f"Added {len(claim_ids)} claims to {project} relational store")

        # Write extraction log
        log_path = self._write_extraction_log(claims, run_id, project)
        output_paths.append(log_path)

        # ── Step 5: Activate to project ─────────────────────────────────────
        try:
            activator = get_activator(
                project,
                **{"dry_run": False},
            )
        except ValueError as e:
            logger.error(f"No activator for project={project}: {e}")
            return output_paths

        activation_result = activator.activate(claims)
        logger.info(activator.format_summary(activation_result))

        if activation_result.output_path:
            output_paths.append(activation_result.output_path)

        return output_paths

    # ── internal ──────────────────────────────────────────────────────────────

    def _enriched_item_to_doc(self, item: EnrichedItem) -> str:
        """
        Convert an EnrichedItem into a plain-text document for cognify().
        Combines title + summary + body text.
        """
        parts = [
            f"# {item.raw.title}",
            f"Source: {item.raw.url}",
            f"Published: {item.raw.published_at.isoformat()}",
            "",
            item.summary,  # LLM summary is the best text for extraction
            "",
            "## Content",
            item.raw.body[:5000],  # Truncate to avoid token limits
        ]
        return "\n".join(parts)

    def _extract_claims_from_result(
        self,
        result: dict,
        items: list[EnrichedItem],
    ) -> list[dict]:
        """
        Extract structured claims from Cognee's result dict.

        Cognee's cognify() returns a dict with extracted data.
        We normalise it into our CLAIMS_SCHEMA.

        The result dict structure from Cognee varies; we handle both
        the direct list-of-dicts format and the graph format.
        """
        claims = []
        project = result.get("_project", "default")
        domain = result.get("_domain", "general")
        extracted_at = datetime.utcnow().isoformat() + "Z"

        # Map items by their content hash (use title as proxy)
        item_map = {item.raw.title: item for item in items}

        # Cognee returns extracted data in various shapes
        extracted_data = result.get("extracted_data", []) or result.get("graph", {}).get("nodes", [])

        for record in extracted_data:
            if isinstance(record, dict):
                claim_text = record.get("text") or record.get("claim") or record.get("entity", "")
                if not claim_text:
                    continue

                # Try to match source from original items
                source_title = record.get("source_title", "")
                source_url = record.get("source_url", "")
                if not source_url and source_title in item_map:
                    source_url = item_map[source_title].raw.url

                entity_type = record.get("type") or record.get("entity_type") or domain
                claim_id = self._make_claim_id(claim_text)

                claims.append({
                    "claim_id": claim_id,
                    "source_url": source_url,
                    "source_title": source_title or record.get("source", ""),
                    "claim_text": claim_text,
                    "entity_type": entity_type,
                    "project": project,
                    "domain": domain,
                    "extracted_at": extracted_at,
                    "status": "confirmed",
                })

        # If Cognee returned raw text (no structured extraction), fall back
        # to creating one claim per document from the LLM summary
        if not claims and extracted_data and isinstance(extracted_data, list) and len(extracted_data) == 0:
            for item in items:
                if item.summary:
                    claims.append({
                        "claim_id": self._make_claim_id(item.summary),
                        "source_url": item.raw.url,
                        "source_title": item.raw.title,
                        "claim_text": item.summary,
                        "entity_type": domain,
                        "project": project,
                        "domain": domain,
                        "extracted_at": extracted_at,
                        "status": "confirmed",
                    })

        return claims

    @staticmethod
    def _make_claim_id(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()[:24]

    def _write_extraction_log(
        self,
        claims: list[dict],
        run_id: str,
        project: str,
    ) -> str:
        """Write a local extraction log (pipeline audit trail)."""
        output_dir = Path(self.config.output_dir) / "structured"
        output_dir.mkdir(parents=True, exist_ok=True)

        log_path = output_dir / f"{project}_{run_id}_claims.jsonl"
        import json
        with open(log_path, "w", encoding="utf-8") as f:
            for claim in claims:
                f.write(json.dumps(claim, ensure_ascii=False) + "\n")

        logger.info(f"Wrote extraction log: {log_path}")
        return str(log_path)
