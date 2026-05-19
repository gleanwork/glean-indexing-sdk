# AI Layer Workstream

**Author**: Sarthak Kapoor  
**Last updated**: 05/19/2026

## Goals

- Help users build SDK connectors with AI guidance
- Add a knowledge exploration step before connector generation
- Reuse `connector-mcp` for scaffolding, schema mapping, code generation, and execution
- Ensure generated connectors use the SDK pull and push layers
- Keep the first version demo-friendly without changing `connector-mcp`

## Current State

The SDK has reusable pull and push layers. `connector-mcp` already provides an MCP tool workflow for creating connector projects, configuring metadata, inferring schemas, mapping fields, generating code, and running connectors.

What is missing is the reasoning layer before generation. The AI needs to identify the right API docs, understand source-specific nuances, and produce a connector plan before asking `connector-mcp` to generate code.

## What We Want To Add

### Documentation discovery

The AI should first search for source system documentation, prefer official vendor docs, and ask the user which docs should be used as the source of truth.

### Source investigation

After the user confirms docs, the AI should write a source investigation artifact covering auth, endpoints, pagination, rate limits, permissions, incremental strategy, deletes, attachments, and open questions.

### Connector plan

Before generating code, the AI should write a connector plan deciding the SDK base class, pull-layer primitives, push operations, source models, Glean object types, identity/permission strategy, checkpoint strategy, and tests.

### Connector MCP orchestration

Once the investigation and plan exist, the AI can use `connector-mcp` for the mechanical parts: scaffold, config, schema, mappings, build, data client update, run, and inspect.

## V0 Scope

- documentation discovery
- user confirmation of source docs
- source investigation artifact
- connector plan artifact
- `connector-mcp` setup instructions
- Webex-style SDK connector generation demo

## Later Production Work

- first-class `investigate_source` and `plan_connector` tools in `connector-mcp`
- stronger schema validation for `.glean/api_endpoints.json`
- richer skills for auth, pagination, permissions, and testing
- automated review loops inspired by Floo
- recording-based regression tests for generated connectors
