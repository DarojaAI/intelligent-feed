"""Base activator class and shared types."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ActivationResult:
    """Result of a single activation run."""

    success: bool
    project: str
    claim_count: int
    output_path: Optional[str] = None
    error: Optional[str] = None
    activated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    details: dict[str, Any] = field(default_factory=dict)


class BaseActivator(ABC):
    """
    Abstract base for project-specific activation handlers.

    Each project implements:
      - check_readiness() — are all dependencies present?
      - activate(claims) — push claims to the project
      - project_name — string identifier matching the `project` field in claims
    """

    project_name: str = "base"

    def check_readiness(self) -> ActivationResult:
        """
        Verify all prerequisites for activation are met (paths exist,
        APIs reachable, etc.). Returns an ActivationResult.
        """
        raise NotImplementedError

    @abstractmethod
    def activate(self, claims: list[dict]) -> ActivationResult:
        """
        Activate a list of confirmed claims for this project.

        Args:
            claims: List of claim dicts from CogneeClient.add()

        Returns:
            ActivationResult describing what was done
        """
        ...

    def format_summary(self, result: ActivationResult) -> str:
        """Human-readable summary of the activation result."""
        status = "✅" if result.success else "❌"
        msg = (
            f"{status} [{self.project_name}] "
            f"{result.claim_count} claims → {result.output_path or 'no output'}"
        )
        if result.error:
            msg += f" | Error: {result.error}"
        return msg
