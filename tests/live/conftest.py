"""Live integration test harness.

These tests hit the real KULINE server.  They are **opt-in**: by default
``pytest`` skips everything marked ``live``.  Enable with either::

    pytest --live                # CLI flag
    KUOPAC_LIVE=1 pytest         # environment variable

Two safety nets:

1. **Reachability skip** — if the landing page can't be reached at session
   start, every live test is skipped (so a KULINE outage doesn't fail CI).
2. **Polite pacing** — a session-scoped :class:`KulineClient` enforces a
   minimum interval between requests (default 1.5s, matching
   ``docs/opac-spec.md`` §0.4).
"""
from __future__ import annotations

import os
import time
from typing import Iterator

import pytest

from kuopac import KulineClient


# ---------------------------------------------------------------------------
# Opt-in plumbing
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run live integration tests against the real KULINE server.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    enabled = config.getoption("--live") or bool(os.getenv("KUOPAC_LIVE"))
    if enabled:
        return
    skip_live = pytest.mark.skip(
        reason="live tests opt-in: pass --live or set KUOPAC_LIVE=1",
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


# ---------------------------------------------------------------------------
# Polite, session-scoped client
# ---------------------------------------------------------------------------

_RATE_LIMIT_SECONDS = float(os.getenv("KUOPAC_LIVE_RATE_LIMIT", "1.5"))


def _install_pacing(client: KulineClient, interval: float) -> None:
    """Attach a request hook that ensures ``interval`` seconds between requests."""
    last = [0.0]

    def hook(_request) -> None:  # type: ignore[no-untyped-def]
        wait = (last[0] + interval) - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        last[0] = time.perf_counter()

    client._http._client.event_hooks.setdefault("request", []).append(hook)


@pytest.fixture(scope="session")
def kuline() -> Iterator[KulineClient]:
    """A polite, session-scoped client.

    Reachability is verified once: ``suggest('a')`` exercises the GET path,
    legacy-cipher SSL, and JSON parsing all in one cheap call.  Failure here
    skips every test rather than reporting them as failures.
    """
    c = KulineClient()
    _install_pacing(c, _RATE_LIMIT_SECONDS)
    try:
        c.suggest("a")
    except Exception as e:  # noqa: BLE001 — translate any error into skip
        c.close()
        pytest.skip(f"KULINE unreachable from this environment: {e}")
    try:
        yield c
    finally:
        c.close()
