"""Basic Temporal workflow example for Glean connectors."""

from basic_workflow.workflow import IndexingWorkflow
from basic_workflow.activities import configure_datasource, execute_indexing

__all__ = ["IndexingWorkflow", "configure_datasource", "execute_indexing"]
