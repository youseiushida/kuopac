"""``kuopac suggest <term>`` — autocomplete suggestions."""
from __future__ import annotations

from typing import Annotated

import typer

from ..config import RunConfig
from ..formatters import listing, write
from ..runtime import build_client


def register(app: typer.Typer) -> None:
    @app.command("suggest", help="OPAC のサジェストAPIを叩いて補完候補を返す")
    def suggest_cmd(
        ctx: typer.Context,
        term: Annotated[str, typer.Argument(help="補完したい先頭文字列")],
    ) -> None:
        cfg: RunConfig = ctx.obj
        with build_client(cfg) as kuline:
            terms = kuline.suggest(term)
        if cfg.limit is not None:
            terms = terms[: cfg.limit]
        envelope = listing("Suggestion", terms, meta=cfg.meta())
        write(envelope, cfg)
