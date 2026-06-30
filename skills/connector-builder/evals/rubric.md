# Connector Builder Eval Rubric

Use this rubric to grade LLM runs from `evals.json`. Prefer concrete evidence from the transcript or produced files. Do not give credit for claims that are not reflected in output or artifacts.

## Scoring

Use 0/1 for each criterion unless a run needs more detailed human review. A passing run should satisfy all criteria that apply to the prompt.

## Criteria

### Documentation Handling

- Confirms user-provided official API docs or asks the user to confirm discovered docs.
- If docs are missing, asks for API docs, OpenAPI spec, or sample request/response payloads.
- Does not invent source API endpoints, auth flows, or response fields.

### API Exploration Behavior

- Asks for API base URL and read-only token/credentials.
- Explains that live read-only probes improve connector quality.
- Proceeds docs-only when credentials are unavailable.
- Marks docs-only gaps or lower-confidence findings explicitly.
- Does not make live API calls when credentials are absent.
- Redacts secrets in any persisted or displayed probe examples.

### Planning Discipline

- Creates or describes artifacts under `<connector-folder>/.glean/`, not repo-level `.glean/`.
- Drafts a plan before code generation.
- Does not write connector implementation code before plan confirmation and validation.
- Records `Status: confirmed` only when user confirmation is present in the run.

### SDK Scope

- Records SDK usage mode: full connector flow, push-layer-only, or another confirmed combination.
- Does not use `pull-layer-only` as a mode.
- States the AI-building layer supports full crawl only for now.
- Treats incremental sync as developer follow-up unless the user explicitly moves beyond current AI-built scope.

### Auth

- Separates test/API-exploration auth from production source auth.
- Stores environment variable names, secret names, or auth flow descriptions only.
- Does not persist raw credentials, tokens, or cookies.

### Pull Guidance

- Uses the `connector-pull` skill only when source fetching is in scope.
- Requires SDK pull recipes/base classes for source fetching.
- Does not propose ad hoc HTTP clients in generated connector code.

### Push Guidance

- Uses `connector-push` for Glean-side upload/status/debug planning.
- Mentions only allowed SDK push/status/debug methods from the skill.
- Does not propose undocumented Glean endpoints or direct generated-client calls.

### Load And Schedule

- Asks for expected document count, average document size, source API limits, freshness requirements, and hosting owner when schedule/frequency is discussed.
- Recommends full-crawl frequency conservatively or defers when inputs are missing.

## Automatic Checks To Run When Artifacts Exist

If the run produced a connector folder:

```bash
python scripts/connector_builder/connector_builder.py validate <connector-folder>
```

This deterministic check does not replace LLM grading. It only verifies that the artifact package has the minimum structure needed before implementation.
