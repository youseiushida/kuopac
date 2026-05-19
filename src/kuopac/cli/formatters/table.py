"""``--format=table`` writer using Rich.

Dispatches on the envelope ``type`` to pick a renderer.  Falls back to a
generic key/value or list table when the type is unknown.
"""
from __future__ import annotations

import sys
from typing import Any, TextIO

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ---- per-type rendering ----------------------------------------------------


def _availability_style(value: str | None) -> str:
    if not value:
        return ""
    if "貸出中" in value or "返却" in value or "取置" in value:
        return "red"
    if value == "available_on_shelf":
        return "green"
    if value == "online":
        return "blue"
    if value == "remote":
        return "magenta"
    return ""


def _render_search_result(console: Console, data: dict[str, Any]) -> None:
    summary = data.get("query_summary") or ""
    total = data.get("total", 0)
    page_start = data.get("page_start", 1)
    page_size = data.get("page_size", 0)
    scope = data.get("scope", "LOCAL")
    header = f"{total:,} 件ヒット  ({scope}  page start={page_start} size={page_size})"
    if summary:
        header += f"\n検索条件: {summary}"
    console.print(Panel.fit(header, border_style="cyan"))

    books = data.get("books") or []
    if not books:
        console.print("[dim](no books on this page)[/dim]")
        return
    has_holdings = any(b.get("holdings") for b in books)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("bibid", style="yellow")
    table.add_column("title", overflow="fold")
    table.add_column("publication", overflow="fold")
    if has_holdings:
        table.add_column("location")
        table.add_column("call_no")
        table.add_column("availability")
    for b in books:
        row = [
            str(b.get("list_index", "")),
            b.get("bibid") or b.get("ids", {}).get("ncid") or "",
            (b.get("title") or "").strip(),
            (b.get("publisher_line") or "").strip(),
        ]
        if has_holdings:
            holdings = b.get("holdings") or []
            if not holdings:
                row += ["", "", ""]
                table.add_row(*row)
                continue
            first = holdings[0]
            avail = first.get("availability") or ""
            style = _availability_style(avail)
            row += [
                first.get("location") or "",
                first.get("call_no") or "",
                f"[{style}]{avail}[/{style}]" if style else avail,
            ]
            table.add_row(*row)
            for extra in holdings[1:]:
                avail = extra.get("availability") or ""
                style = _availability_style(avail)
                table.add_row(
                    "", "", "", "",
                    extra.get("location") or "",
                    extra.get("call_no") or "",
                    f"[{style}]{avail}[/{style}]" if style else avail,
                )
        else:
            table.add_row(*row)
    console.print(table)


def _render_book_detail(console: Console, data: dict[str, Any]) -> None:
    ids = data.get("ids") or {}
    title = data.get("title") or ""
    console.print(Panel.fit(
        f"[bold]{title}[/bold]\n"
        f"bibid={ids.get('bibid') or '-'}   ncid={ids.get('ncid') or '-'}   "
        f"isbn={ids.get('isbn') or '-'}",
        border_style="cyan",
    ))

    pub = data.get("publication") or {}
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="bold")
    meta.add_column()
    if data.get("responsibility"):
        meta.add_row("責任表示", data["responsibility"])
    if pub.get("publisher"):
        loc = pub.get("place") or ""
        yr = pub.get("year") or ""
        meta.add_row("出版", f"{loc} : {pub['publisher']}  ({yr})")
    if data.get("language"):
        meta.add_row("言語", data["language"])
    if data.get("physical_description"):
        meta.add_row("形態", data["physical_description"])
    rda = data.get("rda_types") or {}
    if any(rda.values()):
        meta.add_row(
            "RDA",
            f"content={rda.get('content') or '-'}  media={rda.get('media') or '-'}  "
            f"carrier={rda.get('carrier') or '-'}",
        )
    console.print(meta)

    authors = data.get("authors") or []
    if authors:
        t = Table(title="著者", show_header=True, header_style="cyan")
        t.add_column("name")
        t.add_column("kana")
        t.add_column("role")
        t.add_column("auid")
        for a in authors:
            t.add_row(
                a.get("name") or "",
                a.get("kana") or "",
                a.get("role") or "",
                a.get("auid") or "",
            )
        console.print(t)

    subjects = data.get("subjects") or []
    classifications = data.get("classifications") or []
    if subjects or classifications:
        t = Table(show_header=True, header_style="cyan")
        t.add_column("scheme")
        t.add_column("value")
        for s in subjects:
            t.add_row(f"件名:{s.get('scheme', '')}", s.get("term", ""))
        for c in classifications:
            t.add_row(f"分類:{c.get('scheme', '')}", c.get("code", ""))
        console.print(t)

    children = data.get("children") or []
    if children:
        t = Table(title="子書誌", show_header=True, header_style="cyan")
        t.add_column("#", justify="right")
        t.add_column("bibid", style="yellow")
        t.add_column("title")
        t.add_column("publication")
        for c in children:
            t.add_row(
                str(c.get("number") or ""),
                c.get("bibid") or "",
                c.get("title") or "",
                c.get("publication") or "",
            )
        console.print(t)

    holdings = data.get("holdings") or []
    if holdings:
        _render_holdings_table(console, holdings, title="所蔵")

    sup = data.get("_supplementary")
    if sup:
        _render_supplementary(console, sup)

    sup2 = data.get("_supplementary_openbd")
    if sup2:
        _render_supplementary(console, sup2)


def _render_holdings_table(
    console: Console, holdings: list[dict[str, Any]], *, title: str = "Holdings"
) -> None:
    if not holdings:
        return
    is_cinii = any(h.get("institution") for h in holdings)
    t = Table(title=title, show_header=True, header_style="cyan")
    if is_cinii:
        t.add_column("institution")
        t.add_column("location")
        t.add_column("orderno")
        t.add_column("rgtn")
        for h in holdings:
            t.add_row(
                h.get("institution") or "",
                h.get("location") or "",
                h.get("cinii_orderno") or "",
                h.get("cinii_rgtn") or "",
            )
    else:
        t.add_column("location")
        t.add_column("call_no")
        t.add_column("barcode")
        t.add_column("blkey")
        t.add_column("availability")
        for h in holdings:
            avail = h.get("availability") or ""
            style = _availability_style(avail)
            t.add_row(
                h.get("location") or "",
                h.get("call_no") or "",
                h.get("barcode") or "",
                h.get("blkey") or "",
                f"[{style}]{avail}[/{style}]" if style else avail,
            )
    console.print(t)


def _render_supplementary(console: Console, sup: dict[str, Any]) -> None:
    if sup.get("empty"):
        return
    parts: list[str] = []
    src = sup.get("source") or ""
    if sup.get("synopsis"):
        parts.append(f"[bold]あらすじ[/bold]\n{sup['synopsis']}")
    toc = sup.get("toc") or []
    if toc:
        parts.append("[bold]目次[/bold]\n" + "\n".join(toc))
    if parts:
        console.print(Panel("\n\n".join(parts), title=f"補助情報 ({src})",
                            border_style="green"))


def _render_holdings_map(console: Console, data: dict[str, Any]) -> None:
    """data is {bibid: [Holding, ...]}."""
    for bibid, holdings in data.items():
        _render_holdings_table(console, holdings, title=f"{bibid}")


def _render_facet_map(console: Console, data: dict[str, Any]) -> None:
    for ft_name, info in data.items():
        values = (info or {}).get("values") or []
        t = Table(title=ft_name, show_header=True, header_style="cyan")
        t.add_column("count", justify="right")
        t.add_column("label")
        t.add_column("value", style="dim")
        for v in values:
            t.add_row(str(v.get("count", "")),
                      v.get("label", ""), v.get("value", ""))
        console.print(t)


def _render_book_list(console: Console, items: list[dict[str, Any]]) -> None:
    if not items:
        console.print("[dim](empty)[/dim]")
        return
    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("bibid", style="yellow")
    t.add_column("title")
    t.add_column("publication")
    for b in items:
        t.add_row(
            b.get("bibid") or b.get("ids", {}).get("ncid") or "",
            (b.get("title") or "").strip(),
            (b.get("publisher_line") or "").strip(),
        )
    console.print(t)


def _render_generic_list(console: Console, items: list[Any]) -> None:
    if not items:
        console.print("[dim](empty)[/dim]")
        return
    if all(isinstance(x, dict) for x in items):
        cols = list({k for item in items for k in item.keys()})
        t = Table(show_header=True, header_style="cyan")
        for c in cols:
            t.add_column(c)
        for item in items:
            t.add_row(*[_repr_cell(item.get(c)) for c in cols])
        console.print(t)
        return
    for item in items:
        console.print(item)


def _render_kv(console: Console, data: dict[str, Any]) -> None:
    t = Table(show_header=False)
    t.add_column(style="bold cyan")
    t.add_column()
    for k, v in data.items():
        t.add_row(k, _repr_cell(v))
    console.print(t)


def _repr_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


# ---- main entry ------------------------------------------------------------


def write(envelope: dict[str, Any], *, stream: TextIO | None = None,
          no_color: bool = False) -> None:
    """Write the envelope as a Rich-rendered table.

    Dispatches on ``envelope["type"]``.  Unknown types fall back to generic
    key/value or list rendering so the writer never crashes on a new shape.
    """
    out = stream or sys.stdout
    console = Console(file=out, no_color=no_color, force_terminal=out.isatty(),
                      highlight=False)
    t = envelope.get("type", "")
    data = envelope.get("data")
    if t == "SearchResult" and isinstance(data, dict):
        _render_search_result(console, data)
    elif t == "BookDetail" and isinstance(data, dict):
        _render_book_detail(console, data)
    elif t == "HoldingMap" and isinstance(data, dict):
        _render_holdings_map(console, data)
    elif t == "FacetMap" and isinstance(data, dict):
        _render_facet_map(console, data)
    elif t == "BookList" and isinstance(data, list):
        _render_book_list(console, data)
    elif t == "HoldingList" and isinstance(data, list):
        _render_holdings_table(console, data, title="Holdings")
    elif t == "SuggestionList" and isinstance(data, list):
        for item in data:
            console.print(item if isinstance(item, str) else _repr_cell(item))
    elif isinstance(data, list):
        _render_generic_list(console, data)
    elif isinstance(data, dict):
        _render_kv(console, data)
    else:
        console.print(data)
