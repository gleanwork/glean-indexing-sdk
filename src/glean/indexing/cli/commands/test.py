"""`glean-idx test` — run a connector at one of three fidelities.

The SDK's `TestHarness` already defines the progression: mock Glean, then the
real source against a mocked Glean, then both real. This exposes it so that
checking a connector does not require writing a test file first, which is what
made the middle phases go unused.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

import click

from glean.indexing.cli.errors import CliError, ValidationFailedError
from glean.indexing.cli.main import context, global_options
from glean.indexing.cli.output import emit
from glean.indexing.cli.preconditions import (
    check_credentials,
    missing_credentials,
    project_option,
    requires,
)

DOCS = "https://developers.glean.com/libraries/indexing-sdk/testing"

CONFIG_FILE = "testing_config.yaml"

#: Phase name -> what it does and which harness method runs it. Insertion order
#: is the progression from cheapest to most consequential, which is what lets a
#: failure point at an earlier phase. Names match the headings in the
#: connector-testing skill rather than inventing a second vocabulary.
PHASES: dict[str, dict[str, str]] = {
    "mock": {
        "method": "run_full_mock",
        "summary": "mocked Glean, the connector's own data clients",
    },
    "integration": {
        "method": "run_integration_test",
        "summary": "real source, mocked Glean, recorded to a local cache",
    },
    "live": {
        "method": "run_end_to_end",
        "summary": "real source, real Glean",
    },
}

#: The cheapest phase, and the one a failure elsewhere should point back to.
MOCK = "mock"

#: The only phase that contacts Glean, and so the only one needing credentials.
LIVE = "live"

#: The only phase that records source calls to a cache.
INTEGRATION = "integration"

#: Runs every phase in order. The connector-testing workflow is a batch by
#: nature -- it reports "phases run and skipped" -- and assembling that from
#: three separate invocations loses which ones were even attempted.
ALL = "all"


@click.command()
@click.option(
    "--phase",
    type=click.Choice([*PHASES, ALL]),
    default="mock",
    show_default=True,
    help="How much of the real world to involve. See the description.",
)
@click.option(
    "--connector",
    "reference",
    default=None,
    metavar="MODULE:CLASS",
    help="Connector to test. Defaults to the project file's connector.",
)
@click.option(
    "--mode",
    type=click.Choice(["full", "incremental"]),
    default=None,
    help="Indexing mode. Defaults to the project file's indexing_mode, or full.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=f"Harness config. Defaults to {CONFIG_FILE} in the project, when present.",
)
@click.option(
    "--refresh-cache",
    is_flag=True,
    help="integration: re-record fixtures instead of replaying them.",
)
@click.option(
    "--max-items",
    type=int,
    default=None,
    help="Cap items fetched per data client. Applies to every client.",
)
@project_option
@global_options
@click.pass_context
@requires(project=True)
def test(
    ctx: click.Context,
    phase: str,
    reference: Optional[str],
    mode: Optional[str],
    config_path: Optional[Path],
    refresh_cache: bool,
    max_items: Optional[int],
    project_dir: Optional[Path],
    output: Optional[str],
    assume_yes: bool,
) -> None:
    """Exercise a connector without writing a test file.

    \b
    --phase mock          nothing real. Glean is mocked, and the connector's
                          own data clients are called as-is -- so this still
                          reaches the source unless the connector was built
                          with a static client.
    --phase integration   the source is real and Glean is mocked. The first run
                          records source calls to a local cache and later runs
                          replay them, which is what makes results repeatable.
    --phase live          both are real. This uploads to Glean, and a full
                          crawl removes documents the run does not produce.
    --phase all           every phase in order, stopping at the first failure.
                          A phase that cannot run is skipped and reported, not
                          treated as a failure.

    Each phase involves more of the real world than the one above it, so start
    at mock and move down. Only live contacts Glean, so only live needs
    credentials.
    """
    from glean.indexing.cli.project import instantiate_connector, load_connector
    from glean.indexing.models import IndexingMode

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes, project_dir=project_dir)
    assert cli_ctx.project_dir is not None  # guaranteed by requires(project=True)

    plan = list(PHASES) if phase == ALL else [phase]
    batch = phase == ALL

    # Only live contacts Glean, so demanding credentials for the others would
    # block the two cheapest checks for no reason. In a batch, a missing token
    # skips live rather than failing everything -- the workflow reports live as
    # skipped, and the earlier phases still carry real information.
    if LIVE in plan and not batch:
        check_credentials()

    resolved_mode = IndexingMode(mode or cli_ctx.project_config.get("indexing_mode") or "full")
    connector_class = load_connector(cli_ctx.project_dir, cli_ctx.project_config, reference)
    connector = instantiate_connector(connector_class)

    # Clients are discovered first because --max-items has to name them: the
    # harness looks each one up by attribute name.
    clients = _discover_clients(connector)
    config = _load_config(
        cli_ctx.project_dir, config_path, refresh_cache, max_items, sorted(clients)
    )

    # Asking for a phase that cannot run is an error; running a batch steps over
    # what does not apply.
    if phase == INTEGRATION and not clients:
        raise ValidationFailedError(
            f"the {INTEGRATION} phase needs at least one data client to record",
            detail=_no_clients_detail(connector_class.__name__),
            hint=[f"glean-idx test --phase {name}" for name in (MOCK, LIVE)],
            docs=DOCS,
        )

    phases = _run_plan(connector, config, clients, plan, resolved_mode, batch=batch)
    data = {
        "connector": connector_class.__name__,
        "mode": resolved_mode.value,
        "clients": sorted(clients),
        "phases": phases,
    }

    failures = [entry for entry in phases if entry["status"] == "failed"]
    if failures:
        raise ValidationFailedError(
            f"the {failures[0]['phase']} phase failed: {failures[0]['error_type']}",
            detail=failures[0]["detail"],
            hint=[f"glean-idx test --phase {MOCK}    start at the cheapest phase"]
            if failures[0]["phase"] != MOCK
            else ["check the connector's transform output"],
            docs=DOCS,
            data=data,
        )

    emit(data, cli_ctx.output, text=_render(data))


def _no_clients_detail(connector_name: str) -> str:
    return (
        f"No data client attributes were found on {connector_name}. The "
        f"{INTEGRATION} phase wraps each client to record source calls, so there "
        "is nothing for it to do."
    )


def _skip_reason(phase: str, clients: dict[str, Any], connector_name: str) -> Optional[str]:
    """Why a batch should step over this phase instead of stopping.

    Only consulted for `--phase all`. A phase that cannot run is not the same as
    one that ran and failed, and conflating them would mean a machine without
    Glean credentials could never report on the phases it *can* do.
    """
    if phase == LIVE:
        missing = missing_credentials()
        if missing:
            return "no Glean credentials: " + ", ".join(missing)
    if phase == INTEGRATION and not clients:
        return _no_clients_detail(connector_name)
    return None


def _run_plan(
    connector: Any,
    config: Any,
    clients: dict[str, Any],
    plan: list[str],
    mode: Any,
    *,
    batch: bool,
) -> list[dict[str, Any]]:
    """Run each phase in order, stopping at the first real failure.

    A later phase cannot pass when an earlier one failed, and in the case of
    live it would upload the output that just proved wrong.
    """
    results: list[dict[str, Any]] = []
    for phase in plan:
        reason = _skip_reason(phase, clients, type(connector).__name__) if batch else None
        if reason is not None:
            results.append({"phase": phase, "status": "skipped", "reason": reason})
            continue

        try:
            summary = _run_phase(connector, config, clients, phase, mode)
        except ValidationFailedError as exc:
            if not batch:
                raise
            results.append(
                {
                    "phase": phase,
                    "status": "failed",
                    "error_type": (exc.data or {}).get("error_type", type(exc).__name__),
                    "detail": exc.detail or exc.format_message(),
                }
            )
            break

        results.append(
            {
                "phase": phase,
                "status": "ran",
                "fidelity": PHASES[phase]["summary"],
                **summary,
            }
        )
    return results


def _load_config(
    project_dir: Path,
    config_path: Optional[Path],
    refresh: bool,
    cap: Optional[int],
    client_names: list[str],
) -> Any:
    """Harness config from the given file, the project's default, or defaults."""
    from glean.indexing.testing.harness import ClientConfig, TestConfig

    path = config_path or (project_dir / CONFIG_FILE)
    if config_path is not None and not path.exists():
        raise ValidationFailedError(
            f"no harness config at {path}",
            hint=[f"omit --config to use {CONFIG_FILE} or the built-in defaults"],
            docs=DOCS,
        )

    config = TestConfig.from_yaml(path) if path.exists() else TestConfig()
    if refresh:
        config.refresh_cache = True
    if cap is not None:
        # Named one client at a time. The harness reads
        # `config.clients.get(attr_name, ClientConfig())`, so a client absent
        # from this mapping silently keeps the built-in default -- and a project
        # without a config file has no entries at all, so a cap applied any other
        # way would do nothing in the common case.
        for name in {*config.clients, *client_names}:
            config.clients.setdefault(name, ClientConfig())
            config.clients[name].max_items = cap
    return config


def _discover_clients(connector: Any) -> dict[str, Any]:
    """The connector's data clients, keyed by attribute name.

    The harness wants this mapping and cannot derive it, but the connector
    already holds the clients as attributes, so asking the caller to name them
    again would only be a chance to get it wrong.
    """
    from glean.indexing.connectors.base_async_streaming_data_client import (
        BaseAsyncStreamingDataClient,
    )
    from glean.indexing.connectors.base_data_client import BaseDataClient
    from glean.indexing.connectors.base_streaming_data_client import BaseStreamingDataClient

    kinds = (BaseDataClient, BaseStreamingDataClient, BaseAsyncStreamingDataClient)
    return {
        name: value
        for name, value in vars(connector).items()
        if not name.startswith("_") and isinstance(value, kinds)
    }


def _is_async(connector: Any) -> bool:
    from glean.indexing.connectors import BaseAsyncStreamingDatasourceConnector

    return isinstance(connector, BaseAsyncStreamingDatasourceConnector)


def _run_phase(
    connector: Any, config: Any, clients: dict[str, Any], phase: str, mode: Any
) -> dict[str, Any]:
    """Run one phase and summarize what it produced."""
    from glean.indexing.testing.harness import TestHarness

    try:
        harness = TestHarness(connector=connector, config=config, clients=clients)
    except TypeError as exc:
        # The harness requires a BaseConnector; `run` accepts anything with
        # index_data, so this is reachable with a hand-rolled connector.
        raise ValidationFailedError(
            f"{type(connector).__name__} cannot be tested by the harness",
            detail=str(exc),
            hint=["extend one of the BaseConnector subclasses", "glean-idx run"],
            docs=DOCS,
        ) from exc

    method = PHASES[phase]["method"]
    if _is_async(connector):
        method += "_async"

    call = getattr(harness, method)
    try:
        outcome = asyncio.run(call(mode=mode)) if _is_async(connector) else call(mode=mode)
    except CliError:
        raise
    except Exception as exc:  # noqa: BLE001 - reported with its type and message
        raise ValidationFailedError(
            f"the {phase} phase failed: {type(exc).__name__}",
            detail=str(exc),
            hint=[
                f"glean-idx test --phase {MOCK}    start at the cheapest phase"
                if phase != MOCK
                else "check the connector's transform output",
            ],
            docs=DOCS,
            data={"phase": phase, "error_type": type(exc).__name__},
        ) from exc

    return _summarize(phase, outcome)


def _summarize(phase: str, outcome: Any) -> dict[str, Any]:
    """What the phase produced, in whichever shape it returns.

    The mock and integration phases hand back a recording client; live hands
    back an indexing wait result, or nothing when it did not wait.
    """
    if phase == LIVE:
        return {"indexing_result": getattr(outcome, "value", None) if outcome else None}

    counts = {
        entity: len(getattr(outcome, f"{entity}_posted", []) or [])
        for entity in ("documents", "users", "groups", "memberships", "employees")
    }
    return {"posted": {entity: count for entity, count in counts.items() if count}}


def _render(data: dict[str, Any]) -> str:
    """The run report: which phases ran, which were skipped, and what they produced."""
    lines = [
        f"  {data['connector']} ({data['mode']} crawl)",
        f"  Data clients: {', '.join(data['clients']) or 'none found'}",
        "",
    ]
    for entry in data["phases"]:
        lines += _render_phase(entry)

    skipped = [entry["phase"] for entry in data["phases"] if entry["status"] == "skipped"]
    if skipped:
        # Stated plainly: a batch that quietly stepped over live would read as a
        # clean end-to-end pass when Glean was never contacted.
        lines += [
            "",
            f"  Skipped: {', '.join(skipped)}.",
            "  Phases that did not run prove nothing about the ones they cover.",
        ]
    return "\n".join(lines)


def _render_phase(entry: dict[str, Any]) -> list[str]:
    phase = entry["phase"]
    if entry["status"] == "skipped":
        return [f"  - {phase}: skipped ({entry['reason']})"]
    if entry["status"] == "failed":
        return [f"  - {phase}: FAILED ({entry['error_type']})"]

    if phase == LIVE:
        return [f"  - {phase}: indexing {entry['indexing_result'] or 'not waited for'}"]

    posted = entry.get("posted") or {}
    if posted:
        counts = ", ".join(f"{name}={count}" for name, count in sorted(posted.items()))
        return [f"  - {phase}: posted {counts}"]
    return [
        f"  - {phase}: posted nothing",
        "      A connector that produced no entities will index nothing, so this",
        "      is a failure to investigate, not a pass.",
    ]
