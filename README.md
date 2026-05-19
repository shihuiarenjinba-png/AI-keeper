# AI Keeper

AIアカウントの7日制限を管理するGitHub Pages向けの静的UIです。

## 使い方

1. GitHub Pagesでこのリポジトリを公開します。
2. 画面の「接続設定」でGitHub owner、repo、branch、fine-grained tokenを入力します。
3. 「データファイル初期化」を押すと、`data/accounts.json`、`data/events.json`、`data/settings.json` が作成されます。
4. アカウントを追加し、「制限開始」を押すと7日後の解除予定を自動で記録します。

## 状態

- 未制限: まだ制限開始されていない、または解除確定済み
- 制限中: 7日以内
- 自動解除済み: 7日を過ぎており、表示上は利用可能。必要なら「解除確定」で状態を整理できます。

## Token

GitHub fine-grained personal access tokenを使ってください。

- Repository access: このrepoのみ
- Repository permissions: Contents Read and write

tokenやメールアドレスはソースコードに埋め込まないでください。
