# smallx

X の指定アカウントの投稿を、**原文のまま**読むための静的サイトです。どのPC・スマホのブラウザからでも見られます。

- 公開URL: https://tomochi3.github.io/smallx/
- サーバー不要・無料: **GitHub Actions** が毎朝 7:07（日本時間）に X から新しい投稿を取得し、ページを作り直して commit します。**GitHub Pages** がそれを公開します。

```
GitHub Actions（毎朝）→ X（Cookie または 公式API）→ data/posts/*.json に追記 → HTML を作り直す → commit → GitHub Pages
```

## 取得方法

[`xdigest.toml`](xdigest.toml) の `source` で選びます。

| `source` | 方法 | 費用 | 注意 |
|---|---|---|---|
| `cookie`（今の設定） | ブラウザでログイン中の X の Cookie を使い、Web版と同じ方法で読む（[twscrape](https://github.com/vladkens/twscrape)） | 無料 | **X の規約上は非公式な方法**。Cookie のアカウントが制限・凍結される可能性あり。X の仕様変更で突然動かなくなることがある |
| `api` | X 公式 API | 従量課金（他人の投稿1件 約$0.005） | 安定。Developer Console でクレジット購入が必要 |

## 初期設定（1回だけ）: cookie の場合

1. **Cookie を取り出す**（パスワードは不要）
   - 別のアカウント（サブアカウント）を使うのがおすすめです。制限されても本アカウントに影響しません
   - Safari の**プライベートウインドウ**で <https://x.com> にログイン
   - 開発 → Webインスペクタを表示 → ストレージ → Cookie → `https://x.com`
     （「開発」メニューがなければ Safari の設定 → 詳細 →「Web開発者用の機能を表示」をオン）
   - `auth_token` と `ct0` の値をコピー
   - **ログアウトせずに**プライベートウインドウを閉じる（ログアウトすると Cookie が無効になります）
2. **Secrets に登録**: このリポジトリの Settings → Secrets and variables → Actions → New repository secret
   - 名前 `X_COOKIES`、値 `auth_token=コピーした値; ct0=コピーした値`
   - `NTFY_TOPIC`（任意）: 新しい投稿があったらスマホの [ntfy](https://ntfy.sh/) アプリに通知
3. **Pages を有効化**（済み）: Settings → Pages → Branch: `main` / `/ (root)`
4. **初回実行**: Actions タブ → 「Update posts」→ 「Run workflow」

Cookie の値は、アカウントにログインできてしまう情報です。Secrets 以外（チャット・ファイル・このリポジトリ）には絶対に書かないでください。
ログインし直したり、X から「ログアウトされた」場合は、1 からやり直して `X_COOKIES` を上書きします。

### api の場合

`xdigest.toml` を `source = "api"` にして、Developer Console の **Project に接続した App** の Bearer Token を `X_BEARER_TOKEN` に登録します。クレジットが必要です。

## 読むアカウントを変える

[`xdigest.toml`](xdigest.toml) の `accounts` を編集して commit するだけです（GitHub のWeb画面で編集できます）。
新しく追加したアカウントは、次の実行で直近24時間分から取得します。

## ページ

| ファイル | 中身 |
|---|---|
| `index.html` | 最新7日分（日付ごと） |
| `u/<アカウント>.html` | アカウント別・最新300件 |
| `m/YYYY-MM.html` | 月別アーカイブ |
| `data/posts/YYYY-MM.json` | 投稿データ（ここから毎回ページを作る） |
| `data/state.json` | 前回どこまで取得したか |

**HTML は自動生成です。手で編集しても次回の更新で上書きされます。** 見た目は [`xdigest/site.py`](xdigest/site.py) で変えられます。

## うまく動かないとき

- Actions タブで失敗した実行のログを見ます。エラー（トークン切れ・クレジット切れなど）があっても、取れた分は保存してから失敗になります
- cookie: 「取得できませんでした」が続く → Cookie の期限切れ・ログアウト・アカウント制限のどれか。Cookie を取り直して `X_COOKIES` を上書き。
  GitHub のサーバーからのアクセスを X が拒否するようになった場合は、自宅の Mac で `python -m xdigest` を動かして push する方法に切り替えます
- cookie: 全く動かなくなった → X の仕様変更の可能性。`requirements.txt` の twscrape を新しい版に上げる
- api: `402` / `403` はクレジット不足・Project 未接続、`401` はトークン違い
- 公開リポジトリの定期実行は、60日間リポジトリに動きがないと止まります。毎日の更新 commit があるので通常は止まりませんが、止まったら Actions タブから再度有効にしてください

## 開発

```bash
python -m pip install pytest
python -m pytest -q
python -m xdigest --build-only      # X API を呼ばずにページだけ作り直す
```

## 注意

公開リポジトリなので、URLを知っていれば誰でも見られます。検索エンジンには載らないよう `noindex` と `robots.txt` を入れています。
他人の投稿をそのまま載せているので、X の規約や投稿者の著作権を考えて、個人用にとどめてURLは広めないでください。各投稿の著作権は投稿者にあります。
