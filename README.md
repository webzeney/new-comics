# new-comics

漫画新刊JP（https://new-comics.jp/）のデータ取得・ページ生成スクリプト。

漫画の新刊発売日を出版社の公開情報から集め、カレンダー形式の静的ページとして公開する。実行はすべて GitHub Actions で行う。

## 構成

```
src/newcomics/        取得・データベース・正規化
src/newcomics/fetchers/  出版社ごとの取得処理
db/newcomics.sqlite   データベース（Actions が更新してコミットする）
tests/                単体テスト（HTML は構造だけを再現した最小のサンプル）
.github/workflows/    定期実行
```

## 手元での実行

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 -m unittest discover -s tests
```

出版社サイトへの取得は手元の PC からは行わない。取得は GitHub Actions の「出版社サイトの取得」ワークフローで実行する。

## 取得のルール

- robots.txt に従い、同じサイトへのリクエストは 3 秒以上あける
- 取り込むのは書名・巻数・著者・出版社・レーベル・発売日・価格・ISBN などの事実情報だけ。書影・あらすじ・紹介文は取り込まない
- 成人向けはページ生成の段階で除外する（`labels.is_adult`）
