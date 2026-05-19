# kuopac

京都大学図書館機構の OPAC「**KULINE**」を叩く Python ライブラリ。
検索・書誌詳細・所蔵情報・貸出状況・あらすじ/目次までを型付きで扱える。

```python
from kuopac import KulineClient, SearchQuery, MediaType

with KulineClient() as kuline:
    result = kuline.search("機械学習")          # 1 GET
    print(f"{result.total} 件ヒット")

    result.load_holdings()                     # 1 POST で全書籍の所蔵+貸出状態
    for book in result.books[:5]:
        for h in book.holdings:
            print(f"{h.location}  {h.call_no}  → {h.availability}")
```

実行例(2026年5月時点):

```
1751 件ヒット
情報学||図書室  548.3||TSU 78||1   → available_on_shelf
情報学||図書室  007.6||ISH 76||1   → 貸出中[2026.06.11返却期限]
情報学||図書室  007.1||TAK 196||1  → 貸出中[2026.06.17返却期限]
吉田南||1F 和書  007.6||K||219    → available_on_shelf
```

---

## インストール

Python 3.12+ 必須。

```sh
git clone <repo>
cd kuopac
uv pip install -e .
```

Windows で日本語出力が文字化けする場合は環境変数を設定:

```sh
PYTHONIOENCODING=utf-8 uv run python examples/01_simple_search.py
```

---

## 設計方針

### 1関数呼び出し = 1HTTPリクエスト

KULINE のサーバ仕様を実通信で検証したうえで、ライブラリの全公開メソッドは
原則として **1 メソッド = 1 リクエスト**。プリフライト/N+1 ファンアウトは行わない。

| メソッド | 通信内容 |
|---------|---------|
| `kuline.search(...)` | 1 GET |
| `kuline.detail(bibid)` | 1 GET |
| `result.next_page()` | 1 GET |
| `result.refine(...)` | 1 GET |
| `result.load_holdings()` | **1 POST** (全書籍ぶん一括取得) |
| `kuline.fetch_status(holding)` | 1 GET (任意; 通常は不要) |
| `kuline.fetch_supplementary(book)` | 1 GET (任意) |
| `kuline.suggest(term)` | 1 GET |
| `kuline.facets(result)` | N GET (ファセット種別ごとに並列叩く意図的なファンアウト) |

### Lazy CSRF

検索系 GET はクッキーもセッションも不要(完全 stateless)。CSRF 対が必要なのは
所蔵情報の POST など一部のみ。ライブラリは **初回 POST の直前まで** CSRF を取りに行かない。
検索だけの利用者はプリフライトコストを払わない。

### TLS

KULINE は古い cipher を要求するため、`ssl.SSLContext.set_ciphers("DEFAULT@SECLEVEL=0")`
を自動設定する。利用者は意識不要。

---

## クイックリファレンス

### 検索 (簡易)

```python
result = kuline.search("Python 入門")
print(result.total)            # 該当件数
for book in result.books:      # 1ページ目(デフォルト20件)
    print(book.bibid, book.title)
```

### 検索 (詳細条件 — fluent builder)

```python
from kuopac import SearchQuery, MediaType, Sort, BoolOp

q = (SearchQuery()
     .title("機械学習")
     .author("斎藤", op=BoolOp.AND)
     .year_range(2020, 2024)
     .media(MediaType.BOOK, MediaType.EBOOK)
     .sorted_by(Sort.YEAR_DESC)
     .per_page(50))

result = kuline.search(q)
```

利用可能なフィールド:
`.any() / .title() / .title_exact() / .author() / .publisher() / .subject() /
.isbn() / .issn() / .ncid() / .bibid() / .call_no() / .add(SearchField.XXX, ...)`

### ページング

```python
# 自動: 全ページを走査(上限指定可)
for book in result.iter_all(max_pages=5):
    print(book.title)

# 手動: 1ページずつ
page = result
while page is not None:
    do_something(page.books)
    page = page.next_page()
```

### ファセット集計と再検索

```python
from kuopac import FacetType

facets = kuline.facets(result, types=[FacetType.PUBLISHER, FacetType.YEAR])
for v in facets[FacetType.PUBLISHER].top(10):
    print(f"  {v.label}  ({v.count})")

# ファセット適用 (1 GET)
narrowed = result.refine(publisher="丸善出版", datatype="10")
```

### 所蔵情報 + 貸出状態 (1 POST で全部)

```python
result = kuline.search("プログラミング")
result.load_holdings()        # ← 1 POST だけ

for book in result.books:
    for h in book.holdings:
        print(h.location, h.call_no, h.availability)
        # 在架本   → "available_on_shelf"
        # 貸出中本 → "貸出中[2026.06.11返却期限]"
        # 電子本   → "online"
        # 他大学本 → "remote"
```

特殊状態(例:「研究室」設置)を明示的に取りたいときだけ:

```python
status = kuline.fetch_status(holding)   # 1 GET
```

### 書誌詳細

```python
book = kuline.detail("BB08818020")     # bibid 文字列でも Book でもOK

print(book.title_main)                  # タイトル
print(book.responsibility)              # 責任表示 (著/編/訳)
print(book.publication.publisher)       # 構造化された出版情報
print(book.publication.year)            # 2026
print(book.rda_types.content)           # "テキスト"
print(book.volume_info_parts["ISBN"])   # "9784297153496"

for author in book.authors:
    print(f"{author.name} ({author.kana}, role={author.role}, auid={author.auid})")

for subject in book.subjects:           # [{scheme: "BSH", term: "人工知能"}, ...]
    print(f"  {subject.scheme}: {subject.term}")

for cls in book.classifications:        # [{scheme: "NDC9", code: "007.13"}, ...]
    print(f"  {cls.scheme}: {cls.code}")

# シリーズ親書誌の子(巻)リスト
for child in book.children:
    print(f"  {child.number}. [{child.bibid}] {child.title}")

print(book.external_links.cinii)        # CiNii Books の本書誌へのリンク
print(book.external_links.permalink)    # KULINE 永久URL
```

### あらすじ / 目次 (オプトイン)

```python
from kuopac import SupplementarySource

sup = kuline.fetch_supplementary(book, source=SupplementarySource.BOOKPLUS)
if sup:
    print(sup.synopsis)        # 「性能を制する者が、ＡＩを制す。」
    for ch in sup.toc:
        print(ch)              # 「第１章 パフォーマンスエンジニアリング概論」 …
```

データが無い書籍 (大学図書館蔵書では多い) のときは `sup.empty == True`、
`bool(sup) is False`。

### 他大学検索 (CiNii Books)

```python
from kuopac import Scope

result = kuline.search("深層学習", scope=Scope.CINII)
# または
q = SearchQuery().title("深層学習").in_cinii()
result = kuline.search(q)

for book in result.books:
    print(book.ncid, book.title)

# 他大学詳細 (所蔵館リスト付き)
cinii_book = kuline.detail(result.books[0])   # ncid を自動使用
for h in cinii_book.holdings:
    print(f"{h.institution}  call={h.cinii_orderno}")
```

### サジェスト / スペル修正

```python
suggestions = kuline.suggest("機械")
# → ['日本機械学会', '機械学習', '機械工業', ...]

result = kuline.search("Pithon")           # 1 件しかヒットしない
candidates = kuline.did_you_mean(result)
# → ['python', 'pitson', 'oithona']
```

---

## モデル一覧 (公開 dataclass)

| 型 | 用途 |
|----|------|
| `SearchResult` | 検索結果1ページ。`books` / `total` / `opkey` / `next_page()` / `iter_all()` / `refine()` / `load_holdings()` |
| `Book` | 検索結果一覧の1書誌(軽量) |
| `BookDetail` | 詳細ページから取れる全フィールド (子書誌含む) |
| `BibIdentifiers` | bibid / ncid / isbn / issn / nbn |
| `AuthorHeading` | 著者標目: name / kana / role / auid |
| `Subject` | 件名: scheme / term |
| `Classification` | 分類: scheme / code (NDC9, NDLC など) |
| `ParentSeries` | 親書誌/シリーズの参照 |
| `ChildBib` | シリーズ親書誌の子(巻)1件 |
| `Publication` | 構造化された出版情報 (place / publisher / year / edition / series) |
| `RdaTypes` | RDA 表現種別/機器種別/キャリア種別 |
| `Holding` | 所蔵1冊 (location / call_no / condition / online_url / institution …) |
| `BLStatusQuery` | 貸出状態取得のためのパラメータ束 (内部用) |
| `Supplementary` | あらすじ + 目次 |
| `FacetInfo` / `FacetValue` | ファセット情報 |
| `ExternalLinks` | 他検索サイト誘導 (CiNii / NDL / Google …) |

---

## 例(`examples/`)

| ファイル | 内容 |
|---------|------|
| `01_simple_search.py` | キーワード1つで検索 |
| `02_advanced_query.py` | `SearchQuery` ビルダーで多条件検索 |
| `03_pagination.py` | `iter_all()` / `next_page()` |
| `04_facets_and_refine.py` | ファセット集計 + `.refine()` 絞り込み |
| `05_detail_and_holdings.py` | 詳細ページから書誌 + 所蔵 |
| `06_cinii_other_universities.py` | 他大学(CiNii Books)検索 |
| `07_suggest_and_spell.py` | サジェスト + もしかして |
| `08_search_with_holdings.py` | 検索結果一覧に所蔵+貸出状態を一括ロード |
| `09_synopsis_and_toc.py` | あらすじ/目次取得 (BookPlus / openBD) |

実行:

```sh
PYTHONIOENCODING=utf-8 uv run python examples/08_search_with_holdings.py
```

---

## ドキュメント

- **`docs/opac-spec.md`** — KULINE OPAC 全エンドポイントの通信契約と HTML スキーマ。
  HAR と実通信の両方で検証済。観測根拠を `[verified]`/`[har]`/`[inferred]` で明記。
- **`docs/audit-report.md`** — ライブラリ出力と生 HTML の網羅性監査レポート。
  検索パラメータの実適用検証、書誌詳細・所蔵テーブルの抽出網羅率、修正したバグ一覧。
- **`scripts/probe.py`** + **`scripts/probes.py`** — 仕様調査用の生 HTTP プローブ。
- **`scripts/audit.py`** — 抽出網羅性の自動監査ハーネス。

---

## 未対応 / 既知の制限

- **MyOPAC ログイン**: 予約・ILL申込・購入申込・貸出履歴。実装してない (cookie+ID/PW 必要)。
- **エクスポート**: `opac_mailsend/` `opac_fileout/` `opac_endnote/` `opac_mendeley/` 未対応。
- **書影画像**: `opac_imgoutlink/` は仕様調査済だが `Book`/`BookDetail` に未統合。
- **類似資料/閲覧推薦**: 詳細ページの AJAX セクション。生 API は documented だが未公開。
- **async 版**: 現状 sync のみ。`asyncio.to_thread` で逃げるか、`httpx.AsyncClient` 版を追加実装の余地。

いずれも `HttpSession` + パーサ基盤(`_parse.py`)に1メソッドずつ足せば追加可能。

---

## ライセンス

MIT (詳細は `LICENSE`)。
