"""Run-wide CLI configuration held in ``typer.Context.obj``.

Captured by ``main_callback`` from the global flags and read by every command.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Literal

OutputFormat = Literal["table", "json", "ndjson", "tsv", "yaml"]


def default_format() -> OutputFormat:
    """Pick the default output format based on whether stdout is a TTY."""
    return "table" if sys.stdout.isatty() else "json"


@dataclass(slots=True)
class RunConfig:
    """Global options resolved from the top-level callback."""

    format: OutputFormat = "table"
    fields: list[str] | None = None
    quiet: bool = False
    explain: bool = False
    explain_json: bool = False
    no_color: bool = False
    user_agent: str = "kuopac/0.1"
    rate_limit: float = 0.0
    timeout: float = 30.0
    strict: bool = False

    # Populated by ``explain`` hook during command execution.
    requests: list[dict[str, Any]] = field(default_factory=list)

    def add_request(self, info: dict[str, Any]) -> None:
        self.requests.append(info)

    def meta(self) -> dict[str, Any] | None:
        """``_meta`` payload for the JSON envelope (or None to omit)."""
        if not self.explain_json or not self.requests:
            return None
        return {"requests": list(self.requests)}
