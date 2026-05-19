"""``kuopac status <blkey>`` — single-copy live loan status."""
from __future__ import annotations

from typing import Annotated

import typer

from ...models import BLStatusQuery
from ..config import RunConfig
from ..formatters import single, write


def register(app: typer.Typer) -> None:
    @app.command("status", help="個別冊の貸出状況を取得 (1 GET)")
    def status_cmd(
        ctx: typer.Context,
        blkey: Annotated[str, typer.Argument(
            help="単冊の blipkey (例: BL19200695)")],
        phasecd: Annotated[str, typer.Option("--phasecd")] = "50",
        hldstat: Annotated[str, typer.Option("--hldstat")] = "1",
        lkcd: Annotated[str, typer.Option("--lkcd")] = "1",
        prlndflg: Annotated[str, typer.Option("--prlndflg")] = "0",
        blcd: Annotated[str, typer.Option("--blcd")] = "1",
        odrno: Annotated[str, typer.Option("--odrno")] = "",
        bbcd: Annotated[str, typer.Option("--bbcd")] = "1",
        contcd: Annotated[str, typer.Option("--contcd")] = "",
        addmsg: Annotated[str, typer.Option("--addmsg")] = "返却期限",
    ) -> None:
        cfg: RunConfig = ctx.obj
        from ..runtime import build_client
        q = BLStatusQuery(
            blipkey=blkey, phasecd=phasecd, hldstat=hldstat, lkcd=lkcd,
            prlndflg=prlndflg, blcd=blcd, odrno=odrno, bbcd=bbcd,
            contcd=contcd, addmsg=addmsg,
        )
        with build_client(cfg) as kuline:
            condition = kuline.fetch_status(q)
        payload = {
            "blkey": blkey,
            "condition": condition,
            "availability": condition or "available_on_shelf",
        }
        envelope = single("LoanStatus", payload, meta=cfg.meta())
        write(envelope, cfg)
