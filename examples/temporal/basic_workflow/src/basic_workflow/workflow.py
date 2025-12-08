"""Temporal workflow for connector execution.

Workflows orchestrate activities and define the overall execution flow.
Workflow code must be deterministic - all I/O happens in activities.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities using their function references
with workflow.unsafe.imports_passed_through():
    from basic_workflow.activities import configure_datasource, execute_indexing


@dataclass
class IndexingWorkflowInput:
    """Input parameters for the indexing workflow."""

    connector_name: str
    mode: str = "FULL"
    skip_configuration: bool = False


@workflow.defn(sandboxed=False)
class IndexingWorkflow:
    """Workflow for executing a Glean connector.

    This workflow orchestrates the two main steps of connector execution:
    1. Configure the datasource in Glean (optional, can be skipped)
    2. Execute the indexing process

    Each step is an activity with its own retry policy and timeout.
    """

    @workflow.run
    async def run(self, input: IndexingWorkflowInput) -> dict:
        """Execute the indexing workflow.

        Args:
            input: Workflow input parameters.

        Returns:
            Dictionary with execution results.
        """
        workflow.logger.info(f"Starting indexing workflow for: {input.connector_name}")

        results = {
            "connector_name": input.connector_name,
            "mode": input.mode,
        }

        # Step 1: Configure datasource (optional)
        if not input.skip_configuration:
            config_result = await workflow.execute_activity(
                configure_datasource,
                input.connector_name,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=10),
                    backoff_coefficient=2.0,
                ),
            )
            results["configuration"] = config_result
            workflow.logger.info(f"Configuration complete: {config_result}")

        # Step 2: Execute indexing
        execution_result = await workflow.execute_activity(
            execute_indexing,
            args=[input.connector_name, input.mode],
            start_to_close_timeout=timedelta(hours=2),  # Adjust based on data volume
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=5),
            ),
        )
        results["execution"] = execution_result

        workflow.logger.info(f"Indexing workflow completed for: {input.connector_name}")
        results["status"] = "completed"

        return results
