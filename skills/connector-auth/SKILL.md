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
- If test auth and production auth differ, both must be described in the initial confirmed plan before implementation and the difference must be tracked as a production-readiness gap. Implement, configure, and validate the production mechanism before calling the connector complete or beginning deployment.
- Never persist raw credentials, tokens, cookies, or secrets in `.glean/`, generated code, examples, or logs.
- Store only environment variable names, secret names, auth flow descriptions, scopes, and setup instructions.
- If the user provides a temporary token for exploration, treat it as test-only.
- If OAuth is required, document scopes, token endpoint, refresh behavior, and whether the SDK has enough support. Missing support required by the production plan blocks completion until it is implemented and validated.
- If auth docs are missing or ambiguous, ask the user for API auth documentation or sample auth configuration before implementation.

## Supported Auth Plans

Document one of these in `<connector-folder>/.glean/connector_plan.md` and `<connector-folder>/.glean/source_investigation.md`:

- PAT or bearer token via environment variable.
- API key via header or query parameter.
- Basic auth via environment variables.
- OAuth bearer token supplied by the deployment environment.
- OAuth refresh flow backed by deployed cloud token storage.

For a deployed OAuth refresh flow:

- Set `oauth_token_persistence: true` in `glean_deployment.yaml`.
- Initialize `SOURCE_OAUTH_TOKEN_STATE` in `.env` with the access token, refresh token, and expiry timestamp before running `glean-deploy secrets upload`.
- Build `OAuth2TokenProvider` with the store returned by `get_oauth2_token_store_from_environment()`. If no token state is configured, skip the refresh flow.
- Do not persist refreshed tokens in connector files or process-local storage.

## Required Plan Fields

Before validation, ensure the artifacts include filled-in values for:

- `Test auth`: the auth used for read-only API exploration.
- `Production auth`: the auth flow the generated connector should use in real deployments.
- `Auth validation gap`: anything production auth requires that was not exercised during exploration/testing.
- Required scopes or permissions.
- Environment variable names or secret names.
- Any auth limitations or production-readiness gaps, their required resolution, and current validation status.

Example:

```markdown
- Test auth: Temporary bearer token supplied through SOURCE_API_TOKEN during API exploration.
- Production auth: OAuth bearer token supplied by the connector deployment environment.
```
