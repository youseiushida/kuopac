"""``kuopac detail <id>`` — full bibliographic record."""
from __future__ import annotations

import sys
from typing import Annotated, Optional

import typer

from ...enums import Scope, SupplementarySource
from ...models import Holding
from .._listflag import split_list_flag
from ..config import RunConfig
from ..errors import CliError
from ..formatters import single, write
from ..formatters._serialize import to_jsonable
from ..runtime import build_client

# Heuristic: KULINE bibids start with BB/EB/SB; CiNii ncids with BA/BB/BC/BD/BN.
# The "BB" prefix overlaps both — when ambiguous we default to local since
# anonymous browsers usually want their home institution first.
_CINII_PREFIXES = ("BA", "BC", "BD", "BN")


def _guess_scope(ident: str) -> Scope:
    head = ident[:2].upper()
    if head in _CINII_PREFIXES:
        return Scope.CINII
    return Scope.LOCAL


_WITH_VALID = {"holdings", "synopsis", "bookplus",
               "synopsis-openbd", "openbd", "live-status"}


def register(app: typer.Typer) -> None:
    @app.command("detail", help="書誌詳細を取得")
    def detail_cmd(
        ctx: typer.Context,
        identifier: Annotated[str, typer.Argument(help="bibid または ncid")],
        scope_: Annotated[
            str, typer.Option("--scope", help="auto | local | cinii"),
        ] = "auto",
        with_: Annotated[
            Optional[list[str]],
            typer.Option(
                "--with",
                help="追加情報: holdings | synopsis | synopsis-openbd | "
                     "live-status (複数指定可: 繰り返し or カンマ区切り)",
            ),
        ] = None,
    ) -> None:
        cfg: RunConfig = ctx.obj

        scope_lower = scope_.lower()
        if scope_lower not in ("auto", "local", "cinii"):
            raise CliError("INVALID_ARGUMENT", f"--scope: {scope_!r}")
        if scope_lower == "auto":
            scope = _guess_scope(identifier)
        elif scope_lower == "cinii":
            scope = Scope.CINII
        else:
            scope = Scope.LOCAL

        with_set = set(split_list_flag(with_, lowercase=True))
        bad = with_set - _WITH_VALID
        if bad:
            raise CliError("INVALID_ARGUMENT",
                           f"unknown --with values: {sorted(bad)}")

        with build_client(cfg) as kuline:
            book = kuline.detail(identifier, scope=scope)

            data = to_jsonable(book)

            if "holdings" in with_set:
                bibid = book.ids.bibid
                if bibid:
                    holding_map = kuline.holdings([bibid])
                    holdings = holding_map.get(bibid, [])
                    book.holdings = holdings
                    data["holdings"] = to_jsonable(holdings)

            if "live-status" in with_set:
                copies = [h for h in book.holdings
                          if isinstance(h, Holding) and h.status_query]
                if copies:
                    if not cfg.quiet:
                        print(
                            f"> warning: fetching live status for {len(copies)} "
                            f"copies ({len(copies)} extra requests)",
                            file=sys.stderr,
                        )
                    for h in copies:
                        kuline.fetch_status(h)
                    data["holdings"] = to_jsonable(book.holdings)

            wants_bookplus = with_set & {"synopsis", "bookplus"}
            if wants_bookplus:
                sup = kuline.fetch_supplementary(
                    book, source=SupplementarySource.BOOKPLUS,
                )
                data["_supplementary"] = to_jsonable(sup)

            wants_openbd = with_set & {"synopsis-openbd", "openbd"}
            if wants_openbd:
                sup = kuline.fetch_supplementary(
                    book, source=SupplementarySource.OPENBD,
                )
                data["_supplementary_openbd"] = to_jsonable(sup)

        envelope = single("BookDetail", data, meta=cfg.meta())
        write(envelope, cfg)
