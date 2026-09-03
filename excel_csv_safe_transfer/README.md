# CSV → Excel 安全転記システム

既存Excelの**数式を変更せず**、許可した入力列へCSVの値だけを追記するWindows向けツールです。

## 安全設計

- 原本Excelへ直接書き込まず、まずバックアップと一時コピーを作成
- 転記先セルに数式があれば即停止
- 転記前後・保存後に全シートの数式を比較
- 既存値への上書きを禁止
- 行不足時に自動で行挿入せず停止
- CSV内とExcel既存データの重複キーを検出
- CSV・Excel・設定JSONをSHA-256で再確認
- Excelイベント、外部リンク更新、自動マクロ実行を抑制
- 成功・失敗とも処理ログを保存

## 前提

- Windows
- Microsoft Excel がインストール済み
- Python 3
- pywin32

初回は `setup.bat`、通常起動は `run.bat` を使用します。

## 操作

1. CSVファイルを選択
2. 転記先Excelを選択
3. 設定JSONを選択
4. `① 事前検査`
5. 内容を確認
6. `② 転記実行`

## 年度管理

`fiscal_year_start_month: 4` の場合、2026/04/01～2027/03/31を2026年度として扱います。
CSV内に複数年度が混在している場合は停止します。

## 翌年度のレイアウト変更

年度ごとに設定JSONを分けることで、コード本体を変えずに転記先列を変更できます。

例:

```json
{
  "sheet_name": "入力",
  "data_start_row": 5,
  "data_end_row": 5000,
  "date_csv_header": "日付",
  "date_excel_column": "A",
  "key_csv_headers": ["日付", "伝票番号"],
  "fiscal_year_start_month": 4,
  "workbook_fiscal_year_cell": "B2",
  "columns": [
    {"csv_header": "日付", "excel_column": "A", "type": "date", "required": true},
    {"csv_header": "伝票番号", "excel_column": "B", "type": "text", "required": true},
    {"csv_header": "数量", "excel_column": "C", "type": "number", "required": true},
    {"csv_header": "金額", "excel_column": "D", "type": "number", "required": true}
  ]
}
```

## 数式保護について

最も安全なのは、Excel側に年間分の入力行と数式列をあらかじめ用意しておく運用です。
このツールは `columns` に指定した列だけへ値を書き込み、それ以外の列には触れません。
さらに全数式を転記前後で照合し、1セルでも追加・削除・変更があれば原本Excelを更新しません。

## 注意

- 15桁を超えるIDは `number` ではなく `text` にしてください。
- パスワード付きExcel、特殊アドイン、共同編集、OneDrive/SharePoint同期中のファイルは本番前に追加検証してください。
- 本番導入前に、必ず実ファイルのコピーで4月～直近月まで通しテストしてください。

## ファイル構成

```text
excel_csv_safe_transfer/
├─ app.py
├─ config_example.json
├─ requirements.txt
├─ setup.bat
├─ run.bat
├─ README.md
└─ transfer/
   ├─ __init__.py
   ├─ config.py
   ├─ csv_loader.py
   ├─ excel_com.py
   └─ service.py
```
