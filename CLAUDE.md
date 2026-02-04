# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python SDK for building custom Glean indexing connectors. Provides base classes and utilities to create connectors that fetch data from external systems and upload to Glean's indexing APIs.

## Commands

Uses [mise](https://mise.jdx.dev/) (`brew install mise`) for toolchain and task management with `uv` for Python dependencies.

```bash
# Setup
mise run setup                # Create venv and install all dependencies

# Testing
mise run test                 # Run all tests
mise run test:watch           # Run tests in watch mode
mise run test:cov             # Run tests with coverage

# Linting
mise run lint                 # Run all linters (ruff, pyright, readme)
mise run lint:fix             # Auto-fix lint issues and format code

# Building
mise run build                # Build the package
```

Run a single test:
```bash
uv run pytest tests/unit_tests/test_base_connector.py -v
uv run pytest tests/unit_tests/test_base_connector.py::TestClassName::test_method -v
```

## Architecture

### Core Abstractions

**Connector hierarchy** (`src/glean/indexing/connectors/`):
- `BaseConnector` - Abstract base defining `get_data()`, `transform()`, `index_data()`
- `BaseDatasourceConnector` - For document/content indexing (fits in memory)
- `BaseStreamingDatasourceConnector` - For large/paginated datasets (yields data via sync generator)
- `BaseAsyncStreamingDatasourceConnector` - For large datasets with async APIs (yields data via async generator)
- `BasePeopleConnector` - For employee/identity indexing

**Data clients** (`src/glean/indexing/connectors/`):
- `BaseDataClient[T]` - Fetches all data at once, returns `Sequence[T]`
- `BaseStreamingDataClient[T]` - Yields data incrementally via `Generator[T]`
- `BaseAsyncStreamingDataClient[T]` - Yields data incrementally via `AsyncGenerator[T]`

### Pattern: Implementing a Connector

1. Define data type as `TypedDict`
2. Create data client extending `BaseDataClient[YourType]`
3. Create connector extending `BaseDatasourceConnector[YourType]`
4. Set `configuration: CustomDatasourceConfig` class attribute
5. Implement `transform()` to convert source data to `DocumentDefinition`

### Key Modules

- `models.py` - Type definitions, `IndexingMode`, `DocumentDefinition`, etc.
- `common/glean_client.py` - API client wrapper (uses env vars `GLEAN_INSTANCE`, `GLEAN_INDEXING_API_TOKEN`)
- `common/batch_processor.py` - Batches data for upload
- `observability/` - Logging decorators and metrics tracking
- `testing/` - `ConnectorTestHarness`, `MockGleanClient` for testing without API calls

## Code Style

- Line length: 160 characters
- Docstrings: Google style
- Type hints required (pyright basic mode)
- Ruff for linting and formatting
