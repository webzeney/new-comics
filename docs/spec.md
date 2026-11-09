# 漫画新刊JP の現在の仕様（2026-11-09 時点）

運営のルール（何をしてよいか・何をしないか）は CLAUDE.md、HTML/CSS の書き方は docs/coding-rules.md に書く。
このファイルには、いま動いている仕組みを1か所にまとめる。仕様を変えたら、ここも直す。

## 全体の流れ

1. 毎晩、GitHub Actions の「出版社サイトの取得」（fetch.yml）が非公開リポジトリ new-comics-data のデータベースを取り出し、次の順に更新して保存する。
   1. 単体テスト
   2. 出版社サイトと楽天ブックスからの取得（`newcomics.fetch`）。ISBN のない重複の整理（`store.merge_isbnless_duplicates`・`store.merge_isbnless_by_title`）もここで行う
   3. Amazon の照らし合わせ（`newcomics.amazonlink`）：ISBN-10 の商品ページの確認 → 書影のアドレスの取り直し → ISBN のない本の紙の本 → Kindle版
   4. 楽天の書影の補完（`newcomics.rakutencover`）
   5. 楽天Kobo の照らし合わせ（`newcomics.kobo`）
   6. アナリティクスの読み込み（`newcomics.ga`、よく見られている本）
   7. 件数の集計 → データベースの保存 → ページ生成の確認
   - 3〜6 は失敗しても先へ進む（時間の上限あり）。失敗したときは注意（warning）を出す
2. 取得が終わると「サイトの転送」（deploy.yml）がページを生成し、FTPS で差分だけを転送する。
   - 取得の実行が失敗したときは、失敗したのが出版社の取得（と 3〜6）だけのときに限って転送する
3. 毎朝7時ごろ、「X への投稿」（x-post.yml）がその日発売の新刊を @newcomics_jp に投稿する（`newcomics.xpost`）。

## ページ

`newcomics.build` が静的な .html を書き出す。head の共通部分・サイドメニュー・フッターは `assets/partials/` に書き出し、各ページは PHP の readfile で読み込む。
CSS・JS のアドレスには中身から作った印（`?v=…`）を付け、転送のあとに古いファイルが残らないようにしている。

| ページ | 場所 | 内容 |
|---|---|---|
| トップ | `/` | 今日・明日発売の新刊、発売日の変更、特集 |
| カレンダー | `/calendar/`、`/calendar/YYYY/MM/` | 月ごとの発売日カレンダー。今月のページの正規 URL は `/calendar/` |
| 日ごと | `/date/YYYY-MM-DD/` | その日発売の新刊（出版社別） |
| 書籍 | `/book/{ISBN か b+番号}/` | 本の詳細・購入ボタン・電子書籍・既刊・同じ作者の作品 |
| 作品 | `/series/{番号}/` | 既刊一覧。巻が1冊だけの作品は noindex |
| 出版社・レーベル・タグ・著者 | `/publisher/…`、`/label/…`、`/tag/…`、`/author/…` | 3か月分の発売予定と、それより前の本（最大30冊） |
| お気に入り・検索 | `/favorites/`、`/search/` | ブラウザの中で表示する（検索は `search/index.json` を使う） |
| 発売日の変更・決定 | `/updates/` | |
| 運営者情報など | `/about/` ほか | お問い合わせは PHP（受信内容はサーバーにだけ保存） |
| そのほか | `sitemap.xml`、`llms.txt`、作品ごとの RSS と .ics | |

## 書影とリンク

- 書影：一覧などは楽天の書影。書籍詳細ページのメインの書影だけ、Amazon の書影（取得から24時間以内）があれば Amazon、なければ楽天（CLAUDE.md）
- 書影のリンク先：書籍詳細ページのメインの書影は、その書影の書店の商品ページ。ほかの書影はその本の詳細ページ
- 購入ボタン（Amazon・楽天ブックス・セブンネット）
  - Amazon：ISBN-10 の商品ページ。Amazon に ISBN-10 のページがない本は、ISBN で見つけた ASIN。ISBN のない本は、照らし合わせで見つけた ASIN。どれもなければ検索結果のページ（毎晩探し直し、見つかったら商品ページに変わる）
  - 楽天ブックス：楽天の商品ページ。なければ楽天の検索結果のページ（楽天アフィリエイトのリンクにする）
  - セブンネット：ISBN の商品ページ。ISBN がなければ検索結果のページ。以前の確認でセブンネットにないと分かった本（`books.seven_ok = 0`）にはボタンを出さない
- 電子書籍のボタン（Kindle・楽天Kobo）：電子版ありの本に出す。電子版の有無が分からない本は、見つかったストアだけ出す
- 「まとめてAmazonのカートへ」：Amazon のボタンと同じ ASIN を使う

## データベースのおもな項目（books）

| 項目 | 内容 | 付ける処理 |
|---|---|---|
| `isbn13`・書名・巻数・著者・発売日・価格・電子版の有無 | 出版社サイト（または楽天）の事実情報 | fetch |
| `image_url`・`rakuten_url`・`title_kana` | 楽天の書影・商品ページ・読み仮名（読み仮名は検索だけに使う） | fetch・rakutencover |
| `asin`・`amazon_isbn_ok` | Amazon の紙の本の ASIN と、ISBN-10 の商品ページがあるか | amazonlink |
| `amazon_image_url`・`amazon_image_at` | Amazon の書影のアドレスと取得日時（24時間を過ぎたものは消す） | amazonlink |
| `kindle_asin`・`kobo_url` | Kindle版・楽天Kobo版 | amazonlink・kobo |

使っていない列（`seven_checked_at`・`rakuten_code`・`series.latest_volume` など）は、データベースの作り直しを避けるため残している。

## 手動で動かすワークフロー

| ワークフロー | 用途 |
|---|---|
| サイトの転送（deploy.yml、mode=check/deploy） | 手動の転送 |
| Amazon の商品ページの確認（amazon-isbn.yml） | ISBN の分かる本の商品ページの確認を全件で行う |
| Amazon Creators API の確認（amazon-probe.yml） | ASIN・ISBN・書名で Amazon を調べる |
| 楽天で本を調べる（rakuten-lookup.yml） | 特集記事用に、楽天ブックス・Kobo を ISBN か書名で調べる |
| 楽天ブックスの登録状況の調査（rakuten-probe.yml） | 出版社ごとの判型・ジャンルの調査（結果は成果物） |
| 書籍データの確認（inspect-book.yml） | データベースの本を書名で見る。`--dups` で重複を数える |
| サイトの表示確認（site-check.yml） | 本番の表示・証明書・見えてはいけないファイルの確認 |
| 表示の確認用の画面写真（preview-shot.yml） | 本番のデータでページを作って画面写真を撮る |
| X への投稿（x-post.yml） | 日付を指定した投稿・確認だけの実行 |

## 時間と回数の決まり

- 出版社サイト：同じホストへ3秒以上あける（robots.txt に従う）
- 楽天・Amazon：1秒に1回以下
- 夜間の Amazon の照らし合わせは30分まで（商品ページの確認6分・書影15分を含む）、楽天の書影の補完15分、楽天Kobo 12分
