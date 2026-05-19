# kuopac

[![PyPI version](https://img.shields.io/pypi/v/kuopac.svg)](https://pypi.org/project/kuopac/)
[![Python 3.12+](https://img.shields.io/pypi/pyversions/kuopac.svg)](https://pypi.org/project/kuopac/)
[![Tests](https://github.com/youseiushida/kuopac/actions/workflows/tests.yml/badge.svg)](https://github.com/youseiushida/kuopac/actions/workflows/tests.yml)
[![Live integration](https://github.com/youseiushida/kuopac/actions/workflows/live.yml/badge.svg)](https://github.com/youseiushida/kuopac/actions/workflows/live.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/youseiushida/kuopac/blob/main/LICENSE)

京都大学図書館機構の OPAC「**KULINE**」を**匿名で**叩く Python ライブラリ + CLI。
検索・書誌詳細・所蔵情報・貸出状況・あらすじ/目次までを型付きで扱える。

> **責務の境界**: 予約・ILL申込・MyOPAC 貸出履歴など SSO ログインが必要な操作は対象外です。
> 京大 SSO セッションが必要な場合は [kuauth](https://pypi.org/project/kuauth/) を使い、その認証済み session で必要な MyOPAC エンドポイントを自前で叩いてください (詳細は[スコープ外](#スコープ外--sso-認証が必要な操作))。

```python
from kuopac import KulineClient, SearchQuery, MediaType

with KulineClient() as kuline:
    result = kuline.search("機械学習")          # 1 GET
    print(f"{result.total} 件ヒット")

    result.load_holdings()                     # 1 POST で全書籍の所蔵 (在架/オンライン/他大学)
    for book in result.books[:5]:
        for h in book.holdings:
            print(f"{h.location}  {h.call_no}  → {h.availability}")
```

実行例(2026年5月時点):

```
1751 件ヒット
情報学||図書室  548.3||TSU 78||1   → available_on_shelf
情報学||図書室  007.6||ISH 76||1   → available_on_shelf
情報学||図書室  007.1||TAK 196||1  → available_on_shelf
吉田南||1F 和書  007.6||K||219    → available_on_shelf
```

> `load_holdings()` は **所蔵 (在架/オンライン/他大学)** だけ。
> live な貸出状態 (`貸出中[返却期限]`) は `kuline.fetch_status(holding)` が**1冊につき +1 GET**。

---

## インストール

Python 3.12+ 必須。

```sh
uv tool install kuopac   # CLI として使う (グローバル install)
uv add kuopac            # ライブラリとして自分のプロジェクトに追加
```

開発版:

```sh
git clone https://github.com/youseiushida/kuopac.git
cd kuopac
uv pip install -e ".[dev]"
```

Windows で日本語出力が文字化けする場合は環境変数を設定:

```sh
PYTHONIOENCODING=utf-8 uv run python examples/01_simple_search.py
```

---

## CLI

ライブラリと同じ機能を `kuopac` コマンドから叩ける。出力は **TTY なら表組み・パイプなら JSON** に自動切替。
詳細仕様は [docs/cli-design.md](https://github.com/youseiushida/kuopac/blob/main/docs/cli-design.md)。

```sh
kuopac search 機械学習                                # 表組みで上位 20 件
kuopac --json search "Python" --year 2022-2024 --media book
kuopac --json detail BB08818020 --with holdings,synopsis
kuopac --format ndjson search Python --all --max-pages 3 | jq '.bibid'
kuopac --json holdings BB08818020 BB08823008          # 1 POST で複数 bibid の所蔵
kuopac --json status BL19200695                       # 個別冊の貸出状態
kuopac --json suggest 機械                             # サジェスト候補
kuopac --json manifest                                # エージェント用カタログ (全コマンド+型スキーマ)
kuopac --json schema BookDetail                       # 個別型の JSON Schema
```

主要グローバルフラグ: `--format {table,json,ndjson,tsv,yaml}` / `--fields ids.bibid,title` / `--explain-json` (`_meta.requests[]` 埋込) / `--strict` (0件ヒットを exit 1) / `--rate-limit SECONDS`。

`kuopac manifest --format json` を tools catalog として読み込めば、Claude Desktop / OpenAI agents から型安全に呼び出せる。

---

## 設計方針

### 1関数呼び出し = 1HTTPリクエスト

KULINE のサーバ仕様を実通信で検証したうえで、ライブラリの全公開メソッドは
原則として **1 メソッド = 1 リクエスト**。**暗黙の preflight・暗黙の N+1 ファンアウトは無い**:
CSRF preflight は初回 POST 直前に1回だけ遅延発生し、`facets()` のファセット並列や
`iter_all()` の全ページ走査はユーザが明示的に opt-in したときのみ。

| メソッド | 通信内容 |
|---------|---------|
| `kuline.search(...)` | 1 GET |
| `kuline.detail(bibid, scope=...)` | 1 GET (`scope=Scope.CINII` で他大学詳細を強制可) |
| `kuline.holdings(bibids)` | **1 POST** (バッチ; 初回のみ CSRF preflight が +1 GET) |
| `result.next_page()` | 1 GET |
| `result.start_at(n)` | 1 GET (任意の start オフセットに飛ぶ) |
| `result.refine(...)` | 1 GET |
| `result.load_holdings()` | **1 POST** (全書籍ぶん一括取得) |
| `kuline.fetch_status(holding)` | 1 GET (任意; 通常は不要) |
| `kuline.fetch_supplementary(book)` | 1 GET (任意) |
| `kuline.suggest(term)` | 1 GET |
| `kuline.facets(result)` | N GET (ファセット種別ごとに 1 GET、同期 for ループ。並列化が必要なら threadpool / async でラップ) |

### Lazy CSRF

検索系 GET はクッキーもセッションも不要(完全 stateless)。CSRF 対が必要なのは
所蔵情報の POST など一部のみ。ライブラリは **初回 POST の直前まで** CSRF を取りに行かない。
検索だけの利用者はプリフライトコストを払わない。

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

# 任意の start オフセットに飛ぶ (1-indexed)
page = result.start_at(41)         # 41件目から1ページぶん
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

### 所蔵情報 (1 POST で全部) と貸出状態 (要追加 GET)

```python
result = kuline.search("プログラミング")
result.load_holdings()        # ← 1 POST: 所蔵位置だけ取れる
                              #  (KULINE は live 状態を別 AJAX で返すので
                              #   load_holdings 単体では h.condition は None)

for book in result.books:
    for h in book.holdings:
        print(h.location, h.call_no, h.availability)
        # 在架本   → "available_on_shelf"
        # 電子本   → "online"
        # 他大学本 → "remote"
```

live な貸出状態 (`貸出中[返却期限]`・「研究室」配置など) を取るには **1冊につき 1 GET** が要る。
明示オプトインなのは N+1 ファンアウトを暗黙発生させないため:

```python
for h in book.holdings:
    kuline.fetch_status(h)            # 1 GET; h.condition に書き戻される
    print(h.location, h.availability)
    # 貸出中本 → "貸出中[2026.06.11返却期限]"
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
cinii_book = kuline.detail(result.books[0])   # Book を渡せば ncid を自動使用
for h in cinii_book.holdings:
    print(f"{h.institution}  call={h.cinii_orderno}")

# 文字列 ncid から直接 CiNii 詳細を引きたい場合は scope を明示
cinii_book = kuline.detail("BD18537825", scope=Scope.CINII)
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

## スコープ外 — SSO 認証が必要な操作

kuopac は **匿名カタログアクセス専用**。次の操作は対象外:

- **MyOPAC**: 予約 / ILL申込 / 購入申込 / 貸出履歴
- **個人化された機能**: ブックマーク / タグ / マイリスト

京大 SSO 認証セッションが必要なら、姉妹ライブラリ **[kuauth](https://pypi.org/project/kuauth/)** が KULINE を含む京大 SP の認証セッションを提供する:

```python
from kuauth import KyotoUAuth, MyKULINE

with KyotoUAuth(username="a0XXXXXX", password="...") as auth:
    r = MyKULINE(auth).get("/opac/opac_search/?lang=0&...")
    # 必要なエンドポイント (予約フォーム POST 等) を HAR で特定して自前で叩く
```

kuopac と kuauth は **直接統合しない方針** です。kuopac は **匿名アクセス前提の単純な API surface** を保ち、SSO 認証ロジックは kuauth に分離します。両方使いたい場合は kuauth のセッションで生 HTTP を叩く形で書いてください。

---

## ライセンス

MIT (詳細は `LICENSE`)。
