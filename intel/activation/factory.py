"""
Activation factory — returns the correct activator for a project.
"""

from __future__ import annotations

from intel.activation.base import BaseActivator
from intel.activation.bondnexus import BondNexusActivator
from intel.activation.dynamic_worlock import DynamicWorlockActivator
from intel.activation.globalbitings import GlobalBitingsActivator
from intel.activation.rag_research import RagResearchActivator


def get_activator(project: str, **kwargs) -> BaseActivator:
    """
    Return the activator instance for the given project name.

    Supported projects:
      globalbitings | bond-nexus | rag-research | dynamic-worlock
    """
    activators = {
        "globalbitings": GlobalBitingsActivator,
        "bond-nexus": BondNexusActivator,
        "bond_nexus": BondNexusActivator,
        "rag-research": RagResearchActivator,
        "rag_research": RagResearchActivator,
        "dynamic-worlock": DynamicWorlockActivator,
        "dynamic_worlock": DynamicWorlockActivator,
    }

    cls = activators.get(project) or activators.get(project.replace("-", "_"))
    if cls is None:
        raise ValueError(
            f"Unknown project: {project!r}. "
            f"Supported: {list(set(activators.keys()))}"
        )

    return cls(**kwargs)
