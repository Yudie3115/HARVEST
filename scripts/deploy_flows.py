"""
Deploy Prefect flows with schedules to the Prefect server.

Usage:
    poetry run python scripts/deploy_flows.py [--work-pool <pool>] [--env <env>]

What this script does:
  1. Points Prefect at the server configured in PREFECT_API_URL (.env / settings)
  2. Creates a Prefect work pool (if it does not already exist)
  3. Deploys all flows with their default schedules:
       - main_scraper_flow       → daily at 02:00 UTC
       - incremental_update_flow → hourly
       - reprocess_failed_flow   → weekly (Sunday 03:00 UTC)

Requires a running Prefect server (docker compose up -d).
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on the path BEFORE any project imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load settings (reads .env) and immediately propagate PREFECT_API_URL into
# os.environ so that the Prefect client picks it up.
from src.config.settings import settings  # noqa: E402

os.environ.setdefault("PREFECT_API_URL", settings.prefect_api_url)

# Prefect imports must come AFTER os.environ is patched
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
    return parser.parse_args()


def ensure_work_pool(pool_name: str) -> None:
    """Create the Prefect work pool if it does not already exist."""
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate

    async def _create() -> None:
        async with get_client() as client:
            try:
                await client.read_work_pool(pool_name)
                logger.info(f"Work pool already exists: {pool_name}")
            except Exception:
                await client.create_work_pool(
                    WorkPoolCreate(name=pool_name, type="process")
                )
                logger.info(f"Created work pool: {pool_name}")

    try:
        asyncio.run(_create())
    except Exception as exc:
        logger.warning(
            f"Could not ensure work pool '{pool_name}': {exc}\n"
            "Continuing – create the pool manually in the Prefect UI if needed."
        )


def deploy_flows(work_pool: str, env: str) -> None:
    """Build and apply all flow deployments."""
    from prefect.deployments import Deployment
    from prefect.server.schemas.schedules import CronSchedule

    from src.flows.orchestration import (
        main_scraper_flow,
        incremental_update_flow,
        reprocess_failed_flow,
        reprocess_stuck_flow,
    )
    from src.flows.manual_ingestion import ingest_manual_upload_flow

    deployments = [
        {
            "flow": main_scraper_flow,
            "name": f"daily-scraper-{env}",
            "schedule": CronSchedule(cron="0 2 * * *", timezone="UTC"),
            "tags": [env, "scheduled", "daily"],
            "description": (
                "Full discovery + processing pipeline – runs daily at 02:00 UTC"
            ),
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
            "description": (
                "Retry failed documents – runs every Sunday at 03:00 UTC"
            ),
            "parameters": {"limit": 100},
        },
        {
            # No schedule — triggered on demand by the Admin UI
            # (POST /admin/documents/reprocess-stuck).
            "flow": reprocess_stuck_flow,
            "name": f"reprocess-stuck-{env}",
            "tags": [env, "manual", "maintenance"],
            "description": (
                "Retry documents stuck in DISCOVERED/QUEUED/PROCESSING or FAILED "
                "– triggered from the Admin UI"
            ),
            "parameters": {"limit": 200},
        },
        {
            # No schedule — one flow run per document submitted through
            # POST /admin/documents/ingest.
            "flow": ingest_manual_upload_flow,
            "name": f"ingest-upload-{env}",
            "tags": [env, "manual", "ingestion"],
            "description": (
                "Ingest a document uploaded or linked from the Admin UI "
                "– one run per document"
            ),
            "parameters": {},
        },
    ]

    failures = []
    for deployment_config in deployments:
        cfg = dict(deployment_config)
        flow_obj = cfg.pop("flow")
        name = cfg["name"]
        try:
            deployment = Deployment.build_from_flow(
                flow=flow_obj,
                work_pool_name=work_pool,
                **cfg,
            )
            deployment_id = deployment.apply()
            schedule = cfg.get("schedule")
            logger.info(
                f"Deployed '{name}' (id={deployment_id}, "
                f"schedule={schedule.cron if schedule else 'on demand'})"
            )
        except Exception as exc:
            logger.error(f"Failed to deploy '{name}': {exc}")
            failures.append(name)

    if failures:
        raise RuntimeError(f"Failed to deploy Prefect flows: {', '.join(failures)}")


def print_summary(work_pool: str, env: str) -> None:
    lines = [
        "",
        "=" * 60,
        "  Deployment complete!",
        f"  Work pool  : {work_pool}",
        f"  Environment: {env}",
        "",
        "  Scheduled deployments:",
        f"    daily-scraper-{env:<12} → daily  02:00 UTC",
        f"    incremental-update-{env:<7} → hourly",
        f"    reprocess-failed-{env:<9} → weekly 03:00 UTC (Sunday)",
        "",
        "  On-demand deployments:",
        f"    reprocess-stuck-{env:<10} → triggered from the Admin UI",
        f"    ingest-upload-{env:<12} → one run per Admin document upload",
        "",
        "  Start a worker to execute flows:",
        f"    prefect worker start --pool {work_pool}",
        "",
        "  Or trigger manually:",
        (
            f"    prefect deployment run "
            f"'post_harvest_scraper/daily-scraper-{env}'"
        ),
        "=" * 60,
    ]
    for line in lines:
        logger.info(line)


def main() -> None:
    args = parse_args()
    logger.info(
        f"Deploying flows to Prefect "
        f"(url={settings.prefect_api_url}, pool={args.work_pool}, env={args.env})"
    )

    ensure_work_pool(args.work_pool)
    deploy_flows(args.work_pool, args.env)
    print_summary(args.work_pool, args.env)


if __name__ == "__main__":
    main()
