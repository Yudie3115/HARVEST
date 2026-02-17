"""
Deploy Prefect flows with schedules to the Prefect server.

Usage:
    poetry run python scripts/deploy_flows.py [--work-pool <pool>] [--env <env>]

What this script does:
  1. Creates a Prefect work pool (if it doesn't already exist)
  2. Deploys all flows with their default schedules:
       - main_scraper_flow       → daily at 02:00 UTC
       - incremental_update_flow → hourly
       - reprocess_failed_flow   → weekly (Sunday 03:00 UTC)

Requires a running Prefect server (docker compose up -d prefect_server).
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make sure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger  # noqa: E402


WORK_POOL_DEFAULT = "postharvest-pool"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy Post-Harvest Scraper Prefect flows"
    )
    parser.add_argument(
        "--work-pool",
        default=WORK_POOL_DEFAULT,
        help=f"Prefect work pool name (default: {WORK_POOL_DEFAULT})",
    )
    parser.add_argument(
        "--env",
        default="production",
        choices=["development", "staging", "production"],
        help="Deployment environment tag (default: production)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate existing deployments",
    )
    return parser.parse_args()


def ensure_work_pool(pool_name: str) -> None:
    """Create the Prefect work pool if it doesn't exist."""
    try:
        from prefect.client.orchestration import get_client
        import httpx

        async def _create():
            async with get_client() as client:
                try:
                    await client.read_work_pool(pool_name)
                    logger.info(f"Work pool already exists: {pool_name}")
                except Exception:
                    await client.create_work_pool(
                        work_pool={"name": pool_name, "type": "process"}
                    )
                    logger.info(f"Created work pool: {pool_name}")

        asyncio.run(_create())
    except Exception as e:
        logger.warning(f"Could not ensure work pool '{pool_name}': {e}")
        logger.warning("Continuing – you may need to create the pool manually in the Prefect UI.")


def deploy_flows(work_pool: str, env: str) -> None:
    """Build and apply all flow deployments."""
    from prefect import deploy
    from prefect.deployments import Deployment
    from prefect.server.schemas.schedules import CronSchedule

    # Import flows
    from src.flows.orchestration import (
        main_scraper_flow,
        incremental_update_flow,
        reprocess_failed_flow,
    )

    deployments = [
        {
            "flow": main_scraper_flow,
            "name": f"daily-scraper-{env}",
            "schedule": CronSchedule(cron="0 2 * * *", timezone="UTC"),
            "tags": [env, "scheduled", "daily"],
            "description": "Full discovery + processing pipeline – runs daily at 02:00 UTC",
            "parameters": {
                "run_discovery": True,
                "run_processing": True,
                "max_documents": 500,
            },
        },
        {
            "flow": incremental_update_flow,
            "name": f"incremental-update-{env}",
            "schedule": CronSchedule(cron="0 * * * *", timezone="UTC"),
            "tags": [env, "scheduled", "hourly"],
            "description": "Lightweight incremental update – runs every hour",
            "parameters": {},
        },
        {
            "flow": reprocess_failed_flow,
            "name": f"reprocess-failed-{env}",
            "schedule": CronSchedule(cron="0 3 * * 0", timezone="UTC"),
            "tags": [env, "scheduled", "weekly", "maintenance"],
            "description": "Retry failed documents – runs every Sunday at 03:00 UTC",
            "parameters": {"limit": 100},
        },
    ]

    for cfg in deployments:
        flow_obj = cfg.pop("flow")
        try:
            deployment = Deployment.build_from_flow(
                flow=flow_obj,
                work_pool_name=work_pool,
                **cfg,
            )
            deployment_id = deployment.apply()
            logger.info(
                f"Deployed '{cfg['name']}' "
                f"(id={deployment_id}, schedule={cfg['schedule'].cron})"
            )
        except Exception as e:
            logger.error(f"Failed to deploy '{cfg['name']}': {e}")


def print_summary(work_pool: str, env: str) -> None:
    logger.info("")
    logger.info("=" * 60)
    logger.info("  Deployment complete!")
    logger.info(f"  Work pool : {work_pool}")
    logger.info(f"  Environment: {env}")
    logger.info("")
    logger.info("  Scheduled deployments:")
    logger.info(f"    daily-scraper-{env}       → daily  02:00 UTC")
    logger.info(f"    incremental-update-{env}  → hourly")
    logger.info(f"    reprocess-failed-{env}    → weekly 03:00 UTC (Sunday)")
    logger.info("")
    logger.info("  Start a worker to execute flows:")
    logger.info(f"    prefect worker start --pool {work_pool}")
    logger.info("")
    logger.info("  Or trigger manually:")
    logger.info(f"    prefect deployment run 'post_harvest_scraper/daily-scraper-{env}'")
    logger.info("=" * 60)


def main() -> None:
    args = parse_args()

    logger.info(
        f"Deploying flows to Prefect "
        f"(pool={args.work_pool}, env={args.env})"
    )

    ensure_work_pool(args.work_pool)
    deploy_flows(args.work_pool, args.env)
    print_summary(args.work_pool, args.env)


if __name__ == "__main__":
    main()
