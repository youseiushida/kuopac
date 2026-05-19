"""``kuopac manifest`` — self-describing tool catalog for agents."""
from __future__ import annotations

import typer

from ... import __version__
from ..config import RunConfig
from ..formatters import single, write
from ..schema_gen import all_schemas

_MANIFEST_COMMANDS = [
    {
        "name": "search",
        "summary": "OPAC で書誌を検索 (簡易/詳細/他大学)",
        "arguments": [{"name": "keyword", "type": "string", "required": False}],
        "options": [
            {"name": "--title", "type": "string"},
            {"name": "--title-exact", "type": "string"},
            {"name": "--author", "type": "string"},
            {"name": "--publisher", "type": "string"},
            {"name": "--subject", "type": "string"},
            {"name": "--isbn", "type": "string"},
            {"name": "--issn", "type": "string"},
            {"name": "--ncid", "type": "string"},
            {"name": "--bibid", "type": "string"},
            {"name": "--call-no", "type": "string"},
            {"name": "--field", "type": "string", "repeatable": True},
            {"name": "--op", "type": "string", "default": "AND",
             "enum": ["AND", "OR", "NOT"]},
            {"name": "--scope", "type": "string", "default": "local",
             "enum": ["local", "cinii"]},
            {"name": "--media", "type": "string", "repeatable": True},
            {"name": "--year", "type": "string", "format": "YYYY-YYYY"},
            {"name": "--year-from", "type": "integer"},
            {"name": "--year-to", "type": "integer"},
            {"name": "--sort", "type": "string"},
            {"name": "--page-size", "type": "integer", "default": 20},
            {"name": "--start", "type": "integer", "default": 1},
            {"name": "--all", "type": "boolean"},
            {"name": "--max-pages", "type": "integer", "default": 5},
            {"name": "--refine", "type": "string", "repeatable": True},
            {"name": "--with", "type": "string", "enum": ["holdings"]},
        ],
        "output_type": "SearchResult",
        "request_count": "1 GET (+1 POST per page if --with holdings; "
                         "+1 GET if --refine; N GETs if --all)",
        "examples": [
            "kuopac search 機械学習",
            "kuopac search --title Python --year 2022-2024 --media book",
            "kuopac search Python --all --max-pages 3 --format ndjson",
        ],
    },
    {
        "name": "detail",
        "summary": "書誌詳細を取得",
        "arguments": [
            {"name": "identifier", "type": "string", "required": True,
             "description": "bibid または ncid"},
        ],
        "options": [
            {"name": "--scope", "type": "string", "default": "auto",
             "enum": ["auto", "local", "cinii"]},
            {"name": "--with", "type": "string", "repeatable": True,
             "enum": ["holdings", "synopsis", "bookplus",
                      "synopsis-openbd", "openbd", "live-status"]},
        ],
        "output_type": "BookDetail",
        "request_count": "1 GET (+1 POST for holdings, +1 GET per synopsis source, "
                         "+N GET for live-status)",
        "examples": [
            "kuopac detail BB08818020",
            "kuopac detail BB08818020 --with holdings,synopsis",
        ],
    },
    {
        "name": "holdings",
        "summary": "複数 bibid の所蔵情報を1POSTで取得",
        "arguments": [
            {"name": "bibids", "type": "list[string]",
             "description": "省略時は stdin から1行ずつ読む"},
        ],
        "options": [
            {"name": "--datatype", "type": "integer", "default": 10},
            {"name": "--with", "type": "string", "enum": ["live-status"]},
        ],
        "output_type": "HoldingMap",
        "request_count": "1 POST (+N GET if --with live-status)",
        "examples": ["kuopac holdings BB08818020 BB08823008"],
    },
    {
        "name": "status",
        "summary": "個別冊の貸出状況",
        "arguments": [{"name": "blkey", "type": "string", "required": True}],
        "options": [
            {"name": "--phasecd", "type": "string", "default": "50"},
            {"name": "--hldstat", "type": "string", "default": "1"},
            {"name": "--lkcd", "type": "string", "default": "1"},
            {"name": "--prlndflg", "type": "string", "default": "0"},
            {"name": "--blcd", "type": "string", "default": "1"},
            {"name": "--odrno", "type": "string"},
            {"name": "--bbcd", "type": "string", "default": "1"},
            {"name": "--contcd", "type": "string"},
            {"name": "--addmsg", "type": "string", "default": "返却期限"},
        ],
        "output_type": "LoanStatus",
        "request_count": "1 GET",
        "examples": ["kuopac status BL19200695"],
    },
    {
        "name": "suggest",
        "summary": "サジェスト候補",
        "arguments": [{"name": "term", "type": "string", "required": True}],
        "options": [],
        "output_type": "SuggestionList",
        "request_count": "1 GET",
        "examples": ["kuopac suggest 機械"],
    },
    {
        "name": "did-you-mean",
        "summary": "スペル候補",
        "arguments": [{"name": "opkey", "type": "string", "required": True}],
        "options": [],
        "output_type": "SuggestionList",
        "request_count": "1 GET",
    },
    {
        "name": "facets",
        "summary": "ファセット集計",
        "arguments": [{"name": "opkey", "type": "string", "required": True}],
        "options": [
            {"name": "--type", "type": "string", "repeatable": True},
            {"name": "--all-types", "type": "boolean"},
            {"name": "--top", "type": "integer"},
            {"name": "--scope", "type": "string", "default": "local"},
            {"name": "--page-size", "type": "integer", "default": 20},
            {"name": "--sort", "type": "integer", "default": 6},
        ],
        "output_type": "FacetMap",
        "request_count": "N GET (1 per --type)",
    },
    {
        "name": "synopsis",
        "summary": "あらすじ・目次",
        "arguments": [{"name": "identifier", "type": "string", "required": True,
                       "description": "ISBN または bibid"}],
        "options": [
            {"name": "--source", "type": "string", "default": "bookplus",
             "enum": ["bookplus", "openbd"]},
            {"name": "--isbn", "type": "string"},
        ],
        "output_type": "Supplementary",
        "request_count": "1 GET (+1 GET if only bibid given)",
    },
    {
        "name": "schema",
        "summary": "dataclass の JSON Schema",
        "arguments": [{"name": "type_name", "type": "string", "required": False}],
        "options": [],
        "output_type": "Schema | TypeNameList",
        "request_count": "0",
    },
    {
        "name": "manifest",
        "summary": "全コマンドの自己記述カタログ",
        "arguments": [],
        "options": [],
        "output_type": "Manifest",
        "request_count": "0",
    },
    {
        "name": "version",
        "summary": "バージョン表示",
        "arguments": [],
        "options": [],
        "output_type": "string",
        "request_count": "0",
    },
]

_GLOBAL_OPTIONS = [
    {"name": "--format", "type": "string",
     "enum": ["table", "json", "ndjson", "tsv", "yaml"],
     "default": "auto (TTY=table, pipe=json)"},
    {"name": "--json", "type": "boolean", "description": "--format=json"},
    {"name": "--fields", "type": "string", "repeatable": True,
     "description": "ドット記法フィールド射影"},
    {"name": "--limit", "type": "integer",
     "description": "表示件数上限 (search / suggest / did-you-mean に適用)"},
    {"name": "--quiet", "type": "boolean"},
    {"name": "--explain", "type": "boolean",
     "description": "リクエスト URL を stderr に出す"},
    {"name": "--explain-json", "type": "boolean",
     "description": "リクエスト情報を JSON の _meta に埋め込む"},
    {"name": "--no-color", "type": "boolean"},
    {"name": "--user-agent", "type": "string", "default": "kuopac/0.1"},
    {"name": "--rate-limit", "type": "number", "default": 0.0},
    {"name": "--timeout", "type": "number", "default": 30.0},
    {"name": "--strict", "type": "boolean"},
]


def register(app: typer.Typer) -> None:
    @app.command("manifest", help="全コマンドの自己記述カタログを出力")
    def manifest_cmd(ctx: typer.Context) -> None:
        cfg: RunConfig = ctx.obj
        payload = {
            "name": "kuopac",
            "version": __version__,
            "description": "京都大学 OPAC KULINE の蔵書検索CLI (匿名アクセス)",
            "global_options": _GLOBAL_OPTIONS,
            "commands": _MANIFEST_COMMANDS,
            "types": all_schemas(),
            "exit_codes": {
                "0": "成功",
                "1": "0件ヒット (--strict 時のみ)",
                "2": "引数エラー / バリデーション失敗",
                "3": "ネットワークエラー / タイムアウト",
                "4": "KULINE 仕様変更 / パース失敗",
                "5": "CSRF / 認証エラー",
                "130": "SIGINT",
            },
        }
        envelope = single("Manifest", payload, meta=cfg.meta())
        write(envelope, cfg)
