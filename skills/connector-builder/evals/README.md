# Connector Builder Evals

These evals test whether an LLM follows the `connector-builder` skill flow. They are intentionally credential-free: no live source API calls and no Glean uploads are required. Quality eval prompts should produce validation-ready `.glean` artifacts.

Evals 1-5 are synthetic and include inline API docs, so they should not need internet access. Eval 6 is the real-docs Webex eval: it should fetch or read public Webex docs / the official OpenAPI spec and then produce validation-ready `.glean` artifacts.

## Files

- `trigger_eval_set.json`: prompt-level trigger evals for skill discovery.
- `evals.json`: quality eval prompts and expectation statements.
- `rubric.md`: grading rubric for LLM outputs and generated `.glean` artifacts.

## What These Evals Check

The evals focus on instruction-following:

- confirms or asks for official API docs
- asks for API base URL and read-only credentials, and explains why they improve connector quality
- proceeds docs-only when credentials are unavailable
- creates or describes connector-folder-local `.glean` artifacts
- drafts a plan before code
- records SDK usage mode
- separates test auth from production auth
- states the full-crawl-only limitation for AI-built connectors
- uses the pull, push, auth, and API exploration skills in their own lanes
- avoids source API calls, Glean uploads, and code generation when the prompt asks for planning only
- produces `.glean` artifacts that pass `connector_builder.py validate`
- uses inline docs for synthetic evals and real public docs for the Webex eval

## Running Quality Evals Locally

For each case in `evals.json`:

1. Create a temporary workspace.
2. Make the current connector-builder plugin/skills available to the LLM.
3. Run the eval prompt exactly as written.
4. Save the transcript and any output files in a local, uncommitted workspace.
5. Grade the run against the case's `expectations` and `rubric.md`.
6. Run:

   ```bash
   python scripts/connector_builder/connector_builder.py validate <connector-folder>
   ```

The deterministic validator is required for quality evals. The main signal is still whether the LLM followed the skill workflow, but the artifacts should be complete enough to pass validation.

## Running Trigger Evals

The trigger eval shape follows Scio's `skill_eval` convention. A future runner can execute `trigger_eval_set.json` with a Claude/Cursor-compatible skill trigger harness. Until then, use it as the canonical list of positive and negative trigger prompts.

## CI Plan

These evals are local/manual for now. They are structured so a future CI job can:

1. install the plugin in a temporary workspace,
2. run each prompt through a selected agent runtime,
3. grade expectations,
4. upload transcripts and `.glean` artifacts as build artifacts.

LLM-backed CI should start as non-blocking or nightly because model outputs can be slow, costly, and occasionally flaky.
