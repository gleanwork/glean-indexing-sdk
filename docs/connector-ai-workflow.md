# AI Connector Builder Workflow

This workflow layers source-system research and planning on top of `connector-mcp`.

The goal is to avoid generating connector code before the AI has confirmed the right documentation and understood source-specific details.

## Prerequisites

Configure `connector-mcp` in Cursor:

```json
{
  "mcpServers": {
    "glean-connector": {
      "command": "npx",
      "args": ["-y", "@gleanwork/connector-mcp"],
      "type": "stdio"
    }
  }
}
```

## Workflow

1. Start with the datasource goal.
2. Search for official API, auth, pagination, rate-limit, and webhook docs.
3. Ask the user to confirm the source-of-truth docs.
4. Write `.glean/source_docs.json`.
5. Write `.glean/source_investigation.md` and `.glean/api_endpoints.json`.
6. Write `.glean/connector_plan.md`.
7. Use `connector-mcp` tools for scaffold, schema, mappings, build, run, and inspect.
8. Patch generated code to use SDK pull and push primitives.

## Required Gate

Do not call `build_connector` until these files exist:

```text
.glean/source_docs.json
.glean/source_investigation.md
.glean/connector_plan.md
```

If docs cannot be found, ask the user for an API docs link or sample API response.
