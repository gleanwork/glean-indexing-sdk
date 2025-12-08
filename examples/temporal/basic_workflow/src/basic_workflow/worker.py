"""Temporal worker for running connector workflows.

The worker connects to the Temporal cluster and polls for workflow
and activity tasks to execute.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from basic_workflow.activities import configure_datasource, execute_indexing
from basic_workflow.workflow import IndexingWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Task queue name - workers and workflow starters must use the same queue
TASK_QUEUE = "glean-indexing-queue"


async def run_worker() -> None:
    """Start the Temporal worker."""
    load_dotenv()

    # Get Temporal connection details from environment
    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_address} (namespace: {temporal_namespace})")

    # Connect to Temporal
    client = await Client.connect(
        temporal_address,
        namespace=temporal_namespace,
    )

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    # Create and run the worker
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[IndexingWorkflow],
        activities=[configure_datasource, execute_indexing],
    )

    # Run the worker until interrupted
    await worker.run()


def main() -> None:
    """Entry point for the worker."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")


if __name__ == "__main__":
    main()
