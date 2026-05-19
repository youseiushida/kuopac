"""``kuopac holdings <bibid...>`` — bulk holdings fetch in one POST."""
from __future__ import annotations

import sys
from typing import Annotated, Optional

import typer

from ...enums import DataType
from ..config import RunConfig
from ..errors import CliError
from ..formatters import single, write
from ..formatters._serialize import to_jsonable
from ..runtime import build_client


def register(app: typer.Typer) -> None:
    @app.command("holdings", help="複数 bibid の所蔵情報を1POSTで取得")
    def holdings_cmd(
        ctx: typer.Context,
        bibids: Annotated[
            Optional[list[str]],
            typer.Argument(help="bibid を1つ以上 (省略時は stdin から1行ずつ)"),
        ] = None,
        datatype: Annotated[
            int, typer.Option("--datatype", help="datatype コード (10=図書)"),
        ] = 10,
        with_: Annotated[
            Optional[list[str]],
            typer.Option("--with", help="live-status"),
        ] = None,
    ) -> None:
        cfg: RunConfig = ctx.obj
        ids: list[str] = list(bibids or [])
        if not ids and not sys.stdin.isatty():
            ids = [line.strip() for line in sys.stdin if line.strip()]
        if not ids:
            raise CliError("INVALID_ARGUMENT",
                           "no bibids given (positional or via stdin)")

        try:
            dt_enum = DataType(datatype)
        except ValueError as e:
            raise CliError("INVALID_ARGUMENT",
                           f"unknown datatype: {datatype}") from e

        live_status = bool(with_ and any(
            token.strip().lower() == "live-status"
            for raw in with_ for token in raw.split(",")
        ))

        with build_client(cfg) as kuline:
            # Pass bibid strings; the client tags them with DataType.BOOK by
            # default, so we patch the datatype if the caller customised it.
            mapping = kuline.holdings(ids) if dt_enum is DataType.BOOK else \
                _holdings_with_dt(kuline, ids, dt_enum)

            if live_status:
                total_copies = sum(
                    1 for v in mapping.values() for h in v if h.status_query
                )
                if total_copies and not cfg.quiet:
                    print(
                        f"> warning: fetching live status for {total_copies} "
                        f"copies ({total_copies} extra requests)",
                        file=sys.stderr,
                    )
                for copies in mapping.values():
                    for h in copies:
                        if h.status_query:
                            kuline.fetch_status(h)

        data = {bibid: to_jsonable(copies) for bibid, copies in mapping.items()}
        envelope = single("HoldingMap", data, meta=cfg.meta())
        write(envelope, cfg)


def _holdings_with_dt(kuline, ids: list[str], dt):  # type: ignore[no-untyped-def]
    """``KulineClient.holdings`` accepts only ``DataType.BOOK`` for raw strings.

    For e-book / serial bulks we forge a lightweight :class:`Book` per id with
    the requested ``data_type`` so each entry posts with the right code.
    """
    from ...models import BibIdentifiers, Book
    from ...enums import Scope as _Scope
    proxies = [
        Book(
            ids=BibIdentifiers(bibid=b),
            title="", publisher_line="",
            data_type=dt, detail_url="", list_index=i,
            scope=_Scope.LOCAL,
        )
        for i, b in enumerate(ids, 1)
    ]
    return kuline.holdings(proxies)
