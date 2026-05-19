"""``kuopac schema [<TypeName>]`` — JSON Schema for the public dataclasses."""
from __future__ import annotations

from typing import Annotated, Optional

import typer

from ..config import RunConfig
from ..formatters import listing, single, write
from ..schema_gen import list_types, schema_for


def register(app: typer.Typer) -> None:
    @app.command("schema", help="dataclass の JSON Schema を出力")
    def schema_cmd(
        ctx: typer.Context,
        type_name: Annotated[
            Optional[str],
            typer.Argument(help="型名 (省略時は名前一覧)"),
        ] = None,
    ) -> None:
        cfg: RunConfig = ctx.obj
        if type_name is None:
            envelope = listing("TypeName", list_types(), meta=cfg.meta())
        else:
            envelope = single(
                "Schema", schema_for(type_name), meta=cfg.meta(),
            )
        write(envelope, cfg)
