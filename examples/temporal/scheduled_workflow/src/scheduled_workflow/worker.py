"""Temporal worker for scheduled workflows."""

import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from scheduled_workflow.activities import configure_datasource, execute_indexing
from scheduled_workflow.workflow import ScheduledIndexingWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TASK_QUEUE = "glean-scheduled-indexing-queue"


async def run_worker() -> None:
    """Start the Temporal worker."""
    load_dotenv()

    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_address}")

    client = await Client.connect(
        temporal_address,
        namespace=temporal_namespace,
    )

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ScheduledIndexingWorkflow],
        activities=[configure_datasource, execute_indexing],
    )

    await worker.run()


def main() -> None:
    """Entry point for the worker."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")


if __name__ == "__main__":
    main()
