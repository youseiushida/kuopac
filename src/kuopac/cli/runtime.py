"""Per-command runtime helpers.

Build a :class:`KulineClient` honoring the run config, attach optional
``--explain`` hooks, and enforce ``--rate-limit`` pacing.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from ..client import KulineClient
from .config import RunConfig
from .explain import attach


@contextmanager
def build_client(cfg: RunConfig) -> Iterator[KulineClient]:
    """Yield a :class:`KulineClient` wired up with the run config.

    Rate-limit pacing is implemented by attaching a request hook that sleeps
    until the configured minimum interval has elapsed since the previous request.
    """
    client = KulineClient(user_agent=cfg.user_agent, timeout=cfg.timeout)
    attach(client._http, cfg)
    if cfg.rate_limit > 0:
        _install_rate_limit(client, cfg.rate_limit)
    try:
        yield client
    finally:
        client.close()


def _install_rate_limit(client: KulineClient, interval: float) -> None:
    last = [0.0]

    def on_request(_request) -> None:  # type: ignore[no-untyped-def]
        now = time.perf_counter()
        wait = (last[0] + interval) - now
        if wait > 0:
            time.sleep(wait)
        last[0] = time.perf_counter()

    client._http._client.event_hooks.setdefault("request", []).append(on_request)
