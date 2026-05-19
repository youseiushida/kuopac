"""``--explain`` / ``--explain-json`` HTTP request capture.

Attaches httpx event hooks to a :class:`kuopac._http.HttpSession` so each request
made by a CLI command is logged either to stderr (``--explain``) or into the
``_meta.requests`` array of the JSON envelope (``--explain-json``).
"""
from __future__ import annotations

import sys
import time
from typing import Any

import httpx

from .._http import HttpSession
from .config import RunConfig


def attach(session: HttpSession, cfg: RunConfig) -> None:
    """Wire request/response hooks onto ``session`` so timing + URLs are recorded."""
    if not (cfg.explain or cfg.explain_json):
        return

    client = session._client
    start: dict[int, float] = {}

    def on_request(request: httpx.Request) -> None:
        start[id(request)] = time.perf_counter()

    def on_response(response: httpx.Response) -> None:
        req = response.request
        t0 = start.pop(id(req), None)
        elapsed_ms = int((time.perf_counter() - t0) * 1000) if t0 else None
        info: dict[str, Any] = {
            "url": str(req.url),
            "method": req.method,
            "status": response.status_code,
        }
        if elapsed_ms is not None:
            info["elapsed_ms"] = elapsed_ms
        cfg.add_request(info)
        if cfg.explain:
            tag = f" {elapsed_ms}ms" if elapsed_ms is not None else ""
            print(
                f"> {req.method} {req.url} -> {response.status_code}{tag}",
                file=sys.stderr,
            )

    client.event_hooks.setdefault("request", []).append(on_request)
    client.event_hooks.setdefault("response", []).append(on_response)


def announce_dry_run(method: str, url: str) -> None:
    """Print the request that *would* be made when ``--dry-run`` is on."""
    print(f"[dry-run] {method} {url}", file=sys.stderr)
