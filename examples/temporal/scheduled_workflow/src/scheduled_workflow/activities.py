"""Temporal activities for scheduled connector execution."""

from datetime import datetime

from temporalio import activity

from glean.indexing.models import IndexingMode

from scheduled_workflow.connector import create_connector


@activity.defn
def configure_datasource(connector_name: str) -> dict:
    """Configure the datasource in Glean."""
    activity.logger.info(f"Configuring datasource for connector: {connector_name}")

    connector = create_connector(connector_name)
    connector.configure_datasource()

    return {
        "status": "configured",
        "connector_name": connector_name,
        "timestamp": datetime.now().isoformat(),
    }


@activity.defn
def execute_indexing(connector_name: str, mode: str = "FULL") -> dict:
    """Execute the indexing process."""
    activity.logger.info(f"Executing indexing for connector: {connector_name} (mode={mode})")

    connector = create_connector(connector_name)

    indexing_mode = IndexingMode.FULL if mode == "FULL" else IndexingMode.INCREMENTAL
    connector.index_data(mode=indexing_mode)

    return {
        "status": "completed",
        "connector_name": connector_name,
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
    }
