# kuopac CLI 設計仕様書

このドキュメントは `kuopac` パッケージに **`kuopac` という名前の CLI ツール** を追加する
ための設計仕様。エージェントへの引き継ぎ用に、判断材料・実装方針・コマンド仕様・
スキーマ・受け入れ基準まで余さず記述する。

> **コンテキスト**: パッケージ `kuopac` (v0.1.0) は京大OPAC「KULINE」を叩く
> 型付き Python ライブラリとして完成済 (`src/kuopac/`)。`KulineClient` クラスが
> 検索/詳細/所蔵/サジェスト等を提供。詳細は `README.md` および
> `docs/opac-spec.md` 参照。

---

## 0. 引き継ぎ前提

### 完了している前提
- [x] ライブラリ本体: 検索・詳細・所蔵・サジェスト・あらすじ/目次・他大学検索
- [x] dataclass モデル群が安定 (`Book`, `BookDetail`, `Holding`, `SearchResult` 等)
- [x] `pyproject.toml` で `kuopac` パッケージとして登録済
- [x] `examples/01_..09_*.py` 動作確認済
- [x] HTML 抽出網羅性監査済 (`docs/audit-report.md`)

### この設計で実装する
- [ ] `src/kuopac/cli/` 配下に CLI 実装
- [ ] `pyproject.toml` の `[project.scripts]` に `kuopac = "kuopac.cli.main:main"` を追加
- [ ] エージェント親和な JSON / NDJSON 出力
- [ ] スキーマ自己記述 (`kuopac schema`, `kuopac manifest`)

### この設計で扱わない (将来作業)
- MyOPAC ログイン機能 (予約・ILL申込・購入申込)
- async 版
- TUI / curses UI
- 書影画像のフェッチ

---

## 1. 設計原則

### 原則A: 1 コマンド呼び出し = 1 HTTPリクエスト (デフォルト)
ライブラリの不変条件 ("1 method = 1 request") を CLI でも維持する。
追加リクエストはユーザーが `--with` フラグで明示的にオプトインしたときだけ。

| CLI 呼び出し | デフォルト通信 |
|------------|--------------|
| `kuopac search X` | 1 GET |
| `kuopac detail BB...` | 1 GET |
| `kuopac detail BB... --with holdings` | 1 GET + 1 POST = 2 req |
| `kuopac detail BB... --with holdings,synopsis` | 1 GET + 1 POST + 1 GET = 3 req |
| `kuopac search X --all` | (total/page_size) GET (順次ページング) |

`--explain` で実発射 URL を可視化、`--dry-run` で送らずに URL だけ表示。

### 原則B: TTY と非TTY で出力を自動切替
- 標準出力が **TTY** → デフォルト `--format=table` (色つき、整形)
- 標準出力が **パイプ/リダイレクト** → デフォルト `--format=json`
- ユーザは `--format=...` で常に上書き可

### 原則C: エージェント向けは「機械可読 + 自己記述」
- 全コマンドが `--format=json` で安定スキーマを返す
- `kuopac schema <TypeName>` で各 dataclass の JSON Schema を吐く
- `kuopac manifest` で全コマンドの (引数 + 戻り値スキーマ) を1ファイルで吐く
  → エージェントは tool catalog としてそのまま取り込める

### 原則D: stderr / stdout の役割分離
- **stdout**: 構造化データ (JSON / NDJSON / 表) **のみ**
- **stderr**: 進捗・警告・`--explain` の URL ログ・エラーメッセージ
- 終了コードで成否判定 (詳細は §7)

---

## 2. コマンド構造一覧

Git 風ネストサブコマンド。ライブラリのメソッドとほぼ 1:1 マッピング。

```
kuopac search <keyword>                                     # 簡易検索
kuopac search --title X --author Y --year 2020-2024 ...    # 詳細検索 (フラグだらけ)
kuopac search --scope cinii <keyword>                       # CiNii (他大学)
kuopac search ... --all                                     # 全ページ走査 (NDJSON 推奨)
kuopac search ... --refine datatype=10,publisher=丸善出版    # 検索後ファセット適用

kuopac detail <bibid|ncid>                                  # 自動判別
kuopac detail <id> --scope cinii                            # 明示
kuopac detail <id> --with holdings                          # +1 POST
kuopac detail <id> --with synopsis                          # +1 GET (BookPlus)
kuopac detail <id> --with synopsis-openbd                   # +1 GET (openBD)
kuopac detail <id> --with holdings,synopsis                 # 計3 req

kuopac holdings <bibid> [<bibid> ...]                       # 1 POST バッチ
kuopac status <blkey> [--phasecd 50] [--blcd 1] ...         # 1 GET 個別冊状態

kuopac suggest <term>                                       # サジェスト
kuopac did-you-mean <opkey>                                 # スペル候補

kuopac facets <opkey> [--type datatype,publisher,year]      # 1ファセット種別=1req
kuopac facets <opkey> --all-types                           # 9種類並列 (意図的 fan-out)

kuopac synopsis <bibid> [--source bookplus|openbd]          # あらすじ/目次

# エージェント向け
kuopac schema [<TypeName>]                                  # JSON Schema 出力
kuopac manifest                                             # 全コマンドのカタログ

# 補助
kuopac version                                              # --version でも可
kuopac --help / kuopac <cmd> --help
```

### 2.1 共通グローバルフラグ

すべてのコマンドで受け付ける:

| フラグ | デフォルト | 説明 |
|--------|-----------|------|
| `--format {table,json,ndjson,tsv,yaml}` | TTY 自動判定 | 出力形式 |
| `--json` | – | `--format=json` のエイリアス |
| `--fields a,b,c.d` | 全フィールド | ドット記法でのフィールド射影 |
| `--limit N` | コマンドにより異なる | 表示件数上限 (検索結果など) |
| `--quiet` | off | stderr 進捗を抑制 |
| `--explain` | off | リクエスト URL を stderr に出す |
| `--dry-run` | off | リクエストを発射せず URL だけ表示 |
| `--no-color` | TTY なら色付き | 色を無効化 |
| `--user-agent UA` | "kuopac/0.1" | UA 上書き |
| `--lang {ja,en}` | ja | UI 言語 (`lang=0|1`) |
| `--rate-limit SECONDS` | 0 | 連続リクエスト間の最小間隔 |
| `--timeout SECONDS` | 30 | HTTP タイムアウト |
| `--strict` | off | 0件ヒットを exit 1 にする |
| `--explain-json` | off | `--explain` 内容を JSON 出力に `_meta.requests[]` として埋める |

---

## 3. 出力フォーマット仕様

### 3.1 `--format=table` (人間向け)
- TTY 幅に応じてカラム自動調整
- 色付け: 状態文字列 (貸出中=赤, 在架=緑, オンライン=青 など)
- 検索結果ヘッダ行に該当件数を表示
- ロケーション/請求記号は等幅で揃える

例:
```
1751 件ヒット   検索条件: (書名: Python) (資料区分: 図書)
─────────────────────────────────────────────────────────
#   bibid       title                              location           call_no             status
1   BB08818184  Pythonで始めるスワーム制御プログラ… 情報学/図書室      548.3||TSU 78||1   ●在架
2   BB08823008  Unityによる3DCGプログラミング…       情報学/図書室      007.6||ISH 76||1   ✗貸出中 2026-06-11返却
3   …
```

### 3.2 `--format=json` (1JSON)

```json
{
  "type": "SearchResult",
  "schema_version": "1",
  "data": {
    "query_summary": "(書名: Python) (資料区分: 図書)",
    "scope": "LOCAL",
    "total": 1751,
    "page_start": 1,
    "page_size": 20,
    "sort": 6,
    "opkey": "B17791...",
    "books": [
      {
        "bibid": "BB08818184",
        "ids": {"bibid": "BB08818184", "ncid": "BD...", "isbn": "...", "nbn": "..."},
        "title": "...",
        "data_type": "BOOK",
        "publisher_line": "...",
        "detail_url": "/opac/opac_details/?...",
        "list_index": 1,
        "scope": "LOCAL",
        "holdings": []
      }
    ]
  },
  "_meta": {
    "requests": [
      {"url": "https://kuline.kulib.kyoto-u.ac.jp/opac/opac_search/?...",
       "method": "GET", "status": 200, "elapsed_ms": 432}
    ]
  }
}
```

ルール:
- ルートは常に `{type, schema_version, data, _meta?}` 形式
- `type` は dataclass 名 + `"List"` (例: `BookList`, `HoldingList`)
- 列挙体は `"name"` 文字列 (`"BOOK"`, `"LOCAL"`)。`schema` コマンドで定義可。
- 日時は ISO8601。
- null は欠落でなく明示。
- `_meta` は `--explain-json` 時のみ。

### 3.3 `--format=ndjson` (ストリーミング)

リスト系の各要素を1行1JSON。エージェントが逐次処理可能。

```
{"bibid":"BB08818184","title":"Python...","location":"情報学/図書室","status":"available_on_shelf"}
{"bibid":"BB08823008","title":"Unity...","location":"情報学/図書室","status":"貸出中[2026.06.11返却期限]"}
```

`--all` でページ送り中も逐次出力されるべき。

### 3.4 `--format=tsv` (シェル混合)

ヘッダ行付きタブ区切り。`awk` / `cut` 用。

```
bibid	title	location	call_no	status
BB08818184	Python...	情報学/図書室	548.3||TSU 78||1	available
```

`--fields` 必須。デフォルトカラムはコマンドごとに定義 (§5)。

### 3.5 `--format=yaml`

`json` を YAML に変換 (依存追加: `pyyaml`)。人間が読む長い結果向け。

---

## 4. オプトイン制御 (`--with`)

`detail` コマンドで追加情報を取りに行く。複数指定はカンマ区切り。

| `--with` 値 | 追加通信 | 統合先 |
|------------|---------|--------|
| `holdings` | 1 POST `/opac/opac_search_localhold/` | `BookDetail.holdings` (上書き) |
| `synopsis` / `bookplus` | 1 GET `/opac/opac_bookplusinfo/` | `BookDetail._supplementary` |
| `synopsis-openbd` / `openbd` | 1 GET `/opac/opac_openbdinfo/` | `BookDetail._supplementary_openbd` |
| `live-status` | N GET (各 Holding の `opac_blstat/`) | `Holding.condition` (各) |

`--with live-status` は明示的に N+1 ファンアウトを引き起こすので、警告を stderr に
出してから実行する (`> warning: this will issue 1 + N requests where N=...`)。

`search` コマンドにも `--with holdings` を使えるようにする (= `result.load_holdings()`)。

---

## 5. コマンド別仕様

### 5.1 `kuopac search`

```
kuopac search [<keyword>] [OPTIONS]
```

**引数**:
- 位置引数 `<keyword>` (任意): 簡易検索ワード。詳細検索フラグと併用なら無視せず `kywd` 扱い。

**フラグ** (詳細検索):
| フラグ | con*_exp に対応 |
|--------|----------------|
| `--title X` | titlekey_ja |
| `--title-exact X` | ftitlekey |
| `--author X` | alkey |
| `--publisher X` | pubkey |
| `--subject X` | shkey |
| `--isbn X` | isbn |
| `--issn X` | issn |
| `--ncid X` | ncid |
| `--bibid X` | bibid |
| `--call-no X` | callno |
| `--field <name>=<value>` (繰り返し) | 任意フィールド |

複数条件は `--op AND|OR|NOT` で連結。デフォルト AND。
最大3条件 (KULINE 制約)。

**絞り込みフラグ**:
| フラグ | 値 | 説明 |
|--------|----|------|
| `--scope {local,cinii}` | local | コレクション |
| `--media {book,book-ja,book-en,serial,serial-ja,serial-en,ebook,ejournal,rare-image,thesis}` (繰り返し) | – | 媒体種別 |
| `--year FROM-TO` または `--year-from N --year-to N` | – | 出版年 |
| `--country CODE` | – | 出版国 |
| `--language CODE` | – | 本文言語 |
| `--classification CODE` | – | 分類 |
| `--department CODE` | all | 部局 |
| `--collection CODE` | "" | 特殊コレクション |

**ソート/件数**:
| フラグ | デフォルト |
|--------|----------|
| `--sort {relevance,title-asc,title-desc,author-asc,author-desc,year-asc,year-desc}` | year-desc |
| `--page-size N` (20/50/100/200/500) | 20 |
| `--start N` | 1 |
| `--all` | off — 全ページ |
| `--max-pages N` | 5 (--all 時) — 暴走防止 |

**統合フラグ**:
- `--with holdings` → 各 Book に所蔵を入れる (1 POST/ページ)
- `--refine datatype=10,fpub=丸善出版` → 検索後 `amode=23` で絞り込み (1 GET 追加)

**出力**: `SearchResult` (JSON) または 表 (table)。

**例**:
```bash
# 簡易
kuopac search "機械学習"

# 多条件
kuopac search --title Python --year 2022-2024 --media book --sort year-desc

# ファセット適用
kuopac search "機械学習" --refine datatype=10

# 全ページストリーム
kuopac search Python --all --max-pages 10 --format ndjson

# CiNii
kuopac search "深層学習" --scope cinii

# 検索結果に所蔵をマージ
kuopac search Python --limit 10 --with holdings --format json
```

### 5.2 `kuopac detail`

```
kuopac detail <id> [OPTIONS]
```

**引数**: `<id>` = bibid (BB/EB/...で始まる) または ncid (BA/BB/BC/BD/BN/...)
`--scope` で曖昧性解消。デフォルトは "BB"/"EB" 始まりは local、"BD"/"BA"/"BC"/"BN" 始まりは cinii の自動判別 (heuristic; 上書き可)。

**フラグ**:
- `--scope {local,cinii,auto}` (デフォルト auto)
- `--with holdings,synopsis,synopsis-openbd,live-status` (繰り返し可)

**出力**: `BookDetail` (拡張)

### 5.3 `kuopac holdings`

```
kuopac holdings <bibid> [<bibid> ...] [OPTIONS]
```

複数 bibid をまとめて1 POST で取得。

**フラグ**:
- `--datatype CODE` (デフォルト 10) — 一括指定。bibid ごとに違うなら 1冊ずつ呼ぶ
- `--with live-status` — 各冊に opac_blstat (注意: N requests)

**出力**: `{bibid: [Holding, ...]}` のマッピング (JSON) または 表

### 5.4 `kuopac status`

```
kuopac status <blkey> [OPTIONS]
```

単一冊の貸出状態。`detail`/`holdings` で取れた `Holding.status_query` を使う想定。

**フラグ**:
- `--phasecd 50` `--hldstat 1` `--lkcd 1` `--prlndflg 0` `--blcd 1` `--bbcd 1`
- `--addmsg "返却期限"`
- これら全部 status_query から渡せるが、上書きフラグも提供

**出力**: `{"blkey": "...", "condition": "貸出中[...]"}` または "available_on_shelf" 文字列

### 5.5 `kuopac suggest`

```
kuopac suggest <term>
```
出力: 候補文字列のリスト。`--format=json` だと `{"suggestions": [...]}`。

### 5.6 `kuopac did-you-mean`

```
kuopac did-you-mean <opkey>
```
直前検索の `opkey` を渡してスペル候補を取得。
あるいは `kuopac search X --did-you-mean` 風にショートカット提供してもいい。

### 5.7 `kuopac facets`

```
kuopac facets <opkey> [--type T1,T2,...] [--all-types]
```

**フラグ**:
- `--type` (デフォルト `datatype,yearkey,fpub,fsh`)
- `--all-types` → 9 種類全部叩く (= 9 GET; 意図的 fan-out 明示)
- `--top N` → 各種類で上位 N バケットだけ表示

**出力**: `{FacetType: FacetInfo}` (JSON) または facet ごとに表

### 5.8 `kuopac synopsis`

```
kuopac synopsis <bibid> [--source bookplus|openbd] [--isbn ISBN]
```

ISBN ベースのエンドポイントだが、bibid から detail 経由でも取れる。

**実装方針**:
- ISBN が引数で直接渡されたら 1 GET
- bibid のみ渡されたら、最初に detail を取って ISBN を得る (= 2 GET になる) → **`--isbn` 指定推奨を help に明記**

**出力**: `Supplementary`

### 5.9 `kuopac schema [<TypeName>]`

引数なし: 全公開 dataclass / Enum 名のリスト。
引数あり: その型の JSON Schema を出力。

**実装**: `dataclasses.fields()` をたどって型情報を JSON Schema に変換。
ライブラリは `dataclass-json` などを使わずに済むよう、シンプルな自作で十分。
あるいは `pydantic` を依存に入れて dataclass → pydantic 変換 → schema 生成のほうが堅い。

### 5.10 `kuopac manifest`

全コマンドのカタログを1JSONで出力。Claude Desktop の `tools` config や
任意のエージェントが直接読める形:

```json
{
  "name": "kuopac",
  "version": "0.1.0",
  "description": "京都大学OPAC KULINE の蔵書検索CLI (匿名アクセス)",
  "commands": [
    {
      "name": "search",
      "summary": "OPACで書誌を検索",
      "arguments": [
        {"name": "keyword", "type": "string", "required": false}
      ],
      "options": [
        {"name": "--title", "type": "string"},
        ...
      ],
      "output_type": "SearchResult",
      "request_count": 1,
      "examples": ["kuopac search 機械学習"]
    },
    ...
  ],
  "types": {
    "SearchResult": {"$ref": "schema://SearchResult"},
    "Book": {...},
    ...
  }
}
```

---

## 6. JSON 出力スキーマ規約

### 6.1 dataclass のシリアライズ
- `slots=True` の dataclass を再帰的に dict 化
- `field(default_factory=...)` で空リスト/dictは `[]` / `{}` として明示
- IntEnum/Enum は **値ではなく名前** で出す: `DataType.BOOK` → `"BOOK"`
- 内部用 `_client` 等の private フィールドは省く
- `None` も明示出力 (欠落させない)

### 6.2 envelope
すべての出力は次のいずれか:

```json
// 単一オブジェクト
{
  "type": "BookDetail",
  "schema_version": "1",
  "data": { ... }
}

// リスト
{
  "type": "BookList",
  "schema_version": "1",
  "data": [ {...}, {...} ],
  "count": N,
  "total": NN   // 検索結果なら全件、それ以外 omit
}
```

ndjson モードはこのenvelopeを使わず、各 `data` 要素を1行ずつ出す。

### 6.3 エラーレスポンス (JSON モード)
```json
{
  "type": "Error",
  "schema_version": "1",
  "error": {
    "code": "PARSE_ERROR",
    "message": "could not find <span class=book-title-trd>",
    "request_url": "https://...",
    "http_status": 200
  }
}
```

エラーコード一覧:
- `INVALID_ARGUMENT`
- `NOT_FOUND` (bibid/ncid 不正)
- `FORBIDDEN` (KULINE が 403、通常起こらない)
- `NETWORK` (タイムアウト・接続失敗)
- `PARSE_ERROR` (KULINE 仕様変更疑い)
- `CSRF_ERROR` (POST 系)
- `RATE_LIMITED` (KULINE 側、現状未確認)

### 6.4 フィールド射影 (`--fields`)

ドット記法 + カンマ区切り。リスト要素は `[]` 表記。

```bash
kuopac search X --fields bibid,title,ids.isbn
kuopac detail BB... --fields title,authors[].name,authors[].auid,holdings[].location
```

実装: `jq` ライクなパスエクスプレッション。最小限なら自作可、本気でやるなら `jmespath` 採用 (依存追加)。

---

## 7. 終了コード規約

| code | 意味 |
|------|------|
| 0 | 成功 (1件以上 or 操作完了) |
| 1 | 成功だが 0 件ヒット (`--strict` 指定時のみ非ゼロ; デフォルトは 0) |
| 2 | 引数エラー / バリデーション失敗 |
| 3 | ネットワークエラー / タイムアウト |
| 4 | KULINE 仕様変更/パース失敗 |
| 5 | CSRF/認証エラー |
| 130 | SIGINT (Ctrl-C) |

---

## 8. 依存ライブラリ

### 8.1 必須追加 (`dependencies`)

| パッケージ | 用途 | 備考 |
|----------|------|------|
| `typer` >= 0.12 | CLI フレームワーク | 型ヒント→CLI 変換が綺麗。`--help` 自動生成。manifest 化しやすい |
| `rich` >= 13 | 表/色付け/プログレス | typer と相性◎。`--format=table` の品質を上げる |

### 8.2 任意追加 (`[project.optional-dependencies] cli`)

| パッケージ | 用途 |
|----------|------|
| `pyyaml` | `--format=yaml` |
| `jmespath` | `--fields` の高度な射影 (`books[?data_type=='BOOK'].bibid` など) |
| `pydantic` >= 2 | スキーマ生成を `BaseModel` に寄せる場合 |

### 8.3 検討した代替案

| 候補 | 不採用理由 |
|------|----------|
| `argparse` (stdlib) | サブコマンドの型補完が貧弱。manifest 自動生成しづらい |
| `click` | typer の方が型ヒント連動で薄く書ける |
| `fire` | `--help` の品質が低い、CLI 一級プロダクトには向かない |
| `tabulate` | rich でカバー |

### 8.4 `pyproject.toml` への追加方針

```toml
[project]
dependencies = [
    "httpx>=0.28.1",
    "lxml>=6.1.1",
    "typer>=0.12",
    "rich>=13",
]

[project.optional-dependencies]
dev = ["pytest>=9.0.3"]
cli-yaml = ["pyyaml>=6"]
cli-jmespath = ["jmespath>=1"]

[project.scripts]
kuopac = "kuopac.cli.main:app"   # typer の app
```

`uv add typer rich` で追加。

---

## 9. ファイル構成

```
src/kuopac/
  cli/
    __init__.py
    __main__.py           # `python -m kuopac` のエントリ
    main.py               # typer app の組み立て
    config.py             # グローバル設定 (フォーマット等)
    commands/
      __init__.py
      search.py
      detail.py
      holdings.py
      status.py
      suggest.py
      did_you_mean.py
      facets.py
      synopsis.py
      schema_cmd.py       # schema は予約語かもなので
      manifest.py
      version.py
    formatters/
      __init__.py         # 共通: pick_formatter(format, type)
      _envelope.py        # type/schema_version/data ラッパ
      _serialize.py       # dataclass → dict 再帰変換
      table.py            # rich.Table を組み立てる
      json_fmt.py
      ndjson_fmt.py
      tsv.py
      yaml_fmt.py         # 任意
    projection.py         # --fields のパス射影
    errors.py             # CLI 固有エラー → exit code
    explain.py            # --explain / --explain-json (httpx event hooks)
    schema_gen.py         # dataclass → JSON Schema
tests/
  cli/
    test_search.py
    test_detail.py
    test_formatters.py
    test_schema.py
    test_manifest.py
    fixtures/
      example_search.html
      example_detail.html
```

### `formatters/_serialize.py` の責任分離
- 既存の `_parse.py` の dataclass を **CLI 専用ロジックを混ぜずに** 直列化
- enum を name に
- Holding.status_query は JSON では `null` で出さず、`{"blipkey": "..."}` だけ残す等の **CLI 側でのプライバシ/簡略化** を一箇所に集約
- 入力: 任意の dataclass / list / dict / scalar
- 出力: JSON 化可能な dict / list / scalar

### `explain.py` の使い方
`HttpSession` に request/response event hook を仕込み、`stderr` または
`_meta.requests[]` に蓄積する。typer の context に保持。

---

## 10. 実装ロードマップ

### Phase 1: スケルトン (半日)
- [ ] `cli/main.py` で typer app 作成
- [ ] `[project.scripts]` 登録 & 再インストール確認
- [ ] `kuopac --help` / `kuopac version` 動作
- [ ] グローバル `--format` `--quiet` `--explain` フラグ
- [ ] `formatters/_envelope.py` `_serialize.py` 実装
- [ ] `kuopac search <keyword> --format=json` で `SearchResult` を envelope に包んで吐く

### Phase 2: 基本コマンド (1日)
- [ ] `search` の詳細フラグ全部 (--title --author --year など)
- [ ] `detail` (`--with` なし版)
- [ ] `suggest`
- [ ] `--format=table` の最低限 (rich.Table)
- [ ] `--format=ndjson`
- [ ] tests/cli の golden output 系テスト

### Phase 3: 統合コマンド (1日)
- [ ] `--with holdings` (1 POST 追加)
- [ ] `--with synopsis` / `--with synopsis-openbd`
- [ ] `holdings` コマンド (batch)
- [ ] `status` コマンド
- [ ] `facets` コマンド
- [ ] `--refine` 統合

### Phase 4: ページネーション (半日)
- [ ] `--all` `--max-pages` `--start`
- [ ] ndjson 逐次出力

### Phase 5: エージェント向け (1日)
- [ ] `schema_gen.py` (dataclass → JSON Schema)
- [ ] `kuopac schema` `kuopac schema BookDetail`
- [ ] `kuopac manifest`
- [ ] `--explain-json` (req メタを envelope に埋める)
- [ ] エラー JSON 化

### Phase 6: 仕上げ (半日)
- [ ] `--fields` プロジェクション
- [ ] `--no-color` / 色付け調整
- [ ] `--strict` 終了コード調整
- [ ] README の CLI セクション追加
- [ ] examples に `examples/cli/` ディレクトリ作成 (シェルスクリプト + AI agent prompt サンプル)

---

## 11. オープンな設計判断 (実装者が決めるべきこと)

### Q1. CLI 名は `kuopac` で確定 (済)
✅ パッケージ名と一致。

### Q2. `KulineClient` クラス名は維持
✅ KULINE は OPAC のサービス固有名。`Anthropic` クラスを `anthropic` package が
持つのと同じ命名規約。

### Q3. `--format` のデフォルト
- 案A: 常に `table` (Unix 流儀)
- 案B: TTY 自動判定 (`isatty()` で json/table 切替) ← **推奨**

### Q4. `--all` 時の安全弁
- 最大ページ数のデフォルト
- 案: デフォルト `--max-pages 5`, `--max-pages 0` で無制限
- KULINE への礼節として `--rate-limit 1.5` がデフォルト推奨

### Q5. `schema` コマンドのスキーマ形式
- 案A: 純 JSON Schema (`{"$schema": "https://json-schema.org/...", "type": "object", ...}`)
- 案B: 独自軽量フォーマット
- → **案A 推奨** (エージェントが pydantic 等で受けられる)

### Q6. `manifest` の対象
- 案A: 各コマンドの引数 + 戻り値型のみ
- 案B: 上記 + 全 dataclass の JSON Schema 埋め込み
- → **案B 推奨** (1ファイルで完結する自己記述カタログ)

### Q7. Python の `--lang` グローバルフラグの扱い
- `lang=0/1` を全コマンドに伝播
- `kuopac search ... --lang en` で検索結果ラベルが英語化される
- ただし書誌内容自体には影響しない

### Q8. `--with live-status` を `detail` から有効にすべきか
- 1 detail = N+1 通信になるので原則違反気味
- **明示オプトインなら原則維持** (ユーザが選んだ)
- 警告を stderr に出す: "fetching live status for N copies (N requests)"

### Q9. `kuopac search "X" | kuopac detail` の パイプ対応
- 案: `detail` が標準入力で bibid を受け付ける (改行区切り)
- 例: `kuopac search Python --format ndjson --fields bibid | kuopac detail -`
- 各 bibid に対し1 GET 発射。並列化は `--concurrency N` で。

### Q10. レート制御の実装位置
- `HttpSession` (ライブラリ側) に `min_interval` パラメータ追加 vs CLI 側で sleep
- → ライブラリ側がスマートか。`HttpSession(min_interval=1.5)` で受ける

### Q11. AI agent 向け補助コマンド: `kuopac eval`
- 案: 自然言語クエリを受けて検索 → 例: `kuopac eval "Python 入門書で2020-2024年" --json`
- LLM 呼び出しが要るので慎重に。**初版では入れない**。

---

## 12. JSON Schema 生成のスケッチ

`schema_gen.py`:

```python
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import get_args, get_origin, Union

def dataclass_to_schema(cls) -> dict:
    props = {}
    required = []
    for f in fields(cls):
        s = type_to_schema(f.type)
        props[f.name] = s
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)
    return {
        "type": "object",
        "title": cls.__name__,
        "properties": props,
        "required": required,
    }

def type_to_schema(t):
    if t is str: return {"type": "string"}
    if t is int: return {"type": "integer"}
    if t is bool: return {"type": "boolean"}
    if t is float: return {"type": "number"}
    if is_dataclass(t): return {"$ref": f"#/definitions/{t.__name__}"}
    if isinstance(t, type) and issubclass(t, Enum):
        return {"enum": [e.name for e in t]}
    origin = get_origin(t)
    if origin is list:
        (inner,) = get_args(t)
        return {"type": "array", "items": type_to_schema(inner)}
    if origin is Union:
        args = [a for a in get_args(t) if a is not type(None)]
        if len(args) == 1:
            sub = type_to_schema(args[0])
            return {"oneOf": [sub, {"type": "null"}]}
    if origin is dict:
        k, v = get_args(t)
        return {"type": "object", "additionalProperties": type_to_schema(v)}
    return {"type": "string"}  # fallback
```

`PEP 604` の `str | None` も `get_origin` が `UnionType` を返すので対応必要。

---

## 13. 受け入れテスト (実装完了の判定)

### 13.1 機能テスト
- [ ] `kuopac search Python --format json | python -c "import json,sys;d=json.load(sys.stdin);print(len(d['data']['books']))"` が整数を吐く
- [ ] `kuopac search Python --all --max-pages 2 --format ndjson | wc -l` が `2*page_size` 程度
- [ ] `kuopac detail BB08818020 --format json` が `BookDetail` envelope を吐く
- [ ] `kuopac detail BB08818020 --with holdings --format json` で `data.holdings` が空でない
- [ ] `kuopac detail BB08818020 --with synopsis --format json` で `data._supplementary` が入る
- [ ] `kuopac status <blkey> --format json` が `{"condition": "..."}` を返す
- [ ] `kuopac suggest 機械 --format json` が `{"suggestions": [...]}` を返す
- [ ] `kuopac schema BookDetail` が JSON Schema を吐き、`jsonschema` で `kuopac detail X --format json` の出力を validate できる
- [ ] `kuopac manifest --format json` が全コマンドを含む

### 13.2 エージェント親和テスト
- [ ] stderr/stdout が完全分離
- [ ] エラー時の終了コードが §7 通り
- [ ] `--dry-run` で実際のHTTP通信が発生しない (curl で監視)
- [ ] `--explain --quiet` で URL ログが stderr に出る

### 13.3 1呼び出し=1通信テスト
- [ ] `kuopac search X` の通信数を `--explain` で数え、1 GET のみと確認
- [ ] `kuopac detail Y` 同上 (1 GET)
- [ ] `kuopac detail Y --with holdings` で 2 通信 (1 GET + 1 POST)
- [ ] `kuopac detail Y --with holdings,synopsis` で 3 通信

### 13.4 既存例の差し替えテスト
`examples/01_simple_search.py` の Python コードを `kuopac search ...` 呼び出しに
書き換えた `examples/cli/01_simple_search.sh` が同じ書誌を返す。

---

## 14. 想定する使い方シナリオ

### 14.1 人間 (シェルから)
```bash
# 普通に検索して読みやすく表示
kuopac search 機械学習

# 詳細を確認
kuopac detail BB08818020

# 所蔵が知りたい
kuopac search Python --limit 5 --with holdings
```

### 14.2 シェルパイプライン
```bash
# ヒットした全 bibid を grep に渡す
kuopac search "深層学習" --all --max-pages 3 --format ndjson \
  | jq -r '.bibid' > bibids.txt

# 1冊ずつ詳細
xargs -I {} kuopac detail {} --format json < bibids.txt > details.jsonl
```

### 14.3 AI エージェント (Claude Desktop / OpenAI agents)
1. 起動時に `kuopac manifest --format json` を読み、tools として登録
2. ユーザクエリ「Python 入門書で 2022 年以降のものを 5冊挙げて、貸出可能なものだけ」を受信
3. `kuopac search --title Python --year 2022 --media book --limit 5 --with holdings --format json` を呼ぶ
4. JSON を解釈して回答
5. ユーザが「3冊目の詳細」と言ったら `kuopac detail <bibid3> --with synopsis --format json` を呼ぶ


---

## 15. 参考: 既存ライブラリAPI ↔ CLI 対応表

| KulineClient メソッド | CLI コマンド |
|---------------------|-------------|
| `search(q)` (Simple/SearchQuery 両対応) | `kuopac search` |
| `detail(bibid)` | `kuopac detail` |
| `_cinii_detail(ncid)` | `kuopac detail --scope cinii` |
| `holdings(bibids)` | `kuopac holdings` |
| `fetch_status(holding)` | `kuopac status` |
| `fetch_supplementary(book, source)` | `kuopac synopsis` |
| `suggest(term)` | `kuopac suggest` |
| `did_you_mean(result)` | `kuopac did-you-mean` |
| `facets(result, types)` | `kuopac facets` |
| `result.next_page()` | `kuopac search ... --start N` |
| `result.refine(...)` | `kuopac search ... --refine ...` |
| `result.load_holdings()` | `kuopac search ... --with holdings` |
| `result.iter_all()` | `kuopac search ... --all` |

---

## 16. 引き継ぎチェックリスト

実装エージェントに渡す前に確認:
- [ ] このドキュメントの §11 のオープン判断にざっと目を通した
- [ ] §8 の依存追加に同意 (typer / rich)
- [ ] §9 のファイル構成で問題ない
- [ ] §13 の受け入れテストが妥当
- [ ] 実装フェーズの分割は §10 で OK

実装エージェントが知っておくべき重要事項:
1. **既存 dataclass は変更しない**。CLI 専用の dict 化は `formatters/_serialize.py` に閉じ込める。
2. **1呼び出し=1通信原則は厳格に守る**。何かのコマンドで内部的に「便利のため」追加 GET を撃つのは禁止。`--with` で明示する。
3. **ライブラリ側の `HttpSession` には極力手を入れない**。CLI 固有のロジック (進捗・色付け・envelope) は CLI 層に閉じ込める。例外: `min_interval` のような薄い拡張は `HttpSession.__init__` に1引数足すだけならOK。
4. **テストの実行はネット接続を要求しない**。`tests/cli/fixtures/` に取得済み HTML を置き、`HttpSession` をモック。

以上。実装に着手して構いません。質問があれば `KulineClient` の挙動はライブラリ側のテストとして
`audit_data/` の生 HTML を参照すれば再現可能。
