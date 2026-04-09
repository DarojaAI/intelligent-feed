"""
intel/activation/ — Phase 4 activation routing.

Each project that receives processed claims has an activation handler here.
Handlers take confirmed claim records and push them to the project's
native format / live system.

Activation is triggered by the StructuredRenderer after Cognee add().
"""

from intel.activation.base import ActivationResult, BaseActivator
from intel.activation.globalbitings import GlobalBitingsActivator
from intel.activation.bondnexus import BondNexusActivator
from intel.activation.rag_research import RagResearchActivator
from intel.activation.dynamic_worlock import DynamicWorlockActivator
from intel.activation.factory import get_activator

__all__ = [
    "ActivationResult",
    "BaseActivator",
    "GlobalBitingsActivator",
    "BondNexusActivator",
    "RagResearchActivator",
    "DynamicWorlockActivator",
    "get_activator",
]
