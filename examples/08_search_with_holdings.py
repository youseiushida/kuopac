"""Search → see each book's holdings (location/call_no/availability) in one POST.

Per-copy live status (貸出中 / 返却期限 …) is fetched **only on demand** via
`kuline.fetch_status(holding)` — each call is one extra GET.
"""
from kuopac import KulineClient, MediaType, SearchQuery


def main() -> None:
    with KulineClient() as kuline:
        q = (SearchQuery()
             .title("プログラミング")
             .media(MediaType.BOOK)
             .per_page(10))
        result = kuline.search(q)
        print(f"Found {result.total} hits — loading holdings for page 1...")

        # ONE POST for all 10 books on this page
        result.load_holdings()

        for book in result.books:
            print(f"\n[{book.bibid}] {book.title[:60]}")
            if not book.has_holdings_loaded:
                print("    (no holdings)")
                continue
            for h in book.holdings:
                # availability hint is free — no extra request
                if h.is_online:
                    print(f"    [ONLINE] {h.online_label or 'link'}: {h.online_url}")
                elif h.is_remote_university:
                    print(f"    [REMOTE] {h.institution}  call={h.cinii_orderno}")
                else:
                    print(f"    [SHELF ] {h.location:<25}  call={h.call_no:<18}  "
                          f"barcode={h.barcode}  -> {h.availability}")

        # OPTIONAL: fetch the actual live status of the very first physical copy
        # (one extra GET).  Most callers will skip this entirely.
        first_physical = next(
            (h for b in result.books for h in b.holdings
             if not h.is_online and h.status_query is not None),
            None,
        )
        if first_physical:
            print(f"\nLive status of {first_physical.blkey} (1 extra request):")
            status = kuline.fetch_status(first_physical)
            print(f"  → {status or '(available on shelf)'}")


if __name__ == "__main__":
    main()
