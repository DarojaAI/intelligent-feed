"""Agent renderer - generates JSON payloads for AI agents"""

import hmac
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from intel.config import Config
from intel.models import EnrichedItem, Subscription

logger = logging.getLogger(__name__)


class AgentRenderer:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    def render(self, subscription: Subscription, items: list[EnrichedItem], run_id: str) -> list[str]:
        """Render JSON payloads for an agent subscription

        Returns list of output file paths
        """
        output_paths = []

        for item in items:
            payload = self._build_payload(subscription, item, run_id)

            # Write to file
            output_dir = Path(self.config.output_dir) / "agent-payloads"
            output_dir.mkdir(parents=True, exist_ok=True)

            item_id = item.raw.id[:16]  # Truncate for filename
            output_path = output_dir / f"{subscription.id}_{item_id}_{run_id}.json"
            output_path.write_text(json.dumps(payload, indent=2))
            output_paths.append(str(output_path))

            logger.info(f"Wrote agent payload to {output_path}")

            # Send to webhook if configured
            if subscription.delivery.webhook_url:
                self._send_to_webhook(subscription, payload)

        return output_paths

    def _build_payload(self, subscription: Subscription, item: EnrichedItem, run_id: str) -> dict:
        """Build the agent JSON payload"""
        # Determine event type
        if item.raw.source_type == "pypi_api":
            event_type = "package_update"
        elif "vulnerability" in item.topic_tags or "security" in item.topic_tags:
            event_type = "vulnerability"
        elif "model" in item.raw.title.lower() or "gpt" in item.raw.title.lower():
            event_type = "model_release"
        elif "api" in item.topic_tags:
            event_type = "api_change"
        elif "deprecation" in item.topic_tags:
            event_type = "deprecation"
        else:
            event_type = "article"

        # Extract context
        context = {
            "breaking_changes": item.breaking_changes,
        }

        if item.raw.source_type == "pypi_api":
            context["prev_version"] = item.raw.metadata.get("prev_version", "")
            context["new_version"] = item.raw.metadata.get("version", "")
            # Could add migration_guide_url if available

        # Build payload
        payload = {
            "schema_version": "1.0",
            "id": f"upd_{item.raw.id[:20]}",
            "created_at": item.enriched_at.isoformat() + "Z",
            "pipeline_run": f"run_{run_id}",
            "event": {
                "type": event_type,
                "source": item.raw.source_id,
                "title": item.raw.title,
                "summary": item.summary,
                "url": item.raw.url,
            },
            "relevance": {
                "score": item.relevance_scores.get(subscription.id, 0.0),
                "urgency": item.urgency,
                "topics": item.topic_tags,
                "matched_subscription": subscription.id,
                "relevance_reason": f"Matched filters: {', '.join(set(item.topic_tags) & set(subscription.topic_filters))}"
            },
            "suggested_actions": [
                {
                    "action_id": a.action_id,
                    "type": a.type,
                    "description": a.description,
                    "priority": a.priority,
                    "auto_execute": a.auto_execute,
                    "params": a.params,
                }
                for a in item.suggested_actions
            ],
            "context": context,
            "callbacks": {
                "report_outcome": None,
                "acknowledge": None,
                "escalate": None,
            }
        }

        return payload

    def _send_to_webhook(self, subscription: Subscription, payload: dict):
        """Send payload to agent webhook"""
        url = subscription.delivery.webhook_url
        if not url:
            return

        headers = {"Content-Type": "application/json"}

        # Add HMAC signature if secret is configured
        if subscription.delivery.webhook_secret:
            body = json.dumps(payload)
            signature = hmac.new(
                subscription.delivery.webhook_secret.encode(),
                body.encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Intel-Signature"] = f"sha256={signature}"

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info(f"Sent agent payload to webhook: {url}")
        except Exception as e:
            logger.error(f"Error sending to webhook: {e}")
