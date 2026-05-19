"""``kuopac version`` command."""
from __future__ import annotations

import typer

from ... import __version__


def register(app: typer.Typer) -> None:
    @app.command("version", help="バージョンを表示")
    def version_cmd() -> None:
        typer.echo(__version__)
