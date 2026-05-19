# 京都大学 OPAC (KULINE) 図書検索 仕様

調査対象: `https://kuline.kulib.kyoto-u.ac.jp/opac/` (京大図書館機構 KULINE)

調査方法:
1. 提供されたHARファイル(`har/`)から既知の挙動を抽出
2. `scripts/probe.py` + `scripts/probes.py` で実通信して検証

各事項に **観測根拠** をマーカで付記:
- **[verified]** 実通信で確認済み
- **[har]** HARでのみ確認 (再現通信せず)
- **[inferred]** ソース(JS等)から推測

このドキュメントは KULINE をラップする図書検索ライブラリの実装リファレンス。

---

## 0. プロトコル基本 [verified]

| 項目 | 値 |
|------|----|
| ベースURL | `https://kuline.kulib.kyoto-u.ac.jp` |
| 文字コード | UTF-8 (リクエスト/レスポンス両方) |
| 言語切替 | クエリ `lang=0` (日本語) / `lang=1` (英語) |
| TLS | **TLS 1.2 だが弱いcipher必須**。Python httpx では `ssl.SSLContext.set_ciphers("DEFAULT@SECLEVEL=0")` で接続可。`SECLEVEL=2` (デフォルト) では `TLSV1_ALERT_INSUFFICIENT_SECURITY` |
| Cookie | `csrftoken` (Max-Age 約1年), `sessionid` (HttpOnly), `FJNADDSPID` (CDN負荷分散) |
| Server | Apache + Django |
| サーバヘッダ | `X-Frame-Options: DENY, SAMEORIGIN` / `X-Content-Type-Options: nosniff` / `Referrer-Policy: same-origin` |

### 0.1 認証
検索系はすべて匿名で叩ける。MyOPAC・ILL申込・予約・購入申込のみ要ログイン。

### 0.2 セッション/Cookie 要件 [verified — 実通信検証済]

KULINE は **GET系で完全 stateless**、**POST系で標準 Django CSRF対** という二層構造。ライブラリ実装は GET 系を最大限 stateless に扱える。

| 操作 | Cookie | Referer | 備考 |
|------|--------|---------|------|
| `/opac/opac_search/` (検索・ページング・facet apply) | 不要 | 不要 | 完全 stateless |
| `/opac/opac_facet/`, `/opac/opac_suggest/`, `/opac/opac_spellcheck/` | 不要 | 不要 | |
| `/opac/opac_details/`, `/opac/opac_detail_ciniibooks/`, `/opac/opac_detail_book/` | 不要 | **必要** | 無いと 403 Forbidden (199バイト) |
| `/opac/opac_openbdinfo/`, `/opac/opac_bookplusinfo/`, etc. | 不要 | 不要(推定) | |
| `/opac/opac_search_localhold/` (POST), `/opac/opac_imgoutlink/` (POST), `/opac/opac_stamp/` (POST) | **必要** (csrftoken) | 不要 | Django CSRF: cookie csrftoken と form csrfmiddlewaretoken がマスク対応関係になっている必要 |

**[verified] 確認した事実:**
- 検索結果の `opkey` は **セッション非依存**。別clientで生成した opkey を別clientで `amode=22` (ページング) / `amode=23` (ファセット適用) に渡しても200を返す。サーバ側キャッシュキーで、IP や Cookie に紐づかない
- `opac_details/` の bare アクセスは 403。`Referer: https://kuline.kulib.kyoto-u.ac.jp/opac/opac_search/?lang=0` を付与すれば fresh client / no-cookie でも200
- POST系は Referer 不要。Django CSRF の対 (cookie csrftoken と form csrfmiddlewaretoken のペア) が同じ起源から得られていれば200。別 client の csrf を借りてくると403

### 0.3 CSRF (POST系のみ) [verified]

Django 標準の二重提出 CSRF:

1. Cookie `csrftoken` (HttpOnly でない、JS から見える)
2. POST body の `csrfmiddlewaretoken` フィールド

両者は **同じ secret** から生成されており、サーバが unmask して一致を確認する。
**実測**: form の値と cookie の値は **異なる文字列** に見えるが (form 側は毎回マスクされた異なる値を出す)、unmask 後の secret は同じ。

→ ライブラリ実装:
- 初回POST直前に `GET /opac/opac_search/?lang=0` を1回だけ叩いて
  - Cookie csrftoken を httpx Client に持たせる(自動)
  - HTML から `<input type="hidden" name="csrfmiddlewaretoken" value="..."/>` を抜き出してキャッシュ
- 以降同一Client内ではこのキャッシュを再利用してよい(cookie csrftoken は1年TTL)
- AJAX 慣習として `X-CSRFToken: <token>` と `X-Requested-With: XMLHttpRequest` ヘッダも付ける(必須ではないが付けても害なし)

**警告**: HTMLの csrfmiddlewaretoken は **シングルクォート** で出ているケースがある:
```html
<input type='hidden' name='csrfmiddlewaretoken' value='HToIq383...' />
```
抽出正規表現は `['\"]` 両対応にする。

### 0.4 レート
明示的なレート制限の通知なし。礼節として 1.0〜2.0 秒間隔推奨。

---

## 1. エンドポイント一覧 [verified]

| パス | メソッド | レスポンス | 用途 |
|------|---------|------------|------|
| `/opac/opac_search/` | GET | HTML | 検索 (簡易/詳細/他大学)・結果一覧・ソート・件数・ファセット適用 |
| `/opac/opac_details/` | GET | HTML | 自館書誌詳細 |
| `/opac/opac_detail_ciniibooks/` | GET | HTML | 他大学書誌詳細 (CiNii Books) |
| `/opac/opac_detail_ciniibooks/pt_list/` | GET | HTML 断片 | CiNii 関連書誌AJAX |
| `/opac/opac_detail_book/` | GET | HTML 断片 | 個別資料(冊単位)モーダル |
| `/opac/opac_authority/` | GET | HTML | 著者標目詳細 (auid キー) |
| `/opac/opac_suggest/` | GET | **JSON** (text/javascript) | サジェスト |
| `/opac/opac_spellcheck/` | GET | HTML 断片 | スペル候補 |
| `/opac/opac_facet/` | GET | HTML 断片 | ファセット (種別別) |
| `/opac/opac_search_localhold/` | POST | **JSON** (内に HTML) | 所蔵情報一括取得 |
| `/opac/opac_imgoutlink/` | POST/GET | **JSON** | 書影URL |
| `/opac/opac_bookplusimg/` | GET | HTML | 書影プレビュー |
| `/opac/opac_openbdinfo/` | GET | HTML 断片 | openBD補助情報 |
| `/opac/opac_bookplusinfo/` | GET | HTML 断片 | BookPlus補助情報 (あらすじ・目次) |
| `/opac/opac_stamp/` | POST/GET | **JSON** | レコメンドスタンプ |
| `/opac/opac_360link/` | GET | HTML/302 | 外部リゾルバ橋渡し |
| `/opac/opac_blstat/` | GET | HTML 断片 (空のことも) | 個別冊の貸出状況 |
| `/opac/opac_tag/detail/` | GET | HTML/JSON | タグ |
| `/opac/opac_link/bibid/<bibid>` | GET (302) | → opac_details | パーマリンク |
| `/opac/opac_mailsend/`, `/opac/opac_fileout/`, `/opac/opac_endnote/`, `/opac/opac_mendeley/` | GET | HTML/ファイル | エクスポート |
| `/opac/ill/`, `/opac/bok/`, `/opac/odr/` | GET/POST | HTML | ILL申込・購入申込・予約 (要ログイン) |

---

## 2. 検索リクエスト `/opac/opac_search/` [verified]

### 2.1 制御パラメータ

| パラメータ | 値 | 意味 |
|-----------|----|------|
| `lang` | `0`/`1` | 日本語/英語 (UI言語のみ。検索結果の中身には影響なし) |
| `cmode` | `0` / `5` | 検索コレクション: 0=自館KULINE, 5=他大学CiNii Books |
| `smode` | `0` / `1` | 検索タブ: 0=簡易, 1=詳細 |
| `amode` | `2`/`9`/`11`/`22`/`23` | アクション種別 (下記) |
| `reqCode` | `fromsrch` / `fromlist` / `frombib` / `back` | 呼び出し元タグ |
| `opkey` | `B<14桁>` | 検索セッションキー (サーバ発行) |
| `tikey` | 空 | 用途不明・常に空 |
| `appname`,`version` | `Chrome`/`120.0.0.0` | クライアント識別 (省略可) |
| `csrfmiddlewaretoken` | 64文字 | POST時必須 |
| `start` | `1`,`21`,... | ページ先頭(1始まり) |
| `disp` / `disp_exp` / `list_disp` | `20`/`50`/`100`/`200`/`500` | 1ページあたり件数 |
| `sort` / `sort_exp` / `list_sort` | `0`〜`6` | ソート (§2.5) |
| `place` | 空 | 配架場所絞り込み (空=全館) |
| `check` | `00000000000000000000` | 選択行ビットマスク文字列 (20字0埋め) |
| `chk_st` | `0` | チェック開始フラグ |

#### amode 値の意味 [inferred + verified]
- `2` = 検索実行 (新セッションで `opkey` を発行)
- `9` = 結果一覧再表示 (戻る)
- `11` = 書誌詳細表示 (`opac_details`/`opac_detail_ciniibooks` で使用)
- `22` = ページング/ソート/件数変更 (既存 `opkey` を再利用)
- `23` = ファセット適用 (既存 `opkey` を再利用、 `fc_val=...` 付随)

### 2.2 簡易検索 (smode=0) [verified]

```http
GET /opac/opac_search/?lang=0&amode=2&cmode=0&smode=0&kywd=<KW>&index_amazon_s=Books&node_s=
```

| パラメータ | 説明 |
|-----------|------|
| `kywd` | フリーキーワード (全項目対象, スペース区切り AND) |
| `index_amazon_s` | UIの Amazon タブ用 (検索結果には無関係。`Books`/`Music`等) |
| `node_s` | 不明・空 |

ヒット数の例 (2026-05-19 時点):
- `kywd=機械学習` → 886 件
- `kywd=Python` → 多数
- `kywd=9784297153496` (ISBN直入力) → 1件 (ISBN フィールド指定なしでもヒット)
- `kywd=zzz_no_such_keyword_xyz9999` → 0件 (ゼロヒットページにメッセージ「該当する資料が大学に見つかりません。」)

### 2.3 詳細検索 (smode=1, cmode=0) [verified]

最大3条件をAND/OR/NOTで連結。

```http
GET /opac/opac_search/?lang=0&amode=2&cmode=0&smode=1
    &kywd1_exp=<KW1>&con1_exp=<F1>
    &op2_exp=AND&kywd2_exp=<KW2>&con2_exp=<F2>
    &op3_exp=AND&kywd3_exp=<KW3>&con3_exp=<F3>
    &file_exp=1&file_exp=3        # 媒体種別(チェックボックス、複数同名)
    &vfile_exp=10&jf_exp=         # 隠し補助 (常時10/空でOK)
    &year1_exp=2020&year2_exp=2023 # 出版年範囲
    &cntry_exp=0                   # 出版国
    &txtl_exp=0                    # 本文言語
    &cls_exp=0                     # 分類
    &dpmc_exp=all                  # 部局
    &lib_exp=                      # 特殊コレクション
    &sort_exp=6&disp_exp=20
```

ヒットゼロでも 200 OK。`<p class="search-results-hits_num">該当件数:0件</p>` が出ない/空のときがゼロヒット。

### 2.4 検索フィールド `conN_exp` [verified]

23値。日本語ラベルと英語ラベル(lang=1)の両方を観測。

| value | 日本語ラベル | 英語ラベル | 備考 |
|-------|-------------|-----------|------|
| `all` | 全ての項目から | Any (Keyword) | |
| `titlekey_ja` | 書名に語が含まれる | Title words | 部分一致 |
| `ftitlekey` | 書名(完全形) | Full Title | 完全一致 |
| `ptblkey` | 親書誌名に語が含まれる | Parent Bibliography | 叢書名等 |
| `alkey` | 著者名に語が含まれる | Author | |
| `volkey` | 巻号 | Volume | |
| `pubkey` | 出版社・出版者 | Publisher | |
| `shkey` | 件名 | Subject | |
| `isbn` | ISBN | ISBN | ハイフン有無不問 |
| `issn` | ISSN | ISSN | |
| `callno` | 請求記号 | Call No. | |
| `bookid` | 図書(資料)番号 | Book ID | バーコード |
| `ledgerno` | 原簿番号 | Ledger No. | |
| `ncid` | NACSIS-ID (NCID) | NACSIS-ID | |
| `bibid` | 書誌ID | Bib ID | KULINE固有 |
| `clskey` | 標題分類 | Classification | |
| `cls` | 分類分類 | (Classification) | |
| `lccn` | LCCN | LCCN | |
| `ndlcn` | NDLCN・NDLPN | NDLCN/NDLPN | |
| `coden` | CODEN | CODEN | |
| `nbn` | 全国書誌番号 | NBN | JPNO 等 |
| `cmnid` | 共通コード | Common ID | |
| `othn` | その他のコード | Others | |

入力値 `kywdN_exp` の先頭 `#` は完全一致モード([inferred]; 結果ページのリンクが頻繁に `kywd1_exp=#人工知能` を生成)。

### 2.5 ソート [verified]

| value | 自館 | CiNii (`sort_ciniibooks`) |
|-------|------|--------------------------|
| `0` | 関連度 | – |
| `1` | 書名 昇順 | 関連度 |
| `2` | 書名 降順 | 出版年 古い順 |
| `3` | 著者名 昇順 | 出版年 新しい順 |
| `4` | 著者名 降順 | 所蔵館 少ない順 |
| `5` | 出版年 昇順 | 所蔵館 多い順 |
| `6` | 出版年 降順 (デフォルト) | タイトル あ→わ |
| `7` | – | タイトル わ→あ |

### 2.6 媒体種別 `file_exp` (チェックボックス, 複数同名可) [verified]

| value | 種別 |
|-------|------|
| `1` | 図書 |
| `2` | --和図書 |
| `3` | --洋図書 |
| `5` | 雑誌 |
| `6` | --和雑誌 |
| `7` | --洋雑誌 |
| `8` | 電子ブック |
| `9` | 電子ジャーナル |
| `91` | 貴重資料画像 |
| `92` | 学位論文 |

`vfile_exp` は隠し補助値で `10` 固定で観測。`jf_exp` は空。

CiNii 側 `ciniibooks_file_exp` は `1` (図書) と `5` (雑誌) のみ。

### 2.7 表示件数 [verified]

`disp_exp` / `list_disp`: `20`, `50`, `100`, `200`, `500`。`500` は実測 1.67MB の HTML を返す。

### 2.8 出版年 `year1_exp` / `year2_exp` [verified]

4桁西暦。片方のみ指定可。

### 2.9 出版国 `cntry_exp` [har]

数値コード約 40 値 (0=指定なし, 1=日本, 2=アメリカ, 3=イギリス, ...)。完全リストはランディングHTMLの `<select name="cntry_exp">` を参照。

### 2.10 本文言語 `txtl_exp` [har]

460+ 値 (0=指定なし, 1=日本語, 2=英語, 3=中国語, ...)。

### 2.11 分類 `cls_exp` [har]

NDC 系階層分類。100+ 値。

### 2.12 部局 `dpmc_exp` [har]

部局名そのものを value とするセレクト(50+ 値)。例:
- `all` = 全学(デフォルト)
- `--本部・北部`
- `--南部`
- `--桂` 等のセクション区切り (`--` プレフィクスはセクション見出し)
- 個別: `工学研究科・工学部桂図書室`, `理学部社会科学研究所図書室` 等

### 2.13 特殊コレクション `lib_exp` [har]

3桁の数値コード:
- 空 = 指定なし
- `001` アーネスト・サトウ書庫(文)
- `002` 維新特別資料文庫(文)
- `015` ドイツ語学文学コレクション(文)
- `411` ジョサイア・コンドル原図面(工図書館)
- `900` 教養図書資料
- 他多数

### 2.14 他大学検索 (cmode=5) のCiNiiフィールド [verified]

詳細検索フィールドはすべて `_ciniibooks` サフィックス:

| パラメータ | 用途 |
|-----------|------|
| `ciniibooks_file_exp` | 媒体 (1=図書, 5=雑誌) |
| `default_ciniibooks` | 全項目 |
| `titlekey_ja_ciniibooks` | タイトル |
| `ftitlekey_ciniibooks` | タイトル(完全形) |
| `alkey_ciniibooks` | 著者名 |
| `auid_ciniibooks` | 著者典拠ID (CiNii) |
| `utid_ciniibooks` | 統一タイトルID |
| `pubkey_ciniibooks` | 出版者 |
| `isbn_ciniibooks` | ISBN |
| `issn_ciniibooks` | ISSN |
| `ncid_ciniibooks` | NCID |
| `shkey_ciniibooks` | 件名 |
| `clskey_ciniibooks` | 分類 |
| `note_ciniibooks` | 注記 |
| `year1_ciniibooks`,`year2_ciniibooks` | 出版年範囲 |
| `txtl_ciniibooks` | 本文言語 |
| `sort_ciniibooks` | ソート (§2.5) |
| `ciniibooks_disp` | 件数 |

簡易検索の場合は `cmode=5&smode=0&kywd=<word>`。

---

## 3. 検索結果一覧 HTML 構造 [verified]

完全な HTML ページ。本文部の主要構造:

### 3.1 ヘッダ (件数・ソート)

```html
<p class="current-search-key">検索キーワード:<span>(...)</span></p>
<p class="search-results-hits_num pull-left">該当件数:886件</p>
<select name="list_sort" id="list_sort">...</select>
<select name="list_disp" id="list_disp">...</select>
```

総件数取得:
```py
hits_text = tree.xpath("string(//p[contains(@class,'search-results-hits_num')])")
# '該当件数:886件' から数字を抜く
```

カンマ区切り (`1,122件`) が出るのでパース時注意。

### 3.2 ゼロヒット時 [verified]

`search-results-hits_num` 自体が出力されないか空。JavaScriptで以下のメッセージが注入される:
> 該当する資料が大学に見つかりません。別の検索語で検索してください。または、リンクボタンをクリックしてください。

検出方法: `result-list` の `<li>` が0件 かつ ヒット数表示なし。

### 3.3 個別結果 `<li>` (自館 cmode=0) [verified]

```html
<ul class="result-list">
  <li>
    <input type="hidden" name="list_bibid" value="BB08815134" />
    <input type="hidden" name="list_datatype" value="10" />
    <span class="result-num">1.</span>
    <a href="/opac/opac_details/?...&bibid=BB08815134&listnum=0..." id="img_BB08815134">
      <span class="icon-opac_book-2"></span>              <!-- 紙書籍 -->
      <!-- icon-opac_online: 電子ブック / icon-opac_serial: 雑誌 等 -->
    </a>
    <div id="book-stamp-BB08815134">…</div>                <!-- AJAXで opac_stamp 注入 -->
    <p class="result-book-title">
      <a href="...">
        書名 : 副題 / 著者責任表示
      </a>
    </p>
    <p class="result-book-publisher">出版地 : 出版者 , 2025.11. - (叢書名 ; 巻号)</p>
    <p class="book-type pull-left">
      <span class="icon-opac_book-2"></span>&nbsp;図書
      &lt;BB08815134&gt; [BD13906877]                       <!-- bibid と NCID -->
    </p>
    <div id="dtl_BB08815134" class="list_bl_block">…</div> <!-- AJAXで localhold 注入 -->
  </li>
</ul>
```

#### 抽出フィールド対応

| 抽出項目 | XPath / Regex |
|---------|---------------|
| bibid | `.//input[@name='list_bibid']/@value` |
| datatype (10=図書/19=電子ブック等) | `.//input[@name='list_datatype']/@value` |
| 順序番号 | `string(.//span[@class='result-num'])` |
| アイコン種別 | `.//span[contains(@class,'icon-opac_')]/@class` |
| タイトル(整形済み) | `string(.//p[contains(@class,'result-book-title')]/a)` |
| 詳細URL | `.//p[contains(@class,'result-book-title')]/a/@href` |
| 出版情報 | `string(.//p[contains(@class,'result-book-publisher')])` |
| 種別+IDs | `string(.//p[contains(@class,'book-type')])` (末尾の `<BBxxxx> [NCID]` を正規表現で) |

datatype コード(実測):
- `10` = 図書
- `19` = 電子ブック
- (他: 雑誌・電子ジャーナル等は別コード)

### 3.4 個別結果 `<li>` (他大学 cmode=5) [verified]

CiNii 結果は構造が異なる:

```html
<ul class="result-list">
  <li>
    <div class="row">
      <div class="col-xs-12">
        <p class="result-book-title">
          <span class="result-num">1.</span>
          <a href="/opac/opac_detail_ciniibooks/?...&ncid=BD18625252&listnum=1&totalnum=695&start=1&opkey=..." >
            タイトル
          </a>
          &nbsp;/&nbsp;責任表示
        </p>
        <p class="result-book-publisher">出版者 , 2026</p>
        <p class="result-book-datatype book-type">
          <span class="icon-opac_book-2"></span>&thinsp;図書
        </p>
      </div>
    </div>
  </li>
</ul>
```

- `list_bibid` / `list_datatype` hidden input は **無い**
- 詳細URLは `opac_detail_ciniibooks/?ncid=...`
- `<a>` の後ろに `&nbsp;/&nbsp;責任表示` がテキストとして並ぶ
- `book-type` クラスは `result-book-datatype book-type` の複合になる
- ヒット数表示は同じ `search-results-hits_num`

NCID は詳細URLの `ncid=` から抽出。

### 3.5 inline JS シードJSON [verified]

検索結果ページ内に AJAX 起動用のシード JSON が文字列リテラルとして埋まる。HTML 一覧そのものには ISBN/NCID/NBN は無いので、これを抽出するのが効率的:

```js
img_out_link_list_all('/opac/opac_imgoutlink/',
  '[[{"bibid":"BB08815134","isbn":"9784621311639","jfcd":"2","datatype":"10","thfmt":"","ncid":"BD13906877","nbn":"JP24199089"}, ...]]',
  '<csrftoken>', 'bookplus,openbd', '1');

get_local_bib_data('/opac/opac_search_localhold/',
  '[[{"bibid":"...","datatype":"10","fieldcd":"","mtid":""}, ...]]',
  '<csrftoken>', '0', '', '', 'opkey=...&start=&totalnum=N&list_disp=20&list_sort=6');

get_recommend_stamp_all('/opac/opac_stamp/',
  '[[{"bibid":"...","kind":"BBBOOK","isbn":"...","issn":""}, ...]]',
  '<csrftoken>', '0');
```

抽出パターン(Python):
```py
import re, json
m = re.search(r"img_out_link_list_all\([^,]+,\s*'(\[\[.*?\]\])'", html)
recs = json.loads(m.group(1))[0]  # → [{"bibid":..., "isbn":..., "ncid":..., "nbn":...}, ...]
```

`jfcd` の意味は不明 (1 or 2 を観測)。

---

## 4. 書誌詳細 `/opac/opac_details/` [verified]

### 4.1 リクエスト

```http
GET /opac/opac_details/?lang=0&amode=11&bibid=BB08818020
    [&reqCode=fromlist&opkey=<key>&start=1&totalnum=N&listnum=I&place=&list_disp=20&list_sort=6&cmode=0&chk_st=0&check=00000000000000000000]
Referer: https://kuline.kulib.kyoto-u.ac.jp/opac/opac_search/?lang=0
```

最小限は `lang=0&amode=11&bibid=<BIBID>` + `Referer` ヘッダだけでOK。**`Referer` を付けないと 403** ([verified])。Cookie は不要 (fresh client でも `Referer` のみで200)。

### 4.2 レスポンス構造

#### 4.2.1 タイトル領域
```html
<h2 class="book-title">
  <span class="book-title-kana">ジッセンテキ パフォーマンス ...</span>
  <br />
  <span class="book-title-trd">実践的パフォーマンスエンジニアリングによるAI高速化 = Accelerating AI through practical performance engineering / フィックスターズ</span>
  <span id="PTBL" class="ptbl_list">(<a href="...&bibid=BB08773638">ML systems</a>)</span>  <!-- 親書誌(叢書)があれば -->
</h2>
```

#### 4.2.2 書誌メタデータ表 [verified]

`<table class="book-detail-table">` 内の `<tr><th class="<CODE>"><td class="<CODE>">` ペア。

**フィールドコード(全観測):**

| コード | ラベル | 内容 |
|--------|-------|------|
| `DATATYPE` | データ種別 | `図書` / `電子ブック` / `雑誌` 等 |
| `AHDNG` | 著者標目 | 著者ごとに `<a href=opac_authority/?auid=AU...>` または `<a href=opac_search/?con1_exp=alkey&kywd1_exp=#NAME>`、後ろに `&nbsp;著者` + `<カナ読み>`。複数は `<br />` 区切り |
| `PUBLICATION` | 出版情報 | `<place> : <publisher> , <yyyy.m>` |
| `LANGUAGE` | 本文言語 | `日本語` 等 |
| `BBVT` | 別書名 | `奥付タイトル:...`, `背タイトル:...` 等プレフィクス付き |
| `PHYS` | 大きさ(形態) | `xvi, 383p : 挿図 ; 21cm` |
| `BBVOLG` | 巻冊次 | `ISBN:9784297153496 ; PRICE:3400円+税` (複数巻ならセミコロン区切り) |
| `BBNOTE` | 一般注記 | RDA表現種別/機器種別/キャリア種別、目次など自由テキスト |
| `BBSUBJECT` | 件名 | `BSH: <a>...</a>` `NDLSH: <a>...</a>` 改行区切り |
| `BBCLS` | 分類 | `NDC9: <a>007.13</a>` `NDC10: ...` `NDLC: <a>M121</a>` |
| `BBBIBID` | 書誌ID | `BB08818020` |
| `BBISBN` | ISBN | `9784297153496` (複数なら別行) |
| `NCID` | NCID | `BD14456776` |

注: ページ内で `<th class="DATATYPE">` 等が **重複** する。PC/モバイル両方の表示用に同じ行が複製されているので、抽出時は最初の出現のみ拾う or dedupeする。

#### 4.2.3 サイドバー: 他の検索サイトリンク [verified]

```html
<div class="panel panel-primary">
  <h3 class="panel-title">他の検索サイト</h3>
  <ul class="list-group">
    <li><a href="https://ci.nii.ac.jp/books/openurl/query?...rft_id=info:ncid/BD14456776">CiNii Books</a></li>
    <li><a href="https://ndlsearch.ndl.go.jp/api/openurl?rft.isbn=9784297153496">国立国会図書館サーチ</a></li>
    <li><a href="https://www.google.co.jp/search?q=9784297153496">Google</a></li>
    <li><a href="https://books.google.co.jp/books?q=9784297153496">Google Books</a></li>
    <li><a href="https://scholar.google.co.jp/scholar?q=9784297153496">Google Scholar</a></li>
  </ul>
</div>
```

パーマリンク: `https://kuline.kulib.kyoto-u.ac.jp/opac/opac_link/bibid/<bibid>` (→ 302 → opac_details)

#### 4.2.4 ナビゲーション

`<div class="book-detail-nav">` 内に:
- `<span class="nav-page">[<em>1</em>/<em>663</em>]</span>` (現在/総数)
- `<a class="nav-prev"><a class="nav-next">` (前後)
- `<a class="nav-return">` (検索結果一覧に戻る `amode=9`)

### 4.3 所蔵テーブル `library-info-table2` [verified]

`<tr class="library-info-data">` が1冊。物理本の典型行:

```html
<tr class="library-info-data">
  <td class="VOLUME">…巻次…</td>
  <td class="LOCATION">
    <a target="_blank" href="<floor_pdf>">情報学||図書室</a>   <!-- 館||場所 -->
  </td>
  <td class="CALLNO">
    <a class="no_link" onmouseover="view_barcode('007.1%7C%7CFIX%201%7C%7C3','||');">007.1||FIX 1||3</a>
  </td>
  <td class="BARCODE">
    <a href="/opac/opac_detail_book/?lang=0&amode=11&blkey=19200695&bibid=BB08818020&...">200047045652</a>
  </td>
  <td class="CONDITION">
    <span class="blstat_block_BL19200695"></span>
    <script>dispStatName('/opac/opac_blstat/','50','1','1','BL19200695',...)</script>
  </td>
  <td class="COMMENTS"></td>
  <td class="RESERVE"><a href="/opac/odr/?blkey=19200695&...">予約</a></td>
  <td class="VIRTUALSHELF">仮想書架</td>
  <td class="ILLCOPYFLG">複写取寄</td>
</tr>
```

電子ブックの場合は先頭に `<td class="setCenter ONLINE">` セル (ログインプロキシURLのボタン)、`CALLNO` は空、`CONDITION` は `オンライン` 固定。

各冊の識別子 = **`blkey`** (例: `19200695` または `BL` プレフィクス付き `BL19200695`)。

### 4.4 単冊詳細 `/opac/opac_detail_book/` [verified]

物理冊1点の追加メタ。

```http
GET /opac/opac_detail_book/?lang=0&amode=11&blkey=19200695
```

レスポンス: 約1.7K の HTML モーダル断片。フィールド:

| コード | ラベル |
|--------|-------|
| `VOLUMES` | 巻冊次等 |
| `LOCATION` | 配架場所 |
| `CALLNO` | 請求記号 |
| `BARCODE` | 資料番号 |
| `CONDITION` | 状態 |
| `COMMENT` | 利用者コメント |
| `BIBID` | 書誌ID |
| `LEDGERNO` | 原簿番号 |
| `YEAR` | 刷年 |
| `SLFDT` | 配架日 |
| `LDF` | LDF (内部コード) |

### 4.5 単冊の貸出状況 `/opac/opac_blstat/` [verified]

```http
GET /opac/opac_blstat/?lang=0&phasecd=50&hldstat=1&lkcd=1
    &blipkey=BL19200695&prlndflg=0&blcd=1&odrno=OT00477489
    &bbcd=1&contcd=&addmsg=返却期限
```

レスポンス: 通常は HTML 断片 (在架/貸出中/取置等)。観測サンプルは0バイト (= 「特に表示すべき状態なし」=在架可能と推定 [inferred])。

### 4.6 not-found レスポンス [verified]

**KULINE は不正な bibid に対しても HTTP 200 を返す**。404 ステータスコードや
明示的なエラーメッセージは返さない。識別シグナルは:

| 観測項目 | 有効な bibid | 無効な bibid |
|---------|------------|------------|
| HTTP ステータス | 200 | **200** (同じ) |
| `<span class="book-title-trd">` | 存在 | **欠落** |
| `<table class="book-detail-table">` | 存在 | 欠落 |
| `<title>` タグ | 書名込みのページタイトル | `京都大学 KULINE` (検索画面の汎用タイトル) |
| ボディ長 | 30K〜 | ~17K (検索画面シェル) |

→ ライブラリ実装の判定: `if "book-title-trd" not in r.text: raise NotFoundError`。
`opac_detail_ciniibooks/` も無効な ncid に対して同形式 (200, book-title-trd 欠落)。

---

## 5. 他大学詳細 `/opac/opac_detail_ciniibooks/` [verified]

### 5.1 リクエスト

```http
GET /opac/opac_detail_ciniibooks/?lang=0&ncid=BD18537825
   [&reqCode=fromlist&listnum=1&totalnum=4818&start=1&opkey=...&list_disp=20&list_sort=3]
```

キーは **`ncid`** (bibid は使わない)。

### 5.2 レスポンス

`<table class="book-detail-table">` のフィールドは自館より少ない:

| コード | ラベル | 内容 |
|--------|-------|------|
| `DATATYPE` | データ種別 | 図書 |
| `PUBLISHER` | 出版者 | (自館 `PUBLICATION` と分離) |
| `PUBYEAR` | 出版年 | |
| `LANGUAGE` | 本文言語 | |
| `AHDNG` | 著者標目 | 自館ほど詳細なリンクなし(CiNii典拠リンクは別) |
| `NCID` | NCID | |

(自館で出る `PHYS`/`BBVOLG`/`BBNOTE`/`BBSUBJECT`/`BBCLS`/`BBISBN`/`BBVT` は CiNii 詳細では出ない or AJAX 後埋め)

### 5.3 他大学所蔵館リスト

`<div id="hold_list">` に「大学図書館所蔵　N 件」のヘッダ、`<table class="library-info-table2">` で所蔵大学を列挙。

`<span id="ciniibooks_pt_block">` には AJAX で `/opac/opac_detail_ciniibooks/pt_list/?ncid=...&relations=...&opkey=...` が注入 (関連書誌)。

---

## 6. ファセット [verified]

### 6.1 ファセット情報取得 `/opac/opac_facet/`

検索実行後、結果一覧の左側で各タイプ並列にGET:

```http
GET /opac/opac_facet/?lang=0&opkey=<key>&facet_type=<type>
    &amode=2&cmode=0&place=&list_disp=20&list_sort=6
X-Requested-With: XMLHttpRequest
```

`facet_type` 一覧 (各タイプ独立):

| type | 内容 | 観測サイズ例(機械学習検索時) |
|------|------|------|
| `datatype` | データ種別 | 1.9K (図書 875件, 電子ブック 1824件 等) |
| `yearkey` | 出版年 | 2.9K (年別カウント) |
| `fpub` | 出版者 | 25K (出版者別カウント) |
| `txtl` | 本文言語 | 3.1K |
| `fsh` | 件名 | 24K |
| `fcls` | 分類 | 20K |
| `fauth` | 著者 | 24K |
| `dptidpl` | 部局/配架場所 | 11K |
| `uclibcd` | 所蔵館 (大学) | 0K (cmode=0では空; cmode=5の他大学検索でのみ意味) |

#### レスポンス形式 (典型)
```html
<h4 class="facet-item-head">出版者</h4>
<ul>
  <li>
    <a title="丸善出版" href="..." onclick="facet_search(this.href, '0', 'fpub', '%E4%B8%B8%E5%96%84%E5%87%BA%E7%89%88');return false;">
      丸善出版
    </a>
    &nbsp;<span class="data_cnt">(1)</span>
  </li>
  ...
</ul>
```

`datatype` だけは複数選択チェックボックス:
```html
<li>
  <label><input type="checkbox" value="10" name="facet_datatype" class="datatype"
                onclick="facet_datatype_search(...)" />
    <span title="図書">図書</span>
  </label>
  <span class="data_cnt">(875)</span>
</li>
```

### 6.2 ファセット適用 [verified]

`amode=23` で再検索する。`opkey` を継続、媒体フィルタは `fc_val=<facet_type>#@#<value>` 形式 (※ `#@#` は URL エンコード必須)。

```http
GET /opac/opac_search/?opkey=B<key>&lang=0&amode=23&place=
    &list_disp=20&list_sort=6&cmode=0
    &fc_val=datatype%23%40%2310
```

複数ファセットを同時適用するときは `fc_val` を **同名で繰り返す**:

```http
&fc_val=datatype%23%40%2310&fc_val=datatype%23%40%2319
```

ファセット種別と value 形式:

| facet_type | value 形式 | 例 |
|-----------|------------|---|
| `datatype` | 数値コード | `10`, `19` |
| `yearkey` | 西暦 | `2025` |
| `fpub` | 出版者名 (UTF-8) | `丸善出版` |
| `fsh` | 件名 | `機械学習` |
| `fcls` | 分類 | `007.13` |
| `fauth` | 著者名 | (要URLエンコード) |
| `txtl` | 言語名 | `日本語` |
| `dptidpl` | 部局 | (部局名) |
| `uclibcd` | 大学コード | (要 cmode=5) |

実測ヒット減少例(検索 `kywd=機械学習` で886件 → ファセット適用):
- `fc_val=datatype#@#10` → 527件
- `fc_val=yearkey#@#2025` → 59件
- `fc_val=fpub#@#丸善出版` → 8件
- `fc_val=datatype#@#10&fc_val=datatype#@#19` → 829件
- `fc_val=fsh#@#機械学習` → 454件

JS 由来の参考実装(media/js/opac_list.js):
```js
function facet_search(url, seltab, facet_item, value) {
    url = url + "&fc_val=" + facet_item + encodeURIComponent("#@#") + value;
    url = url + "&cmode=" + seltab;
    location.href=url;
}
```

---

## 7. 所蔵情報 AJAX `/opac/opac_search_localhold/` [verified]

### 7.1 リクエスト (POST `application/x-www-form-urlencoded`)

```http
POST /opac/opac_search_localhold/
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
X-Requested-With: XMLHttpRequest
X-CSRFToken: <csrftoken>
Cookie: csrftoken=...; sessionid=...
Referer: <検索結果ページのURL>

csrfmiddlewaretoken=<token>&lang=0&place=&mdptid=
&q_param=opkey%3D<key>%26start%3D%26totalnum%3D2%26list_disp%3D20%26list_sort%3D6
&rec=%5B%7B%22bibid%22%3A%22BB08818020%22%2C%22datatype%22%3A%2210%22%2C%22fieldcd%22%3A%22%22%2C%22mtid%22%3A%22%22%7D%2C...%5D
```

| パラメータ | 内容 |
|-----------|------|
| `csrfmiddlewaretoken` | フォーム中のCSRFトークン |
| `lang` | `0`/`1` |
| `place` | 配架場所フィルタ (空可) |
| `mdptid` | 部局フィルタ (空可) |
| `q_param` | URL エンコードされた検索コンテキスト (`opkey=…&start=…&totalnum=…&list_disp=…&list_sort=…`) |
| `rec` | JSON 配列 (URL エンコード): `[{"bibid":"…","datatype":"10","fieldcd":"","mtid":""}, …]` |

電子ブックの場合 `fieldcd=ONLINE`, `mtid=<ssj/etc>`。

### 7.2 レスポンス [verified]

`application/json` で配列を返す:

```json
[
  {"bibid": "BB08818020", "res": "<HTML フラグメント (所蔵テーブル) >"},
  {"bibid": "EB13920383", "res": "<HTML フラグメント (オンライン版) >"}
]
```

`res` 内HTMLは `<table class="table table-bordered">` で物理本/オンライン本のテーブル。各行 `<tr class="list_bl_item_tr">` に `VOLUME/LOCATION/CALLNO/BARCODE/CONDITION/COMMENTS` (電子ブックは先頭に `ONLINE`)。

冒頭に `<p class="holding-num">所蔵件数: N件</p>`。

---

## 8. その他のAJAXエンドポイント

### 8.1 `/opac/opac_suggest/` [verified]

```http
GET /opac/opac_suggest/?q_word=<keyword>
X-Requested-With: XMLHttpRequest
```

レスポンス: `Content-Type: text/javascript`、JSON配列。

```json
["日本機械学会","日本機械工業連合会","機械学習","機械工業","日本機械学會論文集","日本建設機械化協会","機械工業基礎調査報告書","機械振興協会経済研究所","農業機械器具","日本機械学會誌"]
```

サジェストなしは `[]`。

### 8.2 `/opac/opac_spellcheck/` [verified]

```http
GET /opac/opac_spellcheck/?lang=0&opkey=<key>&srvce=0&tikey=
X-Requested-With: XMLHttpRequest
```

レスポンス: HTML 断片。候補がある場合:

```html
<p id="opac_spellcheck" class="spellcheck">
  もしかして：
  <a href="/opac/opac_search/?reqCode=fromsrch&lang=0&amode=2&smode=0&kywd=python"><em>python</em></a>,&nbsp;
  <a href="/opac/opac_search/?...&kywd=pitson"><em>pitson</em></a>,&nbsp;
  <a href="/opac/opac_search/?...&kywd=oithona"><em>oithona</em></a>
</p>
```

候補なし: ほぼ空 (4バイトの空白のみ)。

### 8.3 `/opac/opac_imgoutlink/` [verified]

書影の存在チェック(外部の openBD / BookPlus 等にあるか)。

#### POST (一括)
```
POST /opac/opac_imgoutlink/
csrfmiddlewaretoken=<token>&size=1&img_param=bookplus,openbd
&isbn_list=[URLエンコードされた JSON]
```

`isbn_list` の JSON 例:
```json
[{"bibid":"BB08818020","isbn":"9784297153496","jfcd":"2",
  "datatype":"10","thfmt":"","ncid":"BD14456776","nbn":"JP24215802"}]
```

レスポンス: `application/json`
```json
{"img_list": [{"img_url": ""}]}
```
書影が見つからない場合 `img_url` は空文字。

#### GET (単発)
```
GET /opac/opac_imgoutlink/?isbn=...&ncid=...&nbn=...&jfcd=1&datatype=10&img_param=bookplus,openbd&size=1&lang=0&bibid=...
```
レスポンス: JSON
```json
{"link_url": null}
```
あれば `link_url` に URL 文字列。

### 8.4 `/opac/opac_stamp/` [verified]

レコメンドスタンプ(「貸出ランキング」等の小さい飾り)取得。

#### POST
```
POST /opac/opac_stamp/
csrfmiddlewaretoken=<token>&lang=0
&bibid_list=[URLエンコードされた JSON: {"bibid":"…","kind":"BBBOOK","isbn":"…","issn":""}]
```

レスポンス: JSON
```json
{"stamp_list": [{"bibid": "BB08818020", "stamp_data": []}]}
```

`stamp_data` が空配列のときはスタンプなし。

### 8.5 `/opac/opac_openbdinfo/` [verified]

```
GET /opac/opac_openbdinfo/?isbn=<isbn>&bibid=<bibid>
```
レスポンス: HTML フラグメント (openBD由来の目次/あらすじテキスト)、無ければ "目次・あらすじの電子情報はありません。"。

### 8.6 `/opac/opac_bookplusinfo/` [verified]

```
GET /opac/opac_bookplusinfo/?isbn=<isbn>&bibid=<bibid>&lang=0
```
レスポンス: HTML フラグメント。BookPlus のあらすじ・目次:

```
日外アソシエーツ『BOOKデータASPサービス』より

実践的パフォーマンスエンジニアリングによるＡＩ高速化
(出典：日外アソシエーツ『BookPlus』より)

[あらすじ]
性能を制する者が、ＡＩを制す。

[目次]
第１章　パフォーマンスエンジニアリング概論
第２章　まずはパフォーマンスを計測する
...
```

### 8.7 `/opac/opac_bookplusimg/` [verified ヘッダのみ]

```
GET /opac/opac_bookplusimg/?isbn=...&ncid=...&nbn=...&mode=disp&lang=0
```
書影のプレビュー HTML ページ。

### 8.8 `/opac/opac_360link/` [har]

Ex Libris 360Link 連携。
```
GET /opac/opac_360link/?lang=0&datatype=0&isbn=...&ncid=...&linkdatatype=10&bibid=...
```
外部 DB リンクまたは 404 を返す。

### 8.9 `/opac/opac_authority/` [verified]

```
GET /opac/opac_authority/?lang=0&amode=11&auid=AU00950057
```

著者標目典拠の詳細(著者ID、別名、関連著者、その著者の著作一覧へのリンク)。約 20K の HTML。

### 8.10 `/opac/opac_tag/detail/` [har]

タグ機能。`datakey=BB<bibid>` 形式。

---

## 9. 識別子体系まとめ [verified]

| ID | 用途 | 形式 | 取得元 |
|----|------|------|--------|
| `bibid` | KULINE 書誌レコード ID | `BB`+8桁(図書) / `EB`+8桁(電子ブック) / `SB`+(雑誌?) / 他 | 結果 `list_bibid`, 詳細クエリ, インラインJSONシード |
| `ncid` | NACSIS-CAT ID (CiNii Books) | `BA`/`BB`/`BC`/`BD`/`BN`+8桁 | 詳細 `NCID`, 結果末尾の `[NCID]`, インラインJSONシード, CiNii URL |
| `nbn` | 全国書誌番号 | `JPxxxxxx` 等 | 検索条件, インラインJSONシード |
| `isbn` | ISBN | 10/13桁 | 詳細 `BBISBN`, インラインJSONシード |
| `issn` | ISSN | 8桁 | 検索条件 |
| `blkey`/`blipkey` | 個別冊(コピー)ID | 8桁数字 (POST URL では `BL` プレフィクス付き版もあり) | 所蔵表 `BARCODE` リンク, blstat |
| `auid` | 著者標目ID | `AU`+8桁 | 著者リンク, opac_authority |
| `opkey` | 検索セッションキー | `B`+14桁 | サーバが `amode=2` で発行 |
| `mtid` | 電子書誌マスタID | 例 `ssj0000074569` | 電子ブック localhold seed |
| `OT...` | 注文番号? | `OT`+8桁 | blstat の `odrno` |

---

## 10. 文字エンコード・ヘッダ要点 [verified]

- リクエスト/レスポンス全て **UTF-8** (Content-Type で `charset=utf-8` 明示)
- 日本語クエリは UTF-8 → URL エンコード
- `Accept-Language` を変えても UI言語切替には影響しない (`lang` クエリパラメータが支配的)
- gzip 受け入れ可 (`Content-Encoding: gzip`)
- 多くの応答が `Cache-Control: no-cache, no-store, must-revalidate` → ローカル/Proxy キャッシュ不可

---

## 11. ライブラリ実装のための要点 (cheat sheet)

### 11.0 設計方針: GET系はプリフライト不要 [verified]

KULINE の検索系API(GETのみ)は **完全 stateless** であることが実通信で確認済み。
ライブラリは以下の通り **lazy CSRF** で組むのが最もコスト効率が良い:

- 検索・ページング・ファセット・詳細表示・サジェスト等は warmup ゼロで即発
- POST系(所蔵情報・書影解決・スタンプ)を呼ぶ瞬間に **初回1回だけ** warmup
- 同一Client内では CSRF キャッシュを再利用

```py
class KulineClient:
    BASE = "https://kuline.kulib.kyoto-u.ac.jp"
    REFERER = f"{BASE}/opac/opac_search/?lang=0"

    def __init__(self):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")           # KULINEの古cipher対応
        self._http = httpx.Client(
            base_url=self.BASE, verify=ctx, follow_redirects=True, timeout=30,
            headers={
                "User-Agent": "kuopac/0.1",
                "Referer": self.REFERER,                 # opac_details/の403回避
                "Accept-Language": "ja",
            },
        )
        self._csrf: str | None = None                     # POST 初回まで None

    # ---- GET系: warmup 不要 ----

    def search(self, **params) -> SearchResult: ...
    def page(self, opkey: str, start: int, **params) -> SearchResult: ...
    def facet_apply(self, opkey: str, fc_val: list[str], **params): ...
    def detail(self, bibid: str) -> Book: ...
    def cinii_detail(self, ncid: str) -> Book: ...
    def suggest(self, q: str) -> list[str]: ...
    def facet_info(self, opkey: str, facet_type: str): ...

    # ---- POST系: 初回だけ warm ----

    def _ensure_csrf(self) -> str:
        if self._csrf is None:
            r = self._http.get("/opac/opac_search/", params={"lang": "0"})
            m = re.search(
                r"name=['\"]csrfmiddlewaretoken['\"] value=['\"]([^'\"]+)['\"]",
                r.text,
            )
            self._csrf = m.group(1)
        return self._csrf

    def holdings(self, bibids: list[tuple[str, str]]) -> list[Holding]:
        csrf = self._ensure_csrf()
        rec = json.dumps([{"bibid": b, "datatype": dt, "fieldcd": "", "mtid": ""}
                          for b, dt in bibids], ensure_ascii=False)
        r = self._http.post("/opac/opac_search_localhold/", data={
            "csrfmiddlewaretoken": csrf, "lang": "0", "place": "", "mdptid": "",
            "q_param": f"opkey=&start=&totalnum={len(bibids)}&list_disp=20&list_sort=6",
            "rec": rec,
        }, headers={"X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf})
        return [parse_holding(item) for item in r.json()]
```

### 11.1 並列化の指針

GET系はサーバ側 opkey キャッシュにアクセスする以外の状態を持たないので、`asyncio`+`httpx.AsyncClient` か `concurrent.futures.ThreadPoolExecutor` で並列化が安全:

- **検索→詳細展開**: 検索結果の bibid 一覧を並列で `opac_details/` に投げてよい
- **ファセット情報**: 9種類を並列に `opac_facet/` で取得(ブラウザ実装と同じ挙動)
- **書影解決**: 複数 bibid を `opac_imgoutlink/` POST 1回で済むので並列化不要

レート制御は意外に厳しくない印象だが、礼節として 5並列以下 + 0.2〜0.5秒の jitter を推奨。

### 11.2 検索の最小呼び出し
```py
# 簡易
client.get("/opac/opac_search/", params={"lang":"0","amode":"2","cmode":"0","smode":"0","kywd":"機械学習"})

# 詳細
client.get("/opac/opac_search/", params={
    "lang":"0","amode":"2","cmode":"0","smode":"1",
    "kywd1_exp":"Python","con1_exp":"titlekey_ja",
    "file_exp":["1"],"dpmc_exp":"all",
    "sort_exp":"6","disp_exp":"20",
})
```

### 11.3 ページング
1ページ目から得た `opkey` を再利用、`amode=22`、`start=21,41,61,...` (1始まり)。

### 11.4 ファセット適用
`amode=23`, `fc_val=<type>#@#<value>` (反復可、`#@#` は URLエンコード必須)。`opkey` 継続。

### 11.5 検索結果から書誌詳細を引く最短ルート
- HTML から `bibid`, `result-book-title/a/@href` を取り、そのURLでGETするのが最速 (`opkey`/`listnum`/`totalnum` 込み)
- インラインJSONシードから `isbn`/`ncid`/`nbn` を併せて拾える

### 11.6 所蔵情報
HTML一覧は概要のみ。AJAX POST `/opac/opac_search_localhold/` で一括取得(複数bibid可)。

### 11.7 注意 [verified]
- ヒット数表示は `1,122件` のようにカンマ区切り — 整数化時はカンマ除去
- 詳細ページのフィールド行は PC/モバイル 両用に **重複出力**。最初の `<tr>` 出現のみ使う
- 検索結果リスト `<li>` の `book-type` に紛れて `<` `>` で囲まれた bibid と `[` `]` の NCID が出る:`<BB08818020> [BD14456776]`
- ファセットの `uclibcd` (所蔵大学) は CiNii検索 (`cmode=5`) 時のみ意味あり、cmode=0 では空応答
- `opac_details/` を bare で叩くと **403** ([verified])。`Referer` ヘッダを付けるだけで回避できる(Cookieは不要)
- `txtl_ciniibooks` / `txtl_exp` の言語選択肢は **460+** あるので、ライブラリでは数値コードのまま受け渡し推奨
- HTMLの `csrfmiddlewaretoken` は **シングルクォート** で出るので抽出正規表現は `['\"]` 両対応にする
- `opkey` はサーバ側キャッシュ(おそらく memcache)で生成元の Cookie/セッションに紐づかない — ライブラリ利用者にそのまま渡しても問題ない(SearchResult.opkey をプロパティ公開してよい)

### 11.8 入力検証(発見した制約)
- `kywd` の長さ上限: input maxlength=256 (UI側のみ。サーバはより許容するかも)
- `year1_exp`/`year2_exp`: 4桁
- `auid_ciniibooks`/`utid_ciniibooks` 等の ID 系は maxlength=20

---

## 12. 未確認/今後の調査候補

- `opac_360link/` の実レスポンス形式 (今回観測サンプルが空)
- `opac_blstat/` の貸出中/取置時のHTML (今回は在架可能のみ観測)
- 雑誌(`SB...`?)・学位論文(`TB...`?)・貴重資料(`KB...`?) の bibid プレフィクス体系
- ログイン後の MyOPAC エンドポイント(`/opac/myopac/...`)
- ファイル出力 (`/opac/opac_fileout/`) の CSV/RIS フォーマット
- ヒット件数の上限 (`disp_exp=500` 以上の挙動)
- 同時セッション数の制限
- レート制限の有無 (現状 1.5秒/req では問題なし)
