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
from glean.indexing.cli.preconditions import check_credentials, project_option, requires

DOCS = "https://developers.glean.com/libraries/indexing-sdk/testing"

CONFIG_FILE = "testing_config.yaml"

PHASES = {
    1: "mocked Glean, the connector's own data clients",
    2: "real source, mocked Glean, recorded to a local cache",
    3: "real source, real Glean",
}


@click.command()
@click.option(
    "--phase",
    type=click.IntRange(1, 3),
    default=1,
    show_default=True,
    help="1 mocked Glean; 2 real source, mocked Glean; 3 both real.",
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
    help="Phase 2: re-record fixtures instead of replaying them.",
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
    phase: int,
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

    Phase 1 mocks Glean but still calls the connector's data clients, so it
    reaches the real source unless the connector is built with a static client.
    Phase 2 is the one that makes source calls repeatable: the first run records
    them, later runs replay from the cache.

    Only phase 3 uploads anything, so only phase 3 needs credentials.
    """
    from glean.indexing.models import IndexingMode

    from glean.indexing.cli.project import instantiate_connector, load_connector

    cli_ctx = context(ctx, output=output, assume_yes=assume_yes, project_dir=project_dir)
    assert cli_ctx.project_dir is not None  # guaranteed by requires(project=True)

    # Phases 1 and 2 mock the push side, so demanding credentials for them would
    # block the two cheapest checks for no reason.
    if phase == 3:
        check_credentials()

    resolved_mode = IndexingMode(mode or cli_ctx.project_config.get("indexing_mode") or "full")
    connector_class = load_connector(cli_ctx.project_dir, cli_ctx.project_config, reference)
    connector = instantiate_connector(connector_class)

    config = _load_config(cli_ctx.project_dir, config_path, refresh_cache, max_items)
    clients = _discover_clients(connector)

    if phase == 2 and not clients:
        raise ValidationFailedError(
            "phase 2 needs at least one data client to record",
            detail=(
                f"No data client attributes were found on {connector_class.__name__}. "
                "Phase 2 wraps each client to record source calls, so there is "
                "nothing for it to do."
            ),
            hint=["glean-idx test --phase 1", "glean-idx test --phase 3"],
            docs=DOCS,
        )

    result = _run_phase(connector, config, clients, phase, resolved_mode)
    data = {
        "connector": connector_class.__name__,
        "phase": phase,
        "fidelity": PHASES[phase],
        "mode": resolved_mode.value,
        "clients": sorted(clients),
        **result,
    }
    emit(data, cli_ctx.output, text=_render(data))


def _load_config(
    project_dir: Path, config_path: Optional[Path], refresh: bool, cap: Optional[int]
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
        # Applied to configured clients and used as the default for the rest,
        # so --max-items means the same thing whatever the config declares.
        for client in config.clients.values():
            client.max_items = cap
        config.clients.setdefault("__default__", ClientConfig(max_items=cap))
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
    connector: Any, config: Any, clients: dict[str, Any], phase: int, mode: Any
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

    method = {
        1: "run_full_mock",
        2: "run_integration_test",
        3: "run_end_to_end",
    }[phase]
    if _is_async(connector):
        method += "_async"

    call = getattr(harness, method)
    try:
        outcome = asyncio.run(call(mode=mode)) if _is_async(connector) else call(mode=mode)
    except CliError:
        raise
    except Exception as exc:  # noqa: BLE001 - reported with its type and message
        raise ValidationFailedError(
            f"phase {phase} failed: {type(exc).__name__}",
            detail=str(exc),
            hint=[
                "glean-idx test --phase 1    start at the cheapest phase"
                if phase > 1
                else "check the connector's transform output",
            ],
            docs=DOCS,
            data={"phase": phase, "error_type": type(exc).__name__},
        ) from exc

    return _summarize(phase, outcome)


def _summarize(phase: int, outcome: Any) -> dict[str, Any]:
    """What the phase produced, in whichever shape it returns.

    Phases 1 and 2 hand back a recording client; phase 3 hands back an indexing
    wait result, or nothing when it did not wait.
    """
    if phase == 3:
        return {"indexing_result": getattr(outcome, "value", None) if outcome else None}

    counts = {
        entity: len(getattr(outcome, f"{entity}_posted", []) or [])
        for entity in ("documents", "users", "groups", "memberships", "employees")
    }
    return {"posted": {entity: count for entity, count in counts.items() if count}}


def _render(data: dict[str, Any]) -> str:
    lines = [
        f"  {data['connector']} - phase {data['phase']} ({data['fidelity']})",
        f"  Mode: {data['mode']}",
        f"  Data clients: {', '.join(data['clients']) or 'none found'}",
    ]
    if data["phase"] == 3:
        lines.append(f"  Indexing: {data['indexing_result'] or 'not waited for'}")
        return "\n".join(lines)

    posted = data["posted"]
    if posted:
        summary = ", ".join(f"{entity}={count}" for entity, count in sorted(posted.items()))
        lines.append(f"  Posted: {summary}")
    else:
        lines += [
            "",
            "  Nothing was posted. A connector that produced no entities will",
            "  index nothing, so this is a failure to investigate, not a pass.",
        ]
    return "\n".join(lines)
