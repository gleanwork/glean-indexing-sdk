"""Temporal workflow for scheduled connector execution."""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from scheduled_workflow.activities import configure_datasource, execute_indexing


@dataclass
class ScheduledIndexingInput:
    """Input parameters for scheduled indexing workflow."""

    connector_name: str
    mode: str = "FULL"
    skip_configuration: bool = False


@workflow.defn(sandboxed=False)
class ScheduledIndexingWorkflow:
    """Workflow designed for scheduled execution.

    This workflow is similar to the basic workflow but optimized for
    repeated scheduled execution:
    - Skips configuration by default (assumes it's already set up)
    - Supports incremental mode for hourly syncs
    - Includes execution metadata for monitoring
    """

    @workflow.run
    async def run(self, input: ScheduledIndexingInput) -> dict:
        """Execute the scheduled indexing workflow."""
        workflow.logger.info(
            f"Scheduled execution started: {input.connector_name} (mode={input.mode})"
        )

        results = {
            "connector_name": input.connector_name,
            "mode": input.mode,
            "scheduled_time": workflow.now().isoformat(),
        }

        # Configuration step (usually skipped for scheduled runs)
        if not input.skip_configuration:
            config_result = await workflow.execute_activity(
                configure_datasource,
                input.connector_name,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            results["configuration"] = config_result

        # Indexing step
        execution_result = await workflow.execute_activity(
            execute_indexing,
            args=[input.connector_name, input.mode],
            start_to_close_timeout=timedelta(hours=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        results["execution"] = execution_result
        results["status"] = "completed"

        workflow.logger.info(f"Scheduled execution completed: {input.connector_name}")

        return results
