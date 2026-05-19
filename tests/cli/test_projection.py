"""``--fields`` projection — dotted paths and ``[]`` traversal."""
from __future__ import annotations

from kuopac.cli.projection import parse_fields, project


def test_parse_simple_paths() -> None:
    assert parse_fields("a,b") == [["a"], ["b"]]


def test_parse_dot_path() -> None:
    assert parse_fields("ids.bibid") == [["ids", "bibid"]]


def test_parse_list_traversal() -> None:
    assert parse_fields("authors[].name") == [["authors", "[]", "name"]]


def test_parse_empty_returns_none() -> None:
    assert parse_fields("") is None
    assert parse_fields(None) is None


def test_project_simple() -> None:
    data = {"a": 1, "b": 2, "c": 3}
    paths = parse_fields("a,c")
    assert project(data, paths) == {"a": 1, "c": 3}


def test_project_nested() -> None:
    data = {"ids": {"bibid": "BB1", "ncid": None}}
    paths = parse_fields("ids.bibid")
    assert project(data, paths) == {"ids.bibid": "BB1"}


def test_project_list_traversal() -> None:
    data = {"authors": [{"name": "A"}, {"name": "B"}]}
    paths = parse_fields("authors[].name")
    assert project(data, paths) == {"authors[].name": ["A", "B"]}


def test_project_missing_key() -> None:
    data = {"a": 1}
    paths = parse_fields("missing.path")
    assert project(data, paths) == {"missing.path": None}


def test_project_applies_to_list_of_items() -> None:
    items = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    paths = parse_fields("a")
    assert project(items, paths) == [{"a": 1}, {"a": 3}]
