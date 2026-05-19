"""Model properties — ``Holding.availability``, ``BibIdentifiers.primary_key``."""
from __future__ import annotations

import pytest

from kuopac.models import BibIdentifiers, BLStatusQuery, Holding


# ---------------------------------------------------------------------------
# Holding.availability — 4-branch truth table (condition > online > remote > shelf)
# ---------------------------------------------------------------------------

def test_availability_condition_takes_precedence_over_everything() -> None:
    h = Holding(
        condition="貸出中[2026.06.11返却期限]",
        online_url="https://x",
        institution="X大",
    )
    assert h.availability == "貸出中[2026.06.11返却期限]"


def test_availability_online_when_url_set() -> None:
    assert Holding(online_url="https://x").availability == "online"
    assert Holding(online_url="https://x", online_label="eBook").is_online


def test_availability_remote_when_institution_set() -> None:
    h = Holding(institution="神戸大学 附属図書館")
    assert h.availability == "remote"
    assert h.is_remote_university


def test_availability_default_is_on_shelf() -> None:
    """No condition + no online + no institution + no fetched status."""
    assert Holding(location="loc", call_no="c").availability == "available_on_shelf"


def test_availability_ignores_empty_string_condition() -> None:
    """Empty ``condition`` (vs. ``None``) shouldn't override defaults."""
    assert Holding(condition="").availability == "available_on_shelf"


# ---------------------------------------------------------------------------
# BibIdentifiers.primary_key()
# ---------------------------------------------------------------------------

def test_primary_key_prefers_bibid() -> None:
    ids = BibIdentifiers(bibid="BB1", ncid="BD2")
    assert ids.primary_key() == "BB1"


def test_primary_key_falls_back_to_ncid() -> None:
    ids = BibIdentifiers(ncid="BD2")
    assert ids.primary_key() == "BD2"


def test_primary_key_without_either_raises() -> None:
    with pytest.raises(ValueError):
        BibIdentifiers(isbn="9784000000000").primary_key()


# ---------------------------------------------------------------------------
# Misc model invariants
# ---------------------------------------------------------------------------

def test_holding_has_holdings_loaded_property() -> None:
    from kuopac.enums import DataType, Scope
    from kuopac.models import Book
    book = Book(
        ids=BibIdentifiers(bibid="BB1"),
        title="t", publisher_line="",
        data_type=DataType.BOOK, detail_url="",
        list_index=1, scope=Scope.LOCAL,
    )
    assert not book.has_holdings_loaded
    book.holdings = [Holding(location="loc")]
    assert book.has_holdings_loaded


def test_blstatus_query_defaults_match_kuline_convention() -> None:
    """Spec §11 — KULINE's blstat AJAX uses these defaults; if they drift the
    ``addmsg`` shows up as English and reservation flag changes meaning."""
    q = BLStatusQuery(blipkey="BL1")
    assert q.phasecd == "50"
    assert q.addmsg == "返却期限"
    assert q.hldstat == "1"
    assert q.lkcd == "1"
