"""Autocomplete + "did you mean" — useful for building a search UI."""
from kuopac import KulineClient


def main() -> None:
    with KulineClient() as kuline:
        # As-you-type suggestions
        for q in ["機械", "Python", "深層"]:
            suggestions = kuline.suggest(q)
            print(f"  '{q}' → {suggestions[:5]}")

        # Did-you-mean for a misspelled query
        result = kuline.search("Pithon")
        print(f"\nSearching 'Pithon' returned {result.total} hits")
        candidates = kuline.did_you_mean(result)
        if candidates:
            print(f"  Did you mean: {', '.join(candidates)}?")


if __name__ == "__main__":
    main()
