---
name: connector-auth
description: Plan source API authentication for Glean Indexing SDK connectors. Use during connector planning and implementation to separate API-exploration credentials from production connector auth.
---

# Connector Auth

Use this skill when deciding how the connector authenticates to the source API during testing and in production.

## Inputs

- `<connector-folder>/.glean/source_investigation.md`
- `<connector-folder>/.glean/api_inventory.md`
- `<connector-folder>/.glean/connector_plan.md`
- Source API auth docs or OpenAPI security schemes

## Rules

- Separate test/API-exploration auth from production source auth.
- Never persist raw credentials, tokens, cookies, or secrets in `.glean/`, generated code, examples, or logs.
- Store only environment variable names, secret names, auth flow descriptions, scopes, and setup instructions.
- If the user provides a temporary token for exploration, treat it as test-only.
- If OAuth is required, document scopes, token endpoint, refresh behavior, and whether the SDK has enough support or needs developer follow-up.
- If auth docs are missing or ambiguous, ask the user for API auth documentation or sample auth configuration before implementation.

## Supported Auth Plans

Document one of these in `<connector-folder>/.glean/connector_plan.md` and `<connector-folder>/.glean/source_investigation.md`:

- PAT or bearer token via environment variable.
- API key via header or query parameter.
- Basic auth via environment variables.
- OAuth bearer token supplied by the deployment environment.
- OAuth refresh flow, if the source API and SDK support are both clear.
- Custom auth, marked as developer follow-up if it cannot be represented safely with current SDK patterns.

## Required Plan Fields

Before validation, ensure the artifacts include filled-in values for:

- `Test auth`: the auth used for read-only API exploration.
- `Production auth`: the auth flow the generated connector should use in real deployments.
- Required scopes or permissions.
- Environment variable names or secret names.
- Any auth limitations or follow-up work.

Example:

```markdown
- Test auth: Webex developer PAT supplied through WEBEX_API_TOKEN during API exploration.
- Production auth: OAuth bearer token supplied by the connector deployment environment.
```
