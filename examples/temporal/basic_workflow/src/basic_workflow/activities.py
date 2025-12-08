"""Temporal activities for connector execution.

Activities are the units of work that can fail and be retried.
Each activity should be idempotent when possible.
"""

from datetime import datetime

from temporalio import activity

from glean.indexing.models import IndexingMode

from basic_workflow.connector import create_connector


@activity.defn
def configure_datasource(connector_name: str) -> dict:
    """Configure the datasource in Glean.

    This activity registers the datasource configuration with Glean.
    It should be run at least once before indexing, and whenever
    the schema changes.

    Args:
        connector_name: Name of the connector to configure.

    Returns:
        Status dictionary with timestamp.
    """
    activity.logger.info(f"Configuring datasource for connector: {connector_name}")

    connector = create_connector(connector_name)
    connector.configure_datasource()

    activity.logger.info(f"Datasource configured successfully: {connector_name}")

    return {
        "status": "configured",
        "connector_name": connector_name,
        "timestamp": datetime.now().isoformat(),
    }


@activity.defn
def execute_indexing(connector_name: str, mode: str = "FULL") -> dict:
    """Execute the indexing process.

    This activity fetches data from the source system, transforms it,
    and uploads it to Glean.

    Args:
        connector_name: Name of the connector to execute.
        mode: Indexing mode - "FULL" or "INCREMENTAL".

    Returns:
        Status dictionary with metrics.
    """
    activity.logger.info(f"Executing indexing for connector: {connector_name} (mode={mode})")

    connector = create_connector(connector_name)

    indexing_mode = IndexingMode.FULL if mode == "FULL" else IndexingMode.INCREMENTAL
    connector.index_data(mode=indexing_mode)

    activity.logger.info(f"Indexing completed for connector: {connector_name}")

    return {
        "status": "completed",
        "connector_name": connector_name,
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
    }
