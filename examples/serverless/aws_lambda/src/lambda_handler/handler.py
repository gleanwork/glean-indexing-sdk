"""AWS Lambda handler for Glean connector execution.

This handler is invoked by Lambda when triggered by EventBridge
or other AWS services.
"""

import json
import logging
import os
from typing import Any

from glean.indexing.models import IndexingMode
from lambda_handler.connector import SampleConnector, SampleDataClient

# Configure logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler for connector execution.

    This handler supports two modes:
    - FULL: Complete re-index of all documents
    - INCREMENTAL: Index only documents changed since last sync

    Args:
        event: Lambda event data. Can include:
            - mode: "FULL" or "INCREMENTAL" (default: "FULL")
            - configure: Whether to configure datasource (default: False)
        context: Lambda context object.

    Returns:
        Response dictionary with status and metadata.
    """
    logger.info(f"Lambda invoked with event: {json.dumps(event)}")

    # Get configuration from environment
    source_api_url = os.environ.get("SOURCE_API_URL", "https://docs.company.com")
    source_api_key = os.environ.get("SOURCE_API_KEY", "")

    # Parse event parameters
    mode_str = event.get("mode", "FULL")
    should_configure = event.get("configure", False)

    # Determine indexing mode
    mode = IndexingMode.FULL if mode_str == "FULL" else IndexingMode.INCREMENTAL

    logger.info(f"Running connector in {mode_str} mode")

    try:
        # Create the data client
        data_client = SampleDataClient(
            api_url=source_api_url,
            api_key=source_api_key,
        )

        # Create the connector
        connector = SampleConnector(
            name="lambda_docs",
            data_client=data_client,
        )

        # Configure datasource if requested
        if should_configure:
            logger.info("Configuring datasource...")
            connector.configure_datasource()

        # Execute indexing
        logger.info(f"Starting indexing (mode={mode_str})...")
        connector.index_data(mode=mode)

        logger.info("Indexing completed successfully")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "completed",
                    "mode": mode_str,
                    "message": "Indexing completed successfully",
                }
            ),
        }

    except Exception as e:
        logger.error(f"Indexing failed: {str(e)}", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "error": str(e),
                }
            ),
        }
