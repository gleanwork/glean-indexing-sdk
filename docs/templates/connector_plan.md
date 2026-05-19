# Connector Plan: <Datasource>

## Goal

<What this connector should index and why.>

## SDK Shape

- Connector base class:
- Data client type:
- Pull layer primitives:
- Push layer operations:

## Source Data Model

| Source object | Glean target | Notes |
| --- | --- | --- |
|  |  |  |

## Glean Datasource Config

- Datasource name:
- Display name:
- Datasource category:
- URL regex:
- Object definitions:

## Identity And Permissions

- Users:
- Groups:
- Memberships:
- Document permissions:

## Pull Implementation

- Auth:
- Pagination:
- Rate limiting:
- Retry:
- Checkpoint:

## Push Implementation

- Full crawl:
- Incremental crawl:
- Deletes:
- Permission updates:

## Tests

- Unit tests:
- Pull + push tests:
- Recording/replay tests:
- Manual validation:

## Open Questions

- <question>

## Connector MCP Steps

- `create_connector`:
- `set_config`:
- `update_schema` / `infer_schema`:
- `confirm_mappings`:
- `build_connector`:
- `get_data_client` / `update_data_client`:
- `run_connector` / `inspect_execution`:
