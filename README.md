# smallx

X の指定アカウントの投稿を、**原文のまま**読むための静的サイトです。どのPC・スマホのブラウザからでも見られます。

- 公開URL: https://tomochi3.github.io/smallx/
- サーバー不要: **GitHub Actions** が毎朝 7:07（日本時間）に X API から新しい投稿を取得し、ページを作り直して commit します。**GitHub Pages** がそれを公開します。

```
GitHub Actions（毎朝）→ X API → data/posts/*.json に追記 → HTML を作り直す → commit → GitHub Pages
```

## 初期設定（1回だけ）

1. **X API のトークン**: <https://developer.x.com> でアプリを作り、クレジットを購入して **Bearer Token** をコピー
2. **Secrets に登録**: このリポジトリの Settings → Secrets and variables → Actions → New repository secret
   - `X_BEARER_TOKEN`: 1 のトークン（必須）
   - `NTFY_TOPIC`: 新しい投稿があったらスマホの [ntfy](https://ntfy.sh/) アプリに通知したいときだけ。推測されにくい名前に
3. **Pages を有効化**: Settings → Pages → Source: `Deploy from a branch`、Branch: `main` / `/ (root)` → Save
4. **初回実行**: Actions タブ → 「Update posts」→ 「Run workflow」。数分後に公開URLで確認

## 読むアカウントを変える

[`xdigest.toml`](xdigest.toml) の `accounts` を編集して commit するだけです（GitHub のWeb画面で編集できます）。
新しく追加したアカウントは、次の実行で直近24時間分から取得します。

## 料金

GitHub Actions・Pages は公開リポジトリなら無料です。かかるのは **X API の従量課金だけ**で、他人の投稿1件あたり約 $0.005（5アカウント × 1日10投稿で月 $7.5 前後）。
前回の続き（`data/state.json` の `since_id`）からだけ取得するので、同じ投稿に二重に払いません。`max_posts_per_account` が1回あたりの上限です。
単価は変わることがあるので developer console で確認し、使いすぎ防止の上限額も設定してください。

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
- `402` / `403`: X API のクレジット不足・権限。`401`: トークンが違う
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
