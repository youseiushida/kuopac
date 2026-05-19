"""Inspect facet aggregates and refine the search."""
from kuopac import FacetType, KulineClient


def main() -> None:
    with KulineClient() as kuline:
        result = kuline.search("機械学習")
        print(f"{result.total} hits before refinement")

        facets = kuline.facets(result, types=[FacetType.DATATYPE,
                                              FacetType.YEAR,
                                              FacetType.PUBLISHER])
        for ft, info in facets.items():
            print(f"\n— {ft.name} —")
            for v in info.top(5):
                print(f"  {v.label:<30s} ({v.count})")

        # Apply a facet — narrow to books (datatype=10) only
        narrowed = result.refine(datatype="10")
        print(f"\nNarrowed to books: {narrowed.total} hits "
              f"(was {result.total})")

        # Apply multiple facets at once
        narrowed2 = result.refine(datatype=["10", "19"], yearkey="2025")
        print(f"Books + Ebooks published 2025: {narrowed2.total} hits")


if __name__ == "__main__":
    main()
