"""CLI-level error handling.

``CliError`` is a :class:`click.ClickException` subclass so typer/click respect
its ``exit_code`` automatically — including when commands run inside
``typer.testing.CliRunner``.  The exit codes match ``docs/cli-design.md`` §7.
"""
from __future__ import annotations

import sys

import click
import httpx

from ..errors import (
    CSRFError,
    ForbiddenError,
    KulineError,
    NotFoundError,
    ParseError,
)


EXIT_OK = 0
EXIT_NO_HITS = 1
EXIT_INVALID_ARGUMENT = 2
EXIT_NETWORK = 3
EXIT_PARSE = 4
EXIT_AUTH = 5


def exit_code_for(code: str) -> int:
    return {
        "INVALID_ARGUMENT": EXIT_INVALID_ARGUMENT,
        "NOT_FOUND": EXIT_INVALID_ARGUMENT,
        "FORBIDDEN": EXIT_AUTH,
        "NETWORK": EXIT_NETWORK,
        "PARSE_ERROR": EXIT_PARSE,
        "CSRF_ERROR": EXIT_AUTH,
        "RATE_LIMITED": EXIT_NETWORK,
        "NO_HITS": EXIT_NO_HITS,
    }.get(code, EXIT_INVALID_ARGUMENT)


class CliError(click.ClickException):
    """User-facing error.

    Carries a structured ``code`` plus optional request context so the JSON
    envelope on stderr/stdout can include the matching diagnostic fields.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_url: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code_for(code)
        self.request_url = request_url
        self.http_status = http_status

    def show(self, file=None) -> None:  # type: ignore[override]
        # Imported lazily — formatters depend on click via typer.
        from .formatters._envelope import error as error_envelope
        from .formatters import json_fmt
        print(f"error: [{self.code}] {self.message}", file=sys.stderr)
        if self.code == "NO_HITS":
            return
        payload = error_envelope(
            self.code, self.message,
            request_url=self.request_url, http_status=self.http_status,
        )
        try:
            json_fmt.write(payload, stream=sys.stdout)
        except Exception:  # noqa: BLE001 — keep error path resilient
            pass


def translate(exc: BaseException) -> CliError:
    """Convert a library/network exception into a :class:`CliError`."""
    if isinstance(exc, CliError):
        return exc
    if isinstance(exc, NotFoundError):
        return CliError("NOT_FOUND", str(exc))
    if isinstance(exc, ForbiddenError):
        return CliError("FORBIDDEN", str(exc))
    if isinstance(exc, CSRFError):
        return CliError("CSRF_ERROR", str(exc))
    if isinstance(exc, ParseError):
        return CliError("PARSE_ERROR", str(exc))
    if isinstance(exc, httpx.TimeoutException):
        return CliError("NETWORK", f"request timed out: {exc}")
    if isinstance(exc, httpx.HTTPError):
        return CliError("NETWORK", str(exc))
    if isinstance(exc, KulineError):
        return CliError("INVALID_ARGUMENT", str(exc))
    return CliError("INVALID_ARGUMENT", str(exc))
