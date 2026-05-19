"""Simplest possible usage: keyword in, books out."""
from kuopac import KulineClient


def main() -> None:
    with KulineClient() as kuline:
        result = kuline.search("機械学習")

        print(f"Found {result.total} books for '機械学習'")
        print(f"Showing page 1 ({len(result.books)} of {result.total})")
        print()

        for book in result.books[:5]:
            print(f"  [{book.bibid}] {book.title[:60]}")
            print(f"           {book.publisher_line}")
            if book.ids.isbn:
                print(f"           ISBN: {book.ids.isbn}")
            print()


if __name__ == "__main__":
    main()
