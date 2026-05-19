"""Drill down into a book: full bib + physical/online holdings."""
from kuopac import KulineClient


def main() -> None:
    with KulineClient() as kuline:
        # By bibid (e.g. from a previous search or a permalink)
        book = kuline.detail("BB08818020")

        print(f"Title:    {book.title}")
        if book.title_kana:
            print(f"Kana:     {book.title_kana}")
        print(f"Type:     {book.data_type.name}")
        print(f"Pub:      {book.publication}")
        print(f"Lang:     {book.language}")
        print(f"Phys:     {book.physical_description}")
        print(f"ISBN:     {book.ids.isbn}")
        print(f"NCID:     {book.ids.ncid}")
        print(f"Permalink: {book.external_links.permalink}")

        print("\nAuthors:")
        for a in book.authors:
            print(f"  · {a.name}  ({a.kana or '-'})  role={a.role or '-'}  auid={a.auid or '-'}")

        print("\nSubjects:")
        for s in book.subjects:
            print(f"  · {s.scheme}: {s.term}")

        print("\nClassifications:")
        for c in book.classifications:
            print(f"  · {c.scheme}: {c.code}")

        print("\nHoldings (from detail page):")
        for h in book.holdings:
            tag = "ONLINE" if h.is_online else "PHYSICAL"
            print(f"  [{tag}] {h.location or '-':<20} {h.call_no or '-':<25} "
                  f"barcode={h.barcode}  blkey={h.blkey}")

        # If you have many bibids you can batch-fetch live holdings:
        live = kuline.holdings([book])
        print(f"\nLive holdings via POST (first refresh triggers CSRF preflight):")
        for h in live[book.bibid or ""]:
            print(f"  {h.location}  {h.call_no}  {h.condition or '(available)'}")


if __name__ == "__main__":
    main()
