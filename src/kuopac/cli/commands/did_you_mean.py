"""``kuopac did-you-mean <opkey>`` — spellcheck candidates."""
from __future__ import annotations

from typing import Annotated

import typer

from ..._http import HttpSession
from ... import _parse
from ..config import RunConfig
from ..explain import attach
from ..formatters import listing, write


def register(app: typer.Typer) -> None:
    @app.command("did-you-mean", help="直前検索の opkey からスペル候補を取得")
    def did_you_mean_cmd(
        ctx: typer.Context,
        opkey: Annotated[str, typer.Argument(help="検索結果の opkey (B<14桁>)")],
    ) -> None:
        cfg: RunConfig = ctx.obj
        # We don't need a full SearchResult — just hit the endpoint directly so
        # callers can pass a raw opkey from any other tool.
        http = HttpSession(user_agent=cfg.user_agent, timeout=cfg.timeout)
        attach(http, cfg)
        try:
            r = http.get("/opac/opac_spellcheck/", params={
                "lang": "0", "opkey": opkey, "srvce": "0", "tikey": "",
            })
            candidates = [c.term for c in _parse.parse_spellcheck(r.text)]
        finally:
            http.close()
        envelope = listing("Suggestion", candidates, meta=cfg.meta())
        write(envelope, cfg)
