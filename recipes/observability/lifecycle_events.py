"""Lifecycle event logging recipes for tracking crawl phases."""

import time
import uuid
from typing import Any

from glean.indexing.observability import ConnectorObservability


def track_basic_execution() -> None:
    """Track start and end of connector execution."""
    obs = ConnectorObservability("my_connector")

    obs.start_execution()
    time.sleep(0.1)
    obs.end_execution()


def track_execution_with_context() -> None:
    """Track execution with datasource and crawl mode context."""
    obs = ConnectorObservability(
        connector_name="salesforce_connector",
        datasource="salesforce_prod",
        crawl_mode="incremental",
        run_id="custom-run-id-2024-06-05",
    )

    obs.start_execution()
    time.sleep(0.1)
    obs.end_execution()


def track_failed_execution() -> None:
    """Track execution that fails with an error."""
    obs = ConnectorObservability("my_connector")

    obs.start_execution()

    try:
        raise ValueError("API returned invalid data")
    except Exception as error:
        obs.fail_execution(error)


def track_data_fetch_phase(api_items: list[dict[str, Any]]) -> None:
    """Track data fetching from source API."""
    obs = ConnectorObservability("my_connector")

    obs.log_data_fetch_started()

    start_time = time.time()
    fetched_items = api_items
    duration_ms = int((time.time() - start_time) * 1000)

    obs.log_data_fetch_completed(
        item_count=len(fetched_items),
        duration_ms=duration_ms,
        api_endpoint="/api/v1/items",
    )


def track_transform_phase(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Track data transformation from source format to Glean format."""
    obs = ConnectorObservability("my_connector")

    obs.log_transform_started(item_count=len(raw_items))

    start_time = time.time()
    transformed_items = [transform_item(item) for item in raw_items]
    duration_ms = int((time.time() - start_time) * 1000)

    obs.log_transform_completed(
        input_count=len(raw_items),
        output_count=len(transformed_items),
        duration_ms=duration_ms,
    )

    return transformed_items


def track_batch_upload_phase(documents: list[dict[str, Any]], batch_size: int = 100) -> None:
    """Track batch upload to Glean."""
    obs = ConnectorObservability("my_connector")

    batches = [documents[i : i + batch_size] for i in range(0, len(documents), batch_size)]
    batch_count = len(batches)

    for batch_index, batch in enumerate(batches):
        upload_id = str(uuid.uuid4())
        obs.log_batch_upload_started(
            batch_index=batch_index,
            batch_count=batch_count,
            batch_size=len(batch),
            upload_id=upload_id,
            entity_type="document",
        )

        start_time = time.time()
        try:
            upload_batch_to_glean(batch)
            duration_ms = int((time.time() - start_time) * 1000)

            obs.log_batch_upload_completed(
                batch_index=batch_index,
                batch_count=batch_count,
                batch_size=len(batch),
                duration_ms=duration_ms,
                upload_id=upload_id,
                entity_type="document",
            )
        except Exception as error:
            obs.log_batch_upload_failed(
                batch_index=batch_index,
                batch_count=batch_count,
                error=error,
                upload_id=upload_id,
                entity_type="document",
            )
            raise


def track_full_crawl_lifecycle(api_items: list[dict[str, Any]]) -> None:
    """Track complete crawl from start to finish with all phases."""
    obs = ConnectorObservability(
        connector_name="example_connector",
        datasource="salesforce",
        crawl_mode="full",
    )

    try:
        obs.start_execution()

        obs.log_data_fetch_started()
        start_time = time.time()
        raw_items = api_items
        duration_ms = int((time.time() - start_time) * 1000)
        obs.log_data_fetch_completed(item_count=len(raw_items), duration_ms=duration_ms)

        obs.log_transform_started(item_count=len(raw_items))
        start_time = time.time()
        documents = [transform_item(item) for item in raw_items]
        duration_ms = int((time.time() - start_time) * 1000)
        obs.log_transform_completed(
            input_count=len(raw_items),
            output_count=len(documents),
            duration_ms=duration_ms,
        )

        batches = [documents[i : i + 100] for i in range(0, len(documents), 100)]
        for batch_index, batch in enumerate(batches):
            upload_id = str(uuid.uuid4())
            obs.log_batch_upload_started(
                batch_index=batch_index,
                batch_count=len(batches),
                batch_size=len(batch),
                upload_id=upload_id,
            )
            start_time = time.time()
            upload_batch_to_glean(batch)
            duration_ms = int((time.time() - start_time) * 1000)
            obs.log_batch_upload_completed(
                batch_index=batch_index,
                batch_count=len(batches),
                batch_size=len(batch),
                duration_ms=duration_ms,
                upload_id=upload_id,
            )

        obs.end_execution()

    except Exception as error:
        obs.fail_execution(error)
        raise


def transform_item(item: dict[str, Any]) -> dict[str, Any]:
    """Transform source item to Glean document."""
    return {"id": item["id"], "title": item["name"]}


def upload_batch_to_glean(batch: list[dict[str, Any]]) -> None:
    """Upload batch to Glean indexing API."""
    pass


if __name__ == "__main__":
    from glean.indexing.observability import setup_connector_logging

    setup_connector_logging("example_connector", use_structured_logging=True)

    sample_items = [{"id": str(i), "name": f"Item {i}"} for i in range(250)]

    track_full_crawl_lifecycle(sample_items)
