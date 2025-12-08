# Simple Wiki Connector Example

A minimal example demonstrating how to build a datasource connector using the Glean Indexing SDK.

## Overview

This example shows the core pattern for any connector:

1. **Define your data model** (`models.py`) - TypedDict representing your source data
2. **Create a data client** (`data_client.py`) - Fetches data from your source system
3. **Build the connector** (`connector.py`) - Transforms data to Glean's format
4. **Run it** (`main.py`) - Configure and execute indexing

## Project Structure

```
wiki_connector/
  src/wiki_connector/
    __init__.py
    models.py       # WikiPageData TypedDict
    data_client.py  # WikiDataClient - fetches from source
    connector.py    # CompanyWikiConnector - transforms to Glean format
    main.py         # Entry point
  pyproject.toml
  .env.example
  README.md
```

## Prerequisites

- Python 3.10+
- Glean API credentials

## Setup

1. Install the example:

```bash
cd examples/simple/wiki_connector
pip install -e .
```

2. Create your environment file:

```bash
cp .env.example .env
```

3. Edit `.env` with your credentials:

```bash
GLEAN_INSTANCE="your-instance"
GLEAN_INDEXING_API_TOKEN="your-token"

# Optional: Configure your wiki source
WIKI_BASE_URL="https://wiki.company.com"
WIKI_API_TOKEN="your-wiki-token"
```

## Running

```bash
python -m wiki_connector.main
```

## Adapting for Your Use Case

To build your own connector:

1. **Replace the data model** - Define a TypedDict matching your source data structure
2. **Implement the data client** - Call your source system's API in `get_source_data()`
3. **Update the transform** - Map your fields to Glean's `DocumentDefinition`
4. **Configure the datasource** - Update `CustomDatasourceConfig` with your datasource details

## Testing Locally

The example includes static data so you can test the transform logic without a real wiki:

```bash
python -c "from wiki_connector import WikiDataClient; print(WikiDataClient('url', 'token').get_source_data())"
```

## Next Steps

Once you have a working connector, see the other examples for production deployment:

- [Temporal Workflows](../../temporal/) - Durable execution with retry and scheduling
- [AWS Lambda](../../serverless/aws_lambda/) - Serverless deployment
- [Docker/Kubernetes](../../containers/) - Container-based deployment
