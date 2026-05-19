"""Opt-in fetch of synopsis (あらすじ) and table of contents (目次).

`fetch_supplementary()` is one HTTP request per call.  The library never makes
this call automatically — opt in when you want the data.
"""
from kuopac import KulineClient, SupplementarySource


def main() -> None:
    with KulineClient() as kuline:
        # Pick a few books — only some will have supplementary content
        for bibid in ["BB08818020", "BB08815134"]:
            book = kuline.detail(bibid)
            print(f"\n=== {bibid}  {book.title[:50]} ===")

            # 1 request — BookPlus (the more useful source)
            sup = kuline.fetch_supplementary(book, source=SupplementarySource.BOOKPLUS)
            if sup:
                print(f"  [BookPlus] あらすじ:")
                print(f"    {sup.synopsis}")
                print(f"  [BookPlus] 目次 ({len(sup.toc)} chapters):")
                for line in sup.toc[:8]:
                    print(f"    · {line}")
                if len(sup.toc) > 8:
                    print(f"    · ... and {len(sup.toc) - 8} more")
            else:
                print("  [BookPlus] no data")

            # Optional fallback — only call this if BookPlus was empty
            if sup.empty:
                fallback = kuline.fetch_supplementary(book, source=SupplementarySource.OPENBD)
                if fallback:
                    print(f"  [openBD] synopsis: {fallback.synopsis}")
                else:
                    print("  [openBD] no data either")


if __name__ == "__main__":
    main()
