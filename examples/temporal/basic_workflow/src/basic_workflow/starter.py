"""Script to start a workflow execution.

This script demonstrates how to trigger a workflow from the command line
or from another service.
"""

import argparse
import asyncio
import logging
import os
import uuid

from dotenv import load_dotenv
from temporalio.client import Client

from basic_workflow.workflow import IndexingWorkflow, IndexingWorkflowInput

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Must match the task queue used by the worker
TASK_QUEUE = "glean-indexing-queue"


async def start_workflow(
    connector_name: str,
    mode: str = "FULL",
    skip_configuration: bool = False,
) -> str:
    """Start an indexing workflow.

    Args:
        connector_name: Name of the connector to run.
        mode: Indexing mode - "FULL" or "INCREMENTAL".
        skip_configuration: If True, skip the configure_datasource step.

    Returns:
        Workflow ID.
    """
    load_dotenv()

    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_address}")

    client = await Client.connect(
        temporal_address,
        namespace=temporal_namespace,
    )

    # Generate a unique workflow ID
    workflow_id = f"indexing-{connector_name}-{uuid.uuid4().hex[:8]}"

    # Create workflow input
    workflow_input = IndexingWorkflowInput(
        connector_name=connector_name,
        mode=mode,
        skip_configuration=skip_configuration,
    )

    logger.info(f"Starting workflow: {workflow_id}")

    # Start the workflow
    handle = await client.start_workflow(
        IndexingWorkflow.run,
        workflow_input,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Workflow started: {workflow_id}")
    logger.info(
        f"View in Temporal UI: http://localhost:8233/namespaces/default/workflows/{workflow_id}"
    )

    # Optionally wait for result
    result = await handle.result()
    logger.info(f"Workflow completed: {result}")

    return workflow_id


def main() -> None:
    """Entry point for the starter script."""
    parser = argparse.ArgumentParser(description="Start a Glean indexing workflow")
    parser.add_argument(
        "connector_name",
        help="Name of the connector to run",
    )
    parser.add_argument(
        "--mode",
        choices=["FULL", "INCREMENTAL"],
        default="FULL",
        help="Indexing mode (default: FULL)",
    )
    parser.add_argument(
        "--skip-config",
        action="store_true",
        help="Skip datasource configuration step",
    )

    args = parser.parse_args()

    asyncio.run(
        start_workflow(
            connector_name=args.connector_name,
            mode=args.mode,
            skip_configuration=args.skip_config,
        )
    )


if __name__ == "__main__":
    main()
