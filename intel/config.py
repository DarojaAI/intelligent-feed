"""Configuration loader with environment variable overlay"""

import os
from pathlib import Path
from typing import Any

import yaml

from intel.models import Subscription, DeliveryConfig, StructuredConfig


class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
        self._apply_env_overrides()

    def _load_config(self) -> dict:
        """Load config.yaml"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _apply_env_overrides(self):
        """Apply environment variable overrides"""
        if os.environ.get("ANTHROPIC_API_KEY"):
            self._config["anthropic_api_key"] = os.environ["ANTHROPIC_API_KEY"]

        # Apply to subscriptions
        for sub in self._config.get("subscriptions", []):
            delivery = sub.get("delivery", {})
            if os.environ.get("SLACK_WEBHOOK_URL"):
                delivery["slack_webhook_url"] = os.environ["SLACK_WEBHOOK_URL"]
            if os.environ.get("AGENT_WEBHOOK_URL"):
                delivery["webhook_url"] = os.environ["AGENT_WEBHOOK_URL"]
            if os.environ.get("AGENT_WEBHOOK_SECRET"):
                delivery["webhook_secret"] = os.environ["AGENT_WEBHOOK_SECRET"]
            sub["delivery"] = delivery

        if os.environ.get("OUTCOMES_API_PORT"):
            self._config["outcomes_api_port"] = int(os.environ["OUTCOMES_API_PORT"])

    @property
    def db_path(self) -> str:
        return self._config.get("pipeline", {}).get("db_path", "./data/intel.db")

    @property
    def output_dir(self) -> str:
        return self._config.get("pipeline", {}).get("output_dir", "./output")

    @property
    def log_level(self) -> str:
        return self._config.get("pipeline", {}).get("log_level", "INFO")

    @property
    def anthropic_model(self) -> str:
        return self._config.get("pipeline", {}).get("anthropic_model", "claude-sonnet-4-20250514")

    @property
    def enrichment_batch_size(self) -> int:
        return self._config.get("pipeline", {}).get("enrichment_batch_size", 10)

    @property
    def anthropic_api_key(self) -> str:
        key = self._config.get("anthropic_api_key")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        return key

    @property
    def sources(self) -> list[dict]:
        return self._config.get("sources", [])

    @property
    def tracked_packages(self) -> list[str]:
        return self._config.get("tracked_packages", [])

    @property
    def subscriptions(self) -> list[Subscription]:
        subs = []
        for sub_dict in self._config.get("subscriptions", []):
            delivery_dict = sub_dict.get("delivery", {})
            delivery = DeliveryConfig(
                slack_webhook_url=delivery_dict.get("slack_webhook_url", ""),
                webhook_url=delivery_dict.get("webhook_url", ""),
                webhook_secret=delivery_dict.get("webhook_secret", ""),
            )
            structured_dict = sub_dict.get("structured", {})
            structured = StructuredConfig(
                project=structured_dict.get("project", ""),
                domain=structured_dict.get("domain", "general"),
                entity_filters=structured_dict.get("entity_filters", []),
                activator_config=structured_dict.get("activator_config", {}),
            )
            subs.append(Subscription(
                id=sub_dict["id"],
                name=sub_dict["name"],
                subscriber_type=sub_dict["subscriber_type"],
                topic_filters=sub_dict.get("topic_filters", []),
                relevance_threshold=sub_dict.get("relevance_threshold", 0.5),
                lookback_days=sub_dict.get("lookback_days", 7),
                schedule=sub_dict.get("schedule", ""),
                delivery=delivery,
                structured=structured,
            ))
        return subs

    @property
    def outcomes_api_port(self) -> int:
        return self._config.get("outcomes_api_port", 8080)
