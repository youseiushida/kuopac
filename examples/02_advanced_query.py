"""Advanced search with the fluent SearchQuery builder."""
from kuopac import KulineClient, MediaType, SearchQuery, Sort


def main() -> None:
    q = (
        SearchQuery()
        .title("Python")
        .year_range(2020, 2024)
        .media(MediaType.BOOK)
        .sorted_by(Sort.YEAR_DESC)
        .per_page(20)
    )

    with KulineClient() as kuline:
        result = kuline.search(q)

        print(f"{result.total} hits for: {result.query_summary}")
        for book in result.books[:5]:
            print(f"  · {book.title[:60]}  ({book.publisher_line[:40]})")


if __name__ == "__main__":
    main()
