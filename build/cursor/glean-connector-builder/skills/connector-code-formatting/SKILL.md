---
name: connector-code-formatting
description: Organize a Glean Indexing SDK connector into a maintainable handler, per-object service, repository, and parser structure. Use before writing connector implementation code when the connector builder needs a consistent code layout or when restructuring an existing connector.
---

# Connector Code Formatting

Use this skill with `connector-builder` to define the connector's file and responsibility boundaries. This skill governs structure and separation of concerns only; the connector builder and its supporting skills govern SDK APIs, source authentication, crawl semantics, document mappings, indexing behavior, tests, and deployment.

## Target layout

Start from a connector-level `handler.py` and organize the implementation by object type:

```text
connector-folder/
├── handler.py
├── models/                         # Request, response, and source/domain models
├── service/
│   ├── documents_service.py
│   └── users_service.py
├── repository/
│   ├── document_repository.py
│   └── user_repository.py
└── parser/
    ├── document_parser.py
    └── user_parser.py
```

Use the source system's object names in filenames. Add `__init__.py` files when the connector is packaged as a Python package. If the SDK workflow requires a specific module-level `create_connector()` factory or connector class, keep that required entry point in `handler.py` or expose it there; do not add a competing entry point just to fit this layout.

For a connector with one object type, keep the same boundaries rather than collapsing everything into one file. For multiple object types, create a service, repository, and parser for each independently indexed type. Shared code belongs in a small, clearly named module only when it is genuinely shared; do not create generic base classes preemptively.

## Responsibilities

### `handler.py`

Make the handler the composition and orchestration boundary:

- Construct source clients, repositories, parsers/services, and the SDK connector using dependency injection where the SDK workflow supports it.
- Load the confirmed connector configuration and wire credentials through the mechanism chosen by `connector-auth`; do not embed secrets.
- Invoke one service per object type, combine their results when required by the SDK flow, and delegate final indexing/upload to the SDK connector boundary.
- Own lifecycle concerns such as startup, shutdown, scheduling hooks, and top-level error handling when they are required by the runtime.
- Keep object-specific fetching, parsing, and field mapping out of the handler.

The handler may coordinate calls, but repositories and parsers must never call Glean indexing APIs. There should be one obvious path from handler to service to repository/parser to the SDK indexing boundary.

### `service/`

Create one service per object type. A service coordinates the use case for that type:

1. Ask its repository for the source records.
2. Pass records to its parser.
3. Return the SDK-ready results to the handler/connector boundary.

Services may coordinate related repository calls needed to assemble one object type, but should not contain raw pagination, cache implementation, or detailed field-to-field parsing. Keep cross-object orchestration in the handler unless it is part of one object's service use case.

### `repository/`

Create one repository per object type. A repository is the source-data boundary:

- Own source crawling, pagination, filtering, retries, and cache access for its object type.
- Hide source-client details from services and parsers.
- Return source models or typed records, not SDK `DocumentDefinition`/identity payloads.
- Keep full and incremental retrieval paths separate when both are required by the confirmed plan.
- Make cache behavior explicit and safe: do not treat a partial or failed crawl as a complete replacement dataset.

A repository may delegate HTTP or SDK-specific source calls to an injected client. Do not put Glean indexing calls or presentation/SDK document construction in a repository.

### `parser/`

Create one parser per object type. A parser converts a source model into the SDK output selected by the connector builder:

- Keep source-to-indexed-field mapping, IDs, URLs, timestamps, content, metadata, and permissions in the relevant parser.
- Keep parsing deterministic and side-effect free where practical.
- Handle malformed optional source fields locally and apply the confirmed fallback behavior consistently.
- Do not fetch source data, access repositories, manage caches, or upload to Glean from a parser.

If a parser needs reusable formatting logic, extract a narrow helper with a domain-specific name. Do not create a catch-all utility module.

### `models/`

Make `models/` a required contract boundary for the connector. Define the source API request and response shapes, pagination/filter request types, source/domain object models, and other typed data contracts here. Keep models independent of services, repositories, parsers, and indexing side effects. SDK output types belong at the parser/connector boundary; models describe the data those layers exchange.

## Implementation order

Follow this order after the connector plan is confirmed:

1. List the indexed object types and their relationships from the confirmed plan.
2. Create the package skeleton and `handler.py` entry point.
3. Add one service, repository, and parser per object type.
4. Add the request, response, and source/domain models required by each object type under `models/`.
5. Implement source retrieval inside repositories, object-type orchestration inside services, and source-to-SDK conversion inside parsers.
6. Wire the services and the required SDK connector/factory in the handler.
7. Use the connector builder's pull, push, auth, observability, deployment, and testing skills for their respective behavior; do not duplicate their instructions here.

Keep the dependency direction one-way:

```text
handler → service → repository → source clients
       ↘ service → parser → SDK output types
```

A service can depend on its parser, repository, and relevant models. A parser must not depend on a service or repository, and a repository must not depend on a parser. Models must remain lower-level contracts and must not import services, repositories, parsers, or indexing handlers. Avoid circular imports by passing dependencies into constructors and keeping shared types in `models/`.

## Scope boundaries

Keep this skill focused on connector structure. Do not introduce scaffolding that is not required by the confirmed SDK connector plan:

- No repository-wide `constants.py` for dynamic/default configuration that the reusable SDK or connector configuration already provides.
- No versioned namespaces, setup scripts, runtime configuration trees, or duplicate client/metrics abstractions merely for familiarity.
- No speculative support for object types, incremental crawling, or configuration options outside the confirmed plan.

Prefer the smallest structure that preserves the boundaries above. The code-writing skill decides which SDK classes and public library APIs are correct; this skill decides where that code lives and which layer owns it.

## Review checklist

Before considering the structure complete, verify:

- `handler.py` is the only orchestration/indexing boundary.
- Every indexed object type has a corresponding service, repository, and parser.
- Repositories return source records and own crawling/cache concerns.
- Parsers perform source-to-SDK conversion without network or indexing side effects.
- Services coordinate one object type without becoming a second handler.
- SDK-required connector classes/factories remain intact; this skill only controls code placement and responsibility boundaries.
- No unnecessary configuration/constants/runtime scaffolding was introduced.
- Imports flow from handler toward lower layers without cycles.
