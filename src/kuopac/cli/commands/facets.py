"""``kuopac facets <opkey>`` — facet aggregates for an opkey."""
from __future__ import annotations

from typing import Annotated, Optional

import typer

from ...enums import FacetType, Scope
from ...models import SearchResult
from ..config import RunConfig
from ..errors import CliError
from ..formatters import single, write
from ..formatters._serialize import to_jsonable
from ..runtime import build_client

ALL_FACETS = list(FacetType)


def _resolve_types(spec: Optional[list[str]], all_types: bool) -> list[FacetType]:
    if all_types and spec:
        raise CliError("INVALID_ARGUMENT", "--all-types and --type are exclusive")
    if all_types:
        return list(ALL_FACETS)
    if not spec:
        return [FacetType.DATATYPE, FacetType.YEAR,
                FacetType.PUBLISHER, FacetType.SUBJECT]
    out: list[FacetType] = []
    for raw in spec:
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            # Accept either the enum value (the wire code) or its lowercase name.
            try:
                out.append(FacetType(token))
                continue
            except ValueError:
                pass
            try:
                out.append(FacetType[token.upper()])
            except KeyError as e:
                raise CliError(
                    "INVALID_ARGUMENT", f"unknown facet type: {token!r}",
                ) from e
    return out


def register(app: typer.Typer) -> None:
    @app.command("facets", help="検索 opkey に対するファセット集計を取得")
    def facets_cmd(
        ctx: typer.Context,
        opkey: Annotated[str, typer.Argument(help="検索結果の opkey")],
        type_: Annotated[
            Optional[list[str]],
            typer.Option("--type", help="ファセット種別 (繰り返し or カンマ区切り)"),
        ] = None,
        all_types: Annotated[
            bool, typer.Option("--all-types", help="9種類を全部取得"),
        ] = False,
        top: Annotated[
            Optional[int], typer.Option("--top", help="各種別で上位 N バケット"),
        ] = None,
        scope_: Annotated[
            str, typer.Option("--scope", help="local | cinii"),
        ] = "local",
        page_size: Annotated[int, typer.Option("--page-size")] = 20,
        sort: Annotated[int, typer.Option("--sort")] = 6,
    ) -> None:
        cfg: RunConfig = ctx.obj
        scope = Scope.CINII if scope_.lower() == "cinii" else Scope.LOCAL
        types = _resolve_types(type_, all_types)

        # Build a minimal SearchResult shell — the facets() endpoint only needs
        # opkey/scope/page_size/sort.
        shell = SearchResult(
            books=[], total=0, opkey=opkey, scope=scope,
            page_start=1, page_size=page_size, sort=sort,
            query_summary="", raw_url="",
        )
        with build_client(cfg) as kuline:
            facets = kuline.facets(shell, types=types)
        data: dict[str, dict] = {}
        for ft, info in facets.items():
            obj = to_jsonable(info)
            if top:
                obj["values"] = obj.get("values", [])
                obj["values"] = sorted(obj["values"], key=lambda v: -(v.get("count") or 0))[:top]
            data[ft.name] = obj
        envelope = single("FacetMap", data, meta=cfg.meta())
        write(envelope, cfg)
