"""Pipeline scheduler and CLI entry point"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from intel.config import Config
from intel.db import init_db, insert_enriched_item
from intel.enricher import Enricher
from intel.fetcher import Fetcher
from intel.models import Subscription
from intel.renderers.agent import AgentRenderer
from intel.renderers.human import HumanRenderer
from intel.router import Router


def setup_logging(config: Config):
    """Configure logging"""
    log_dir = Path(config.output_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = log_dir / f"run_{run_id}.log"

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_pipeline(subscription_id: str = None):
    """Run the full pipeline"""
    config = Config()
    setup_logging(config)
    logger = logging.getLogger(__name__)

    logger.info("=" * 50)
    logger.info("Starting Intelligence Feed Pipeline")
    logger.info("=" * 50)

    run_id = datetime.utcnow().strftime("%Y-%m-%d")

    # Initialize database
    init_db(config.db_path)

    # Get subscriptions to run
    subscriptions = config.subscriptions
    if subscription_id:
        subscriptions = [s for s in subscriptions if s.id == subscription_id]

    if not subscriptions:
        logger.warning("No subscriptions found")
        return

    # Fetch new items
    fetcher = Fetcher(config)
    max_lookback = max(s.lookback_days for s in subscriptions)
    items = fetcher.fetch_all(lookback_days=max_lookback)
    logger.info(f"Fetched {len(items)} new items")

    if not items:
        logger.info("No new items to process")
        return

    # Save raw items to database
    fetcher.save_items(items)

    # Enrich items
    enricher = Enricher(config)
    # Determine subscription type based on what we're processing
    sub_types = set(s.subscriber_type for s in subscriptions)

    if "agent" in sub_types:
        agent_items = enricher.enrich(items, subscription_type="agent")
    else:
        agent_items = []

    if "human" in sub_types:
        human_items = enricher.enrich(items, subscription_type="human")
    else:
        human_items = []

    # Use all enriched items
    all_enriched = agent_items + human_items
    logger.info(f"Enriched {len(all_enriched)} items")

    # Save enriched items to database
    for item in all_enriched:
        insert_enriched_item(init_db(config.db_path), item)

    # Route items to subscriptions
    router = Router(config)

    # Process each subscription
    human_renderer = HumanRenderer(config)
    agent_renderer = AgentRenderer(config)

    for subscription in subscriptions:
        logger.info(f"Processing subscription: {subscription.name}")

        matched_items = router.route_for_subscription(all_enriched, subscription)
        logger.info(f"Matched {len(matched_items)} items for {subscription.id}")

        if not matched_items:
            continue

        if subscription.subscriber_type == "human":
            human_renderer.render(subscription, matched_items, run_id)
        elif subscription.subscriber_type == "agent":
            agent_renderer.render(subscription, matched_items, run_id)

    logger.info("Pipeline completed")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Intelligence Feed System")
    parser.add_argument("--run-now", action="store_true", help="Run pipeline immediately")
    parser.add_argument("--subscription", help="Run only for specific subscription ID")

    args = parser.parse_args()

    config = Config()

    if args.run_now:
        run_pipeline(subscription_id=args.subscription)
    else:
        # Run in scheduled mode
        setup_logging(config)
        logger = logging.getLogger(__name__)

        scheduler = BlockingScheduler()

        # Schedule subscriptions based on their cron expressions
        for subscription in config.subscriptions:
            if subscription.schedule:
                trigger = CronTrigger.from_crontab(subscription.schedule)
                scheduler.add_job(
                    run_pipeline,
                    trigger=trigger,
                    args=[subscription.id],
                    id=subscription.id,
                    name=subscription.name,
                )
                logger.info(f"Scheduled {subscription.name} with cron: {subscription.schedule}")

        logger.info("Starting scheduler...")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
