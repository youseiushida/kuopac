"""Iterate every search hit transparently across pages."""
from kuopac import KulineClient, SearchQuery


def main() -> None:
    q = SearchQuery().title("Python").per_page(50)

    with KulineClient() as kuline:
        result = kuline.search(q)

        # Option 1: iter_all() walks pages until exhausted (or until max_pages)
        seen = 0
        for book in result.iter_all(max_pages=3):
            seen += 1
            if seen <= 5 or seen % 50 == 0:
                print(f"  [{seen:3d}/{result.total}] {book.title[:50]}")

        print(f"\nVisited {seen} books across 3 pages (total {result.total})")

        # Option 2: explicit next_page() if you want to handle pages yourself
        page = result
        while page is not None and page.page_start < 200:
            page = page.next_page()
            if page:
                print(f"  next page starts at {page.page_start}, {len(page.books)} books")


if __name__ == "__main__":
    main()
