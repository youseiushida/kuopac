"""``kuopac synopsis <bibid>`` — fetch synopsis + TOC."""
from __future__ import annotations

from typing import Annotated, Optional

import typer

from ...enums import SupplementarySource
from ..config import RunConfig
from ..errors import CliError
from ..formatters import single, write
from ..formatters._serialize import to_jsonable
from ..runtime import build_client


def register(app: typer.Typer) -> None:
    @app.command("synopsis", help="あらすじ・目次 (BookPlus / openBD)")
    def synopsis_cmd(
        ctx: typer.Context,
        identifier: Annotated[
            str, typer.Argument(help="ISBN または bibid"),
        ],
        source: Annotated[
            str, typer.Option("--source", help="bookplus | openbd"),
        ] = "bookplus",
        isbn: Annotated[
            Optional[str],
            typer.Option(
                "--isbn",
                help="ISBN を直接渡す (bibid のみだと detail を引いてしまう)",
            ),
        ] = None,
    ) -> None:
        cfg: RunConfig = ctx.obj
        src_lower = source.lower()
        if src_lower == "bookplus":
            src = SupplementarySource.BOOKPLUS
        elif src_lower == "openbd":
            src = SupplementarySource.OPENBD
        else:
            raise CliError("INVALID_ARGUMENT",
                           f"unknown --source: {source!r}")

        with build_client(cfg) as kuline:
            if isbn:
                sup = kuline.fetch_supplementary(isbn, source=src)
            elif identifier.isdigit() or identifier.startswith(("978", "979")):
                # Heuristic: pure-digit / ISBN-shaped argument → use directly.
                sup = kuline.fetch_supplementary(identifier, source=src)
            else:
                # bibid path — fetch detail first to learn the ISBN.
                book = kuline.detail(identifier)
                if not book.ids.isbn:
                    raise CliError(
                        "NOT_FOUND",
                        f"detail for {identifier!r} has no ISBN; pass --isbn",
                    )
                sup = kuline.fetch_supplementary(book, source=src)

        envelope = single("Supplementary", to_jsonable(sup), meta=cfg.meta())
        write(envelope, cfg)
