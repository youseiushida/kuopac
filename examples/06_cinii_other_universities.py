"""Search the consortium catalogue (CiNii Books) instead of KULINE local."""
from kuopac import KulineClient, Scope, SearchQuery


def main() -> None:
    with KulineClient() as kuline:
        # Style A: bare keyword + scope=
        result = kuline.search("機械学習", scope=Scope.CINII)
        print(f"CiNii has {result.total} hits for '機械学習'")
        for book in result.books[:3]:
            print(f"  · [{book.ncid}] {book.title[:60]}")

        # Style B: query builder
        q = (SearchQuery().title("深層学習").in_cinii())
        result2 = kuline.search(q)
        print(f"\nCiNii '深層学習' (title only): {result2.total} hits")

        # Drill down — CiNii detail uses ncid as the primary key
        if result.books:
            book = kuline.detail(result.books[0])  # passes the Book; client picks ncid
            print(f"\nFull detail for {book.ids.ncid}:")
            print(f"  {book.title}")
            print(f"  authors: {[a.name for a in book.authors]}")


if __name__ == "__main__":
    main()
