"""
kuopac — Type-safe Python client for the Kyoto University KULINE OPAC.

Quickstart::

    from kuopac import KulineClient, SearchQuery, MediaType

    with KulineClient() as kuline:
        # Simple keyword search
        result = kuline.search("機械学習")
        print(f"{result.total} hits")
        for book in result.books[:5]:
            print(book.title, book.bibid)

        # Advanced search
        q = (SearchQuery()
             .title("Python")
             .author("斎藤")
             .year_range(2020, 2024)
             .media(MediaType.BOOK))
        result = kuline.search(q)

        # Full detail + holdings
        book = kuline.detail(result.books[0])
        for copy in book.holdings:
            print(copy.location, copy.call_no, copy.condition)
"""
from .client import KulineClient
from .enums import (
    BoolOp,
    CiniiSort,
    DataType,
    FacetType,
    Lang,
    MediaType,
    Scope,
    SearchField,
    Sort,
    SupplementarySource,
)
from .errors import (
    CSRFError,
    ForbiddenError,
    KulineError,
    NotFoundError,
    ParseError,
)
from .models import (
    AuthorHeading,
    BibIdentifiers,
    BLStatusQuery,
    Book,
    BookDetail,
    ChildBib,
    Classification,
    ExternalLinks,
    FacetInfo,
    FacetValue,
    Holding,
    ParentSeries,
    Publication,
    RdaTypes,
    SearchResult,
    SpellCorrection,
    Subject,
    Suggestion,
    Supplementary,
)
from .query import SearchQuery

__all__ = [
    # Client
    "KulineClient",
    # Query builder
    "SearchQuery",
    # Enums
    "BoolOp", "CiniiSort", "DataType", "FacetType", "Lang",
    "MediaType", "Scope", "SearchField", "Sort", "SupplementarySource",
    # Models
    "AuthorHeading", "BibIdentifiers", "BLStatusQuery",
    "Book", "BookDetail", "ChildBib",
    "Classification", "ExternalLinks", "FacetInfo", "FacetValue",
    "Holding", "ParentSeries", "Publication", "RdaTypes",
    "SearchResult", "SpellCorrection", "Subject", "Suggestion",
    "Supplementary",
    # Errors
    "CSRFError", "ForbiddenError", "KulineError", "NotFoundError", "ParseError",
]
try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version
    __version__ = _pkg_version("kuopac")
except PackageNotFoundError:  # source checkout without install metadata
    __version__ = "0.0.0+unknown"
del PackageNotFoundError, _pkg_version  # type: ignore[name-defined]
