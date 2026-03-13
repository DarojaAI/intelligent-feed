"""Subscription router - matches enriched items to subscriptions"""

from collections import defaultdict
from typing import Optional

from intel.config import Config
from intel.enricher import Enricher
from intel.models import EnrichedItem, Subscription


class Router:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.enricher = Enricher(self.config)

    def route(self, items: list[EnrichedItem], subscriptions: list[Subscription]) -> dict[str, list[EnrichedItem]]:
        """Match enriched items to subscriptions

        Returns a mapping of subscription_id -> list of matching EnrichedItems
        """
        result = defaultdict(list)

        for item in items:
            # Compute relevance scores for all subscriptions
            for sub in subscriptions:
                score = self.enricher.score_relevance(item, sub)
                item.relevance_scores[sub.id] = score

                if score >= sub.relevance_threshold:
                    result[sub.id].append(item)

        return dict(result)

    def route_for_subscription(self, items: list[EnrichedItem], subscription: Subscription) -> list[EnrichedItem]:
        """Get matching items for a single subscription"""
        matched = []
        for item in items:
            score = self.enricher.score_relevance(item, subscription)
            item.relevance_scores[subscription.id] = score
            if score >= subscription.relevance_threshold:
                matched.append(item)

        return matched
