"""Script to create and manage Temporal schedules.

Temporal Schedules provide cron-like scheduling with durable execution.
"""

import argparse
import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleSpec

from scheduled_workflow.workflow import ScheduledIndexingInput, ScheduledIndexingWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TASK_QUEUE = "glean-scheduled-indexing-queue"


async def create_schedule(
    connector_name: str,
    schedule_id: str,
    cron_expression: str = "0 2 * * *",  # Default: 2 AM daily
    mode: str = "FULL",
) -> None:
    """Create a schedule for a connector.

    Args:
        connector_name: Name of the connector to schedule.
        schedule_id: Unique ID for the schedule.
        cron_expression: Cron expression for scheduling.
        mode: Indexing mode - "FULL" or "INCREMENTAL".
    """
    load_dotenv()

    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_address}")

    client = await Client.connect(
        temporal_address,
        namespace=temporal_namespace,
    )

    # Create the schedule
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            ScheduledIndexingWorkflow.run,
            ScheduledIndexingInput(
                connector_name=connector_name,
                mode=mode,
                skip_configuration=True,  # Skip config for scheduled runs
            ),
            id=f"scheduled-{connector_name}",
            task_queue=TASK_QUEUE,
        ),
        spec=ScheduleSpec(
            cron_expressions=[cron_expression],
        ),
    )

    await client.create_schedule(
        schedule_id,
        schedule,
    )

    logger.info(f"Schedule created: {schedule_id}")
    logger.info(f"Cron expression: {cron_expression}")
    logger.info(f"Connector: {connector_name} (mode={mode})")
    logger.info(
        f"View in Temporal UI: http://localhost:8233/namespaces/default/schedules/{schedule_id}"
    )


async def list_schedules() -> None:
    """List all schedules."""
    load_dotenv()

    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    client = await Client.connect(
        temporal_address,
        namespace=temporal_namespace,
    )

    logger.info("Listing schedules:")
    async for schedule in client.list_schedules():
        logger.info(f"  - {schedule.id}")


async def delete_schedule(schedule_id: str) -> None:
    """Delete a schedule."""
    load_dotenv()

    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    client = await Client.connect(
        temporal_address,
        namespace=temporal_namespace,
    )

    handle = client.get_schedule_handle(schedule_id)
    await handle.delete()

    logger.info(f"Schedule deleted: {schedule_id}")


def main() -> None:
    """Entry point for schedule management."""
    parser = argparse.ArgumentParser(description="Manage Temporal schedules")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create schedule
    create_parser = subparsers.add_parser("create", help="Create a new schedule")
    create_parser.add_argument("connector_name", help="Name of the connector")
    create_parser.add_argument("--schedule-id", required=True, help="Unique schedule ID")
    create_parser.add_argument(
        "--cron",
        default="0 2 * * *",
        help="Cron expression (default: '0 2 * * *' = 2 AM daily)",
    )
    create_parser.add_argument(
        "--mode",
        choices=["FULL", "INCREMENTAL"],
        default="FULL",
        help="Indexing mode",
    )

    # List schedules
    subparsers.add_parser("list", help="List all schedules")

    # Delete schedule
    delete_parser = subparsers.add_parser("delete", help="Delete a schedule")
    delete_parser.add_argument("schedule_id", help="Schedule ID to delete")

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(
            create_schedule(
                connector_name=args.connector_name,
                schedule_id=args.schedule_id,
                cron_expression=args.cron,
                mode=args.mode,
            )
        )
    elif args.command == "list":
        asyncio.run(list_schedules())
    elif args.command == "delete":
        asyncio.run(delete_schedule(args.schedule_id))


if __name__ == "__main__":
    main()
