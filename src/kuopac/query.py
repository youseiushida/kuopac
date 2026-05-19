"""
Fluent builder for KULINE advanced-search queries.

The builder validates and accumulates parameters; the client serialises them
to the wire format at request time. The point is that ``SearchQuery`` is the
single source of truth for what *a search means* — independent of how KULINE
chooses to encode it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from .enums import (
    BoolOp,
    CiniiSort,
    MediaType,
    Scope,
    SearchField,
    Sort,
)


@dataclass(slots=True)
class _Condition:
    field: SearchField
    keyword: str
    op: BoolOp = BoolOp.AND   # ignored for the first condition


@dataclass(slots=True)
class SearchQuery:
    """A composable advanced-search query.

    Two equivalent ways to build a query:

    * Method chaining::

        SearchQuery().title("機械学習").author("斎藤").year_range(2020, 2024)

    * Dataclass construction (for tests / serialization)::

        SearchQuery(conditions=[_Condition(SearchField.TITLE, "機械学習")], year_from=2020)
    """

    conditions: list[_Condition] = field(default_factory=list)
    scope: Scope = Scope.LOCAL
    media_types: list[MediaType] = field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    sort: Sort | CiniiSort = Sort.YEAR_DESC
    page_size: int = 20
    department: str = "all"   # dpmc_exp
    library_collection: str = ""  # lib_exp
    country_code: int | None = None
    text_language: int | None = None
    classification: int | None = None

    # ---- terse fluent helpers -------------------------------------------

    def add(self, field: SearchField, keyword: str, op: BoolOp = BoolOp.AND) -> Self:
        """Append one keyword condition (up to 3 supported by KULINE)."""
        if len(self.conditions) >= 3:
            raise ValueError("KULINE accepts at most 3 advanced-search conditions")
        self.conditions.append(_Condition(field, keyword, op))
        return self

    # Convenience shortcuts named after the most-used fields.

    def any(self, keyword: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.ANY, keyword, op)

    def title(self, keyword: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.TITLE, keyword, op)

    def title_exact(self, keyword: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.TITLE_EXACT, keyword, op)

    def author(self, keyword: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.AUTHOR, keyword, op)

    def publisher(self, keyword: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.PUBLISHER, keyword, op)

    def subject(self, keyword: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.SUBJECT, keyword, op)

    def isbn(self, code: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.ISBN, code, op)

    def issn(self, code: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.ISSN, code, op)

    def ncid(self, code: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.NCID, code, op)

    def bibid(self, code: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.BIB_ID, code, op)

    def call_no(self, code: str, op: BoolOp = BoolOp.AND) -> Self:
        return self.add(SearchField.CALL_NO, code, op)

    # ---- filters --------------------------------------------------------

    def media(self, *types: MediaType) -> Self:
        self.media_types.extend(types)
        return self

    def year_range(self, year_from: int | None = None, year_to: int | None = None) -> Self:
        self.year_from = year_from
        self.year_to = year_to
        return self

    def in_cinii(self) -> Self:
        """Switch this query to the other-universities (CiNii) scope."""
        self.scope = Scope.CINII
        if isinstance(self.sort, Sort):
            self.sort = CiniiSort.YEAR_DESC
        return self

    def in_local(self) -> Self:
        self.scope = Scope.LOCAL
        if isinstance(self.sort, CiniiSort):
            self.sort = Sort.YEAR_DESC
        return self

    def sorted_by(self, sort: Sort | CiniiSort) -> Self:
        self.sort = sort
        return self

    def per_page(self, n: int) -> Self:
        if n <= 0:
            raise ValueError("per_page must be > 0")
        self.page_size = n
        return self

    def in_department(self, code: str) -> Self:
        """Limit to a faculty/library (KULINE `dpmc_exp` value)."""
        self.department = code
        return self

    def in_collection(self, code: str) -> Self:
        """Limit to a named special collection (KULINE `lib_exp` value)."""
        self.library_collection = code
        return self
