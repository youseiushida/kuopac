"""
HTML analysis utility for KULINE OPAC responses.

Operates on probe_data/<timestamp>_<label>/body.html files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from lxml import html as lxml_html


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "probe_data"


def load(dir_: Path) -> tuple[dict, bytes, Any]:
    meta = json.loads((dir_ / "meta.json").read_text(encoding="utf-8"))
    for f in dir_.iterdir():
        if f.name.startswith("body."):
            body = f.read_bytes()
            ext = f.suffix
            if ext == ".html":
                tree = lxml_html.fromstring(body.decode("utf-8", errors="replace"))
            else:
                tree = None
            return meta, body, tree
    raise FileNotFoundError(f"no body in {dir_}")


def cmd_list(_: argparse.Namespace) -> int:
    for d in sorted(DATA.iterdir()):
        if d.is_dir():
            print(d.name, end="")
            try:
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                sizes = [f.stat().st_size for f in d.iterdir() if f.name.startswith("body")]
                print(f"  status={meta['status']}  body_bytes={sizes[0] if sizes else 0}  url={meta['url'][:100]}")
            except Exception as e:
                print(f"  !! {e}")
    return 0


def _find_latest(label: str) -> Path | None:
    candidates = sorted([d for d in DATA.iterdir() if d.is_dir() and d.name.endswith(f"_{label}")])
    return candidates[-1] if candidates else None


def cmd_form(args: argparse.Namespace) -> int:
    """Dump all form inputs/selects from a saved HTML."""
    dir_ = _find_latest(args.label) if args.label else Path(args.path)
    if not dir_:
        print("not found", file=sys.stderr); return 1
    meta, body, tree = load(dir_)
    print(f"# {dir_.name}  ({meta['url']})\n")
    # inputs
    seen = set()
    print("## <input> fields")
    for inp in tree.xpath("//input"):
        name = inp.get("name")
        type_ = inp.get("type", "text")
        value = inp.get("value", "")
        key = (name, type_)
        if name and key not in seen:
            seen.add(key)
            print(f"  - name={name!r}  type={type_!r}  default={value!r}")
    print("\n## <select> fields")
    for sel in tree.xpath("//select"):
        name = sel.get("name")
        opts = sel.xpath(".//option")
        selected = [o.get("value") for o in opts if o.get("selected") is not None]
        print(f"  - name={name!r}  options={len(opts)}  selected={selected}")
        for o in opts[:50]:
            v = o.get("value")
            t = (o.text or "").strip()
            sel_mark = " *" if o.get("selected") is not None else ""
            print(f"      {v!r:30s} -> {t!r}{sel_mark}")
        if len(opts) > 50:
            print(f"      ...({len(opts) - 50} more)")
    return 0


def cmd_results(args: argparse.Namespace) -> int:
    """Extract search result records from a results page."""
    dir_ = _find_latest(args.label) if args.label else Path(args.path)
    meta, body, tree = load(dir_)
    print(f"# {dir_.name}  ({meta['url']})\n")
    # hit count
    hits = tree.xpath("//p[contains(@class,'search-results-hits_num')]//text()")
    print(f"hits text: {''.join(hits).strip()!r}")
    # current search key
    key = tree.xpath("//p[contains(@class,'current-search-key')]//text()")
    print(f"key text: {''.join(key).strip()!r}")
    # search results list
    items = tree.xpath("//ul[contains(@class,'result-list')]/li")
    print(f"items: {len(items)}")
    for idx, li in enumerate(items[:args.limit], 1):
        bibid = (li.xpath(".//input[@name='list_bibid']/@value") or [None])[0]
        datatype = (li.xpath(".//input[@name='list_datatype']/@value") or [None])[0]
        title_a = li.xpath(".//p[contains(@class,'result-book-title')]//a")
        title = title_a[0].text_content().strip() if title_a else None
        detail_href = title_a[0].get("href") if title_a else None
        publisher = "".join(li.xpath(".//p[contains(@class,'result-book-publisher')]//text()")).strip()
        booktype = "".join(li.xpath(".//p[contains(@class,'book-type')]//text()")).strip()
        print(f"\n  [{idx}] bibid={bibid} datatype={datatype}")
        print(f"      title: {title!r}")
        print(f"      pub:   {publisher!r}")
        print(f"      kind:  {booktype!r}")
        if detail_href:
            print(f"      detail: {detail_href[:120]}")
    # extract inline JS seed JSON for ISBN/NCID
    body_text = body.decode("utf-8", errors="replace")
    seeds = re.findall(r"img_out_link_list_all\([^,]+,\s*'(\[\[.*?\]\])'", body_text)
    if seeds:
        try:
            data = json.loads(seeds[0])
            print(f"\n  inline seed JSON: {len(data[0]) if data else 0} records")
            for rec in data[0][:args.limit]:
                print(f"    {rec}")
        except Exception as e:
            print(f"  seed parse err: {e}")
    return 0


def cmd_details(args: argparse.Namespace) -> int:
    """Extract detail-page biblio fields."""
    dir_ = _find_latest(args.label) if args.label else Path(args.path)
    meta, body, tree = load(dir_)
    print(f"# {dir_.name}  ({meta['url']})\n")
    title = tree.xpath("//h2[contains(@class,'book-title')]//span[contains(@class,'book-title-trd')]/text()")
    kana = tree.xpath("//h2[contains(@class,'book-title')]//span[contains(@class,'book-title-kana')]/text()")
    ptbl = tree.xpath("//span[@id='PTBL']//a/text()")
    print(f"title:    {''.join(title).strip()!r}")
    print(f"kana:     {''.join(kana).strip()!r}")
    print(f"parent (PTBL): {ptbl}")
    print()
    print("## bibliographic fields")
    rows = tree.xpath("//table[contains(@class,'book-detail-table')]//tr")
    for tr in rows:
        ths = tr.xpath("./th")
        tds = tr.xpath("./td")
        if not ths or not tds:
            continue
        code = ths[0].get("class") or ""
        label = ths[0].text_content().strip()
        td_text = re.sub(r"\s+", " ", tds[0].text_content()).strip()
        print(f"  [{code}] {label}: {td_text[:300]}")
    print()
    print("## holdings (library-info-table2)")
    hold_rows = tree.xpath("//table[contains(@class,'library-info-table2')]//tr[contains(@class,'library-info-data')]")
    print(f"  rows: {len(hold_rows)}")
    for r in hold_rows[:args.limit]:
        cells = r.xpath("./td")
        for c in cells:
            ccls = c.get("class") or ""
            txt = re.sub(r"\s+", " ", c.text_content()).strip()
            if txt:
                print(f"    [{ccls}] {txt[:120]}")
        # blkey
        bk = r.xpath(".//a[contains(@href, 'blkey=')]/@href")
        if bk:
            m = re.search(r"blkey=([^&]+)", bk[0])
            if m:
                print(f"    blkey={m.group(1)}")
        print()
    return 0


COMMANDS = {
    "list": cmd_list,
    "form": cmd_form,
    "results": cmd_results,
    "details": cmd_details,
}


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    pf = sub.add_parser("form")
    pf.add_argument("--label", default=None)
    pf.add_argument("--path", default=None)
    pr = sub.add_parser("results")
    pr.add_argument("--label", default=None)
    pr.add_argument("--path", default=None)
    pr.add_argument("--limit", type=int, default=10)
    pd = sub.add_parser("details")
    pd.add_argument("--label", default=None)
    pd.add_argument("--path", default=None)
    pd.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    return COMMANDS[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
