---
name: connector-builder
description: Build Glean Indexing SDK connectors from source-system documentation. Use when planning, generating, validating, or evaluating a custom connector built with the Glean Indexing SDK.
---

# Connector Builder

Use this skill as the top-level workflow for building Glean Indexing SDK connectors with an AI coding agent.

## When To Use

Use this skill when the user wants to build, evaluate, or iterate on a connector for a third-party datasource.

## Workflow Skeleton

1. Confirm official source-system documentation with the user.
2. Explore the source API surface before planning implementation.
3. Draft a user-confirmed plan that captures scope, constraints, and open choices.
4. Write connector planning artifacts under the connector workspace's `.glean/` directory.
5. Validate the planning artifacts before generating code.
6. Generate connector code.
7. Evaluate the connector with local checks and, when credentials are available, a limited source fetch plus test Glean upload.

## Planned Supporting Skills

Future PRs will add focused supporting skills for:

- API exploration
- Pull/source API patterns
- Push/upload patterns
- Auth patterns
- Observability and evaluation

## Current Status

This initial skill is intentionally minimal. It establishes the plugin packaging surface; detailed workflow instructions and local tools will land in follow-up PRs.
