# CSV → Excel 安全転記システム

ローカルPCで使う **Streamlit UI** 版です。

ログイン、アカウント接続、クラウド連携はありません。  
ブラウザはローカルUIを表示するためだけに使います。

## 操作

通常の利用者が触るのは次の3ステップだけです。

1. CSVを選択
2. 元Excelを選択
3. 事前チェック → 転記済みExcelを作成 → 保存

元Excelは**上書きしません**。  
転記後のExcelは別ファイルとしてダウンロードします。

## 対応環境

- Windows
- macOS
- Linux
- Python 3.10+
- ブラウザ（Streamlitのローカル画面表示用）

Microsoft Excel本体は処理時には不要です。

対応ファイル:

- `.xlsx`
- `.xlsm`（VBA保持モード。特殊機能は実ファイル検証推奨）
- `.csv`

`.xls` / `.xlsb` は対象外です。

## 起動

### Windows

初回:

```text
setup.bat
```

通常:

```text
run.bat
```

### macOS

初回:

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

または `setup_local.command` → `run_local.command` を利用できます。

起動すると通常はブラウザでローカル画面が開きます。

## UI方針

メイン画面には以下だけを表示します。

- CSVアップロード
- Excelアップロード
- 事前チェック
- 転記済みExcel作成
- Excel保存

年度変更などで列位置が変わった場合の設定JSONは
**「詳細設定」内に隠しています**。

アカウント、ログイン、接続先、クラウド認証などはありません。

## 数式保護

転記前に全シートの数式を取得し、次のタイミングで比較します。

1. 転記直後
2. 保存後にExcelファイルを再読込した後

1セルでも数式の追加・削除・変更を検出した場合は
完成ファイルを出力しません。

さらに、転記対象セルに既存の値または数式がある場合も停止します。

## 追記ルール

`config_example.json` の設定を利用します。

主な設定:

```json
{
  "sheet_name": "入力",
  "data_start_row": 5,
  "data_end_row": 5000,
  "date_csv_header": "日付",
  "date_excel_column": "A",
  "key_csv_headers": ["日付", "伝票番号"],
  "fiscal_year_start_month": 4
}
```

4月開始の場合:

- 2026/04/01 ～ 2027/03/31 → 2026年度

Excel最終日より前の日付を含むCSVは、重複・上書き防止のため停止します。

## 翌年度にレイアウトが変わる場合

設定JSONだけ差し替えられます。

例:

```json
{
  "csv_header": "金額",
  "excel_column": "G",
  "type": "number",
  "required": true
}
```

コード自体を変更せず、CSV列とExcel列の対応を変更できます。

## 安全上の注意

- 原本Excelは変更しません。
- 自動で行挿入しません。
- 既存セルを上書きしません。
- CSV内の重複キーを検出します。
- Excel既存データとの重複キーを検出します。
- 全数式を転記前後で比較します。
- 15桁を超えるIDは `number` ではなく `text` として設定してください。
- `.xlsm` のVBAは保持する設定ですが、ActiveX、特殊アドイン、外部データ接続などを含むファイルは本番前に実ファイルで検証してください。
- 本番導入前には、必ず実ファイルのコピーで4月から直近月まで通しテストしてください。

## ファイル構成

```text
excel_csv_safe_transfer/
├─ app.py
├─ config_example.json
├─ requirements.txt
├─ setup.bat
├─ run.bat
├─ setup_local.command
├─ run_local.command
├─ README.md
└─ transfer/
   ├─ __init__.py
   ├─ config.py
   ├─ csv_loader.py
   └─ workbook_engine.py
```

`excel_com.py` / `service.py` のWindows専用方式は廃止し、
Streamlit + openpyxl のローカル処理方式へ変更しています。
