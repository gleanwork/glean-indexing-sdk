# Glean Connector SDK

A Python SDK for building custom Glean connectors. This package provides the base classes and utilities to create custom connectors for Glean's indexing APIs.

## Installation

```bash
# Using pip
pip install glean-connector-sdk

# Using uv
uv install glean-connector-sdk
```

## Usage

This SDK supports two types of connectors:

1. **Datasource Connectors** - Used for indexing documents or content from external systems
2. **People Connectors** - Used for indexing employee/identity data

### Datasource Connector Example

```python
from glean.connector_sdk.connector import BaseDatasourceConnector
from glean.connector_sdk.models import DocumentDefinition, IndexingMode

class MyDatasourceConnector(BaseDatasourceConnector):
    name = "my_datasource"
    
    def get_data(self, since=None):
        # Fetch data from your source
        return [{"id": "1", "title": "Document 1", "content": "Content 1"}]
    
    def transform(self, data):
        # Transform data to Glean document format
        return [
            DocumentDefinition(
                id=item["id"],
                title=item["title"],
                content=item["content"]
            )
            for item in data
        ]

# Run the connector
connector = MyDatasourceConnector()
connector.index_data(mode=IndexingMode.FULL)
```

### People Connector Example

```python
from glean.connector_sdk.connector import BasePeopleConnector
from glean.connector_sdk.models import EmployeeDefinition, IndexingMode

class MyPeopleConnector(BasePeopleConnector):
    name = "my_people_connector"
    
    def get_people_data(self, since=None):
        # Fetch people data from your source
        return [{"id": "1", "name": "John Doe", "email": "john@example.com"}]
    
    def transform_people(self, data):
        # Transform data to Glean employee format
        return [
            EmployeeDefinition(
                id=item["id"],
                name=item["name"],
                email=item["email"]
            )
            for item in data
        ]

# Run the connector
connector = MyPeopleConnector()
connector.index_people(mode=IndexingMode.FULL)
```

## Utilities

The SDK provides several utilities to help with the development of connectors:

- `ContentFormatter` - For rendering rich document content using Jinja2 templates
- `BatchProcessor` - For processing data in batches
- `ConnectorMetrics` - For timing operations and emitting metrics

## Testing

The SDK includes a testing harness to help test connectors:

```python
from glean.connector_sdk.testing import ConnectorTestHarness
from myconnector import MyDatasourceConnector

harness = ConnectorTestHarness(MyDatasourceConnector())
harness.run()
harness.validator.assert_documents_posted(count=5)
```

## License

This project is licensed under the MIT License - see the LICENSE file for details. 