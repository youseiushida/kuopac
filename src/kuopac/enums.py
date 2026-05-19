"""
Type-safe enums for KULINE OPAC search parameters.

These map to the raw integer/string codes used by KULINE so callers can write
self-documenting code without memorizing magic numbers.
"""
from __future__ import annotations

from enum import Enum, IntEnum


class Scope(IntEnum):
    """Search scope (KULINE `cmode`)."""

    LOCAL = 0           # 自館 (KULINE)
    CINII = 5           # 他大学 (CiNii Books)


class Lang(IntEnum):
    """UI language (KULINE `lang`)."""

    JA = 0
    EN = 1


class Sort(IntEnum):
    """Sort order for local search results (KULINE `sort_exp` / `list_sort`)."""

    RELEVANCE = 0
    TITLE_ASC = 1
    TITLE_DESC = 2
    AUTHOR_ASC = 3
    AUTHOR_DESC = 4
    YEAR_ASC = 5
    YEAR_DESC = 6       # default in KULINE UI


class CiniiSort(IntEnum):
    """Sort order for CiNii (cmode=5) search results."""

    RELEVANCE = 1
    YEAR_ASC = 2        # 古い順
    YEAR_DESC = 3       # 新しい順
    HOLDINGS_ASC = 4    # 所蔵館 少ない順
    HOLDINGS_DESC = 5   # 所蔵館 多い順
    TITLE_ASC = 6       # あ→わ
    TITLE_DESC = 7      # わ→あ


class MediaType(IntEnum):
    """Media type filter (KULINE `file_exp`)."""

    BOOK = 1
    BOOK_JA = 2         # 和図書
    BOOK_EN = 3         # 洋図書
    SERIAL = 5          # 雑誌
    SERIAL_JA = 6       # 和雑誌
    SERIAL_EN = 7       # 洋雑誌
    EBOOK = 8           # 電子ブック
    EJOURNAL = 9        # 電子ジャーナル
    RARE_IMAGE = 91     # 貴重資料画像
    THESIS = 92         # 学位論文


class DataType(IntEnum):
    """Record data type returned in search results (`list_datatype`)."""

    BOOK = 10
    EBOOK = 19
    SERIAL = 20         # inferred
    UNKNOWN = 0

    @classmethod
    def parse(cls, raw: str | int | None) -> "DataType":
        """Best-effort conversion that never raises."""
        if raw is None or raw == "":
            return cls.UNKNOWN
        try:
            return cls(int(raw))
        except (ValueError, TypeError):
            return cls.UNKNOWN


class SearchField(str, Enum):
    """Field selectors for advanced search (KULINE `conN_exp`)."""

    ANY = "all"
    TITLE = "titlekey_ja"          # 書名(部分一致)
    TITLE_EXACT = "ftitlekey"      # 書名(完全形)
    PARENT_TITLE = "ptblkey"       # 親書誌名
    AUTHOR = "alkey"
    VOLUME = "volkey"
    PUBLISHER = "pubkey"
    SUBJECT = "shkey"
    ISBN = "isbn"
    ISSN = "issn"
    CALL_NO = "callno"
    BOOK_ID = "bookid"             # バーコード番号
    LEDGER_NO = "ledgerno"
    NCID = "ncid"                  # NACSIS-ID
    BIB_ID = "bibid"               # KULINE 書誌ID
    CLASS_TITLE = "clskey"
    CLASS_CODE = "cls"
    LCCN = "lccn"
    NDLCN = "ndlcn"
    CODEN = "coden"
    NBN = "nbn"                    # 全国書誌番号
    COMMON_ID = "cmnid"
    OTHER_CODE = "othn"


class BoolOp(str, Enum):
    """Boolean operator between advanced-search conditions."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class FacetType(str, Enum):
    """Facet aspects available after a search."""

    DATATYPE = "datatype"
    YEAR = "yearkey"
    PUBLISHER = "fpub"
    LANGUAGE = "txtl"
    SUBJECT = "fsh"
    CLASSIFICATION = "fcls"
    AUTHOR = "fauth"
    DEPARTMENT = "dptidpl"
    UNIVERSITY = "uclibcd"   # CiNii (cmode=5) のみ意味あり


class SupplementarySource(str, Enum):
    """Source database for supplementary book content (synopsis + TOC)."""

    BOOKPLUS = "bookplus"   # 日外アソシエーツ BookPlus (most common)
    OPENBD = "openbd"       # openBD (often empty for academic books)


# Page-size choices presented by KULINE UI. Server accepts any of these.
PAGE_SIZES = (20, 50, 100, 200, 500)
