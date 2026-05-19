"""CLI integration smoke tests — typer dispatch + envelope writing.

Mocks :class:`KulineClient` methods so no real HTTP traffic is made.  The goal
is to verify command-level glue (option parsing, envelope shape, exit codes),
not the parser layer which is exercised by the library's own audit suite.
"""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from kuopac.cli.main import app
from kuopac.enums import DataType, Scope, SupplementarySource
from kuopac.models import (
    BibIdentifiers,
    Book,
    BookDetail,
    Holding,
    Publication,
    SearchResult,
    Supplementary,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _fake_search_result(*, total: int = 1) -> SearchResult:
    book = Book(
        ids=BibIdentifiers(bibid="BB1", ncid="BD9", isbn="9784000000000"),
        title="Test book / Test Author",
        publisher_line="Tokyo : Test Pub , 2024",
        data_type=DataType.BOOK,
        detail_url="/opac/opac_details/?bibid=BB1",
        list_index=1, scope=Scope.LOCAL,
    )
    return SearchResult(
        books=[book] if total else [],
        total=total, opkey="B12345", scope=Scope.LOCAL,
        page_start=1, page_size=20, sort=6,
        query_summary="(test)",
        raw_url="https://kuline.example/?lang=0",
    )


def _fake_book_detail() -> BookDetail:
    return BookDetail(
        ids=BibIdentifiers(bibid="BB1", ncid="BD9", isbn="9784000000000"),
        title="Test / author", title_kana=None,
        title_main="Test", responsibility="author",
        data_type=DataType.BOOK,
        publication=Publication(raw="Tokyo : Test , 2024",
                                place="Tokyo", publisher="Test", year=2024),
        language="日本語",
    )


def test_version(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip().count(".") >= 2  # e.g. "0.1.0"


def test_schema_list(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--format", "json", "schema"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "TypeNameList"
    assert "Book" in payload["data"]


def test_schema_for_specific_type(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--format", "json", "schema", "Book"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "Schema"
    assert payload["data"]["title"] == "Book"


def test_search_json_envelope(monkeypatch, runner: CliRunner) -> None:
    def fake_search(self, query, **kwargs):
        return _fake_search_result()
    monkeypatch.setattr("kuopac.client.KulineClient.search", fake_search)
    result = runner.invoke(app, ["--format", "json", "search", "test"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "SearchResult"
    assert payload["data"]["total"] == 1
    assert payload["data"]["books"][0]["bibid"] == "BB1"


def test_search_ndjson_streams_books(monkeypatch, runner: CliRunner) -> None:
    def fake_search(self, query, **kwargs):
        return _fake_search_result()
    monkeypatch.setattr("kuopac.client.KulineClient.search", fake_search)
    result = runner.invoke(app, ["--format", "ndjson", "search", "t"])
    assert result.exit_code == 0
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["bibid"] == "BB1"


def test_search_limit_truncates_books(monkeypatch, runner: CliRunner) -> None:
    """``--limit N`` must cap the returned books even when KULINE returned more."""
    def fake_search(self, query, **kwargs):
        # Fabricate a 3-book page; --limit 2 should leave us with 2.
        from kuopac.models import SearchResult, Book, BibIdentifiers
        from kuopac.enums import DataType, Scope
        books = [
            Book(
                ids=BibIdentifiers(bibid=f"BB{i}"),
                title=f"book {i}", publisher_line="",
                data_type=DataType.BOOK, detail_url="",
                list_index=i, scope=Scope.LOCAL,
            )
            for i in range(1, 4)
        ]
        return SearchResult(
            books=books, total=3, opkey="B1", scope=Scope.LOCAL,
            page_start=1, page_size=20, sort=6,
            query_summary="", raw_url="",
        )
    monkeypatch.setattr("kuopac.client.KulineClient.search", fake_search)
    result = runner.invoke(
        app, ["--format", "json", "search", "x", "--limit", "2"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # total reflects KULINE's hit count, not the locally-trimmed list.
    assert payload["data"]["total"] == 3
    assert len(payload["data"]["books"]) == 2


def test_search_strict_no_hits_exits_1(monkeypatch, runner: CliRunner) -> None:
    def fake_search(self, query, **kwargs):
        return _fake_search_result(total=0)
    monkeypatch.setattr("kuopac.client.KulineClient.search", fake_search)
    result = runner.invoke(
        app, ["--format", "json", "--strict", "search", "x"]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["data"]["total"] == 0


def test_search_fields_projection_in_ndjson(monkeypatch, runner: CliRunner) -> None:
    def fake_search(self, query, **kwargs):
        return _fake_search_result()
    monkeypatch.setattr("kuopac.client.KulineClient.search", fake_search)
    result = runner.invoke(
        app, ["--format", "ndjson", "--fields", "bibid,title", "search", "t"]
    )
    assert result.exit_code == 0
    line = result.stdout.strip().splitlines()[0]
    record = json.loads(line)
    assert set(record.keys()) == {"bibid", "title"}


def test_detail_with_synopsis_merges_supplementary(
    monkeypatch, runner: CliRunner,
) -> None:
    def fake_detail(self, ident, *, scope=None):
        return _fake_book_detail()

    def fake_sup(self, target, *, source):
        return Supplementary(
            source=source, synopsis="ABSTRACT", toc=["c1", "c2"],
        )

    monkeypatch.setattr("kuopac.client.KulineClient.detail", fake_detail)
    monkeypatch.setattr(
        "kuopac.client.KulineClient.fetch_supplementary", fake_sup,
    )
    result = runner.invoke(
        app, ["--format", "json", "detail", "BB1", "--with", "synopsis"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "BookDetail"
    assert payload["data"]["_supplementary"]["synopsis"] == "ABSTRACT"


def test_holdings_returns_map(monkeypatch, runner: CliRunner) -> None:
    def fake_holdings(self, bibids):
        # Library normalises any iterable of identifiers; just return canned.
        return {
            "BB1": [Holding(location="loc", call_no="c1", barcode="b1")],
            "BB2": [Holding(location="loc", call_no="c2", barcode="b2")],
        }
    monkeypatch.setattr("kuopac.client.KulineClient.holdings", fake_holdings)
    result = runner.invoke(
        app, ["--format", "json", "holdings", "BB1", "BB2"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "HoldingMap"
    assert set(payload["data"].keys()) == {"BB1", "BB2"}


def test_suggest_returns_list(monkeypatch, runner: CliRunner) -> None:
    def fake_suggest(self, term):
        return ["abc", "abcd"]
    monkeypatch.setattr("kuopac.client.KulineClient.suggest", fake_suggest)
    result = runner.invoke(app, ["--format", "json", "suggest", "a"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "SuggestionList"
    assert payload["data"] == ["abc", "abcd"]


def test_suggest_limit_caps_results(monkeypatch, runner: CliRunner) -> None:
    """``suggest --limit`` is a subcommand-level flag (not global)."""
    def fake_suggest(self, term):
        return ["abc", "abcd", "abcde", "abcdef"]
    monkeypatch.setattr("kuopac.client.KulineClient.suggest", fake_suggest)
    result = runner.invoke(
        app, ["--format", "json", "suggest", "a", "--limit", "2"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data"] == ["abc", "abcd"]


def test_search_field_accepts_alias_and_wire_code(
    monkeypatch, runner: CliRunner,
) -> None:
    """``--field publisher=X`` and ``--field pubkey=X`` resolve to the same field."""
    from kuopac.enums import SearchField
    seen_conditions: list[list] = []

    def fake_search(self, query, **kwargs):
        conds = list(getattr(query, "conditions", []) or [])
        seen_conditions.append(conds)
        return _fake_search_result(total=0)

    monkeypatch.setattr("kuopac.client.KulineClient.search", fake_search)
    # friendly alias
    runner.invoke(app, ["--format", "json", "search", "x",
                        "--field", "publisher=丸善出版"])
    # wire code
    runner.invoke(app, ["--format", "json", "search", "x",
                        "--field", "pubkey=丸善出版"])
    assert len(seen_conditions) == 2
    fields_used = []
    for conds in seen_conditions:
        # condition objects expose .field; we just compare by enum identity.
        for c in conds:
            f = getattr(c, "field", None)
            if f is SearchField.PUBLISHER:
                fields_used.append(f)
                break
    assert len(fields_used) == 2  # both invocations resolved to PUBLISHER


def test_search_field_unknown_name_rejected(runner: CliRunner) -> None:
    result = runner.invoke(
        app, ["--format", "json", "search", "x", "--field", "nonexistent=X"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
    assert "nonexistent" in payload["error"]["message"]


def test_search_media_accepts_comma_and_repeat(
    monkeypatch, runner: CliRunner,
) -> None:
    """``--media`` accepts both ``a,b`` and repeated forms (parity with --with)."""
    seen_media: list[list] = []

    def fake_search(self, query, **kwargs):
        # The CLI builds a SearchQuery whose .media_codes captures the picks;
        # we just record the query and return an empty result.
        media = list(getattr(query, "media_types", []) or [])
        seen_media.append(media)
        return _fake_search_result(total=0)

    monkeypatch.setattr("kuopac.client.KulineClient.search", fake_search)
    # comma form
    runner.invoke(app, ["--format", "json", "search", "x",
                        "--media", "book,ebook"])
    # repeat form
    runner.invoke(app, ["--format", "json", "search", "x",
                        "--media", "book", "--media", "ebook"])
    assert len(seen_media) == 2
    assert seen_media[0] == seen_media[1]
    assert len(seen_media[0]) == 2


def test_misplaced_global_flag_gives_hint(runner: CliRunner) -> None:
    """``kuopac search --json`` should hint that --json belongs before the subcommand."""
    result = runner.invoke(app, ["search", "x", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["type"] == "Error"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
    assert "--json" in payload["error"]["message"]
    assert "global option" in payload["error"]["message"]
    assert "search" in payload["error"]["message"]


def test_misplaced_global_short_flag_gives_hint(runner: CliRunner) -> None:
    """The hint also fires for short forms like ``-q``."""
    result = runner.invoke(app, ["search", "x", "-q"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
    assert "-q" in payload["error"]["message"]


def test_genuinely_unknown_option_keeps_click_default(runner: CliRunner) -> None:
    """For typos that aren't global flags, click's normal error is preserved."""
    result = runner.invoke(app, ["search", "x", "--nonexistent"])
    assert result.exit_code != 0
    # No JSON envelope when click handles it; just verify it didn't crash with
    # the global-flag hint path.
    assert "global option" not in (result.stdout + result.stderr)


def test_unknown_with_token_is_rejected(runner: CliRunner) -> None:
    result = runner.invoke(
        app, ["--format", "json", "search", "x", "--with", "bogus"],
    )
    assert result.exit_code == 2  # INVALID_ARGUMENT
    payload = json.loads(result.stdout)
    assert payload["type"] == "Error"
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_manifest_includes_commands_and_types(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--format", "json", "manifest"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "Manifest"
    cmd_names = {c["name"] for c in payload["data"]["commands"]}
    assert {"search", "detail", "holdings", "suggest", "manifest"} <= cmd_names
    assert "Book" in payload["data"]["types"]


def test_manifest_includes_agent_patterns(runner: CliRunner) -> None:
    """Shell-pipe idioms intentionally not implemented as subcommands are
    documented as ``agent_patterns`` so an LLM agent can discover them."""
    result = runner.invoke(app, ["--format", "json", "manifest"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    patterns = payload["data"]["agent_patterns"]
    names = {p["name"] for p in patterns}
    assert {
        "did_you_mean_on_empty", "bulk_search", "search_then_detail",
        "local_then_cinii", "available_only_filter",
    } <= names
    # every pattern carries an executable snippet
    for p in patterns:
        assert p["snippet"].strip(), f"pattern {p['name']!r} has empty snippet"
        assert "kuopac" in p["snippet"]
