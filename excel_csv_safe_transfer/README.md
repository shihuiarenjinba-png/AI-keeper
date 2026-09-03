# CSV → Excel 安全転記システム

ローカルPCで使う **Streamlit UI** 版です。

ログイン、アカウント接続、クラウド連携はありません。画面はブラウザに表示されますが、ローカル起動時の処理はそのPC上で実行されます。

## 重要: 2つの画面モード

### ローカル更新

実運用はこちらです。

画面は常に次の4ステップを表示します。

1. **CSVを選択**
2. **更新するExcelを選択**
3. **事前チェックを実行**
4. **このExcelを更新する**

「事前チェック」と「更新実行」のボタンは最初から表示されます。条件が不足している場合はグレーアウトし、何が不足しているかを画面に表示します。

CSVとExcelはOS標準の「参照」ダイアログ、またはパス入力で指定します。

更新対象Excelはアップロードコピーではありません。**指定した実ファイルそのものを更新**します。

### ブラウザ確認用

相手にUIを見せるための確認用です。

CSVとExcelをアップロードできますが、GitHubやクラウド上で動いている画面から、利用者PC上の元Excelを直接更新することはできません。

したがって、実際の更新テスト・本番運用は必ず「ローカル更新」タブで行います。

## 更新処理の流れ

1. CSVを選択
2. 更新対象Excelの実ファイルを選択
3. 事前チェック
4. 元Excelを `_backup` フォルダへバックアップ
5. 一時ファイル上でCSV転記
6. 数式・転記値を検証
7. すべて合格した場合だけ、指定したExcelと同じパスを安全に置換

ダウンロードした別ファイルを手作業で戻す運用ではありません。

## バックアップ

更新前の原本は、更新対象Excelと同じフォルダに自動作成される `_backup` フォルダへ保存します。

```text
Documents/
├─ 2026年度.xlsx              ← 更新対象
└─ _backup/
   └─ 20260903_173000_123456_2026年度.xlsx
```

バックアップは更新前のSHA-256と一致することを確認してから処理を続行します。

## 安全設計

- 転記対象Excelが開かれている可能性がある場合は停止
- 事前チェック後にExcelが変更されていた場合は停止
- 転記先セルに数式があれば停止
- 転記先セルに既存値があれば停止
- CSV内の重複キーを検出
- Excel既存データとの重複キーを検出
- 年度と日付順を確認
- 転記直後に全数式を比較
- 保存後に再読込して全数式を再比較
- 保存後に転記値を全件照合
- 一時ファイルが正常に再オープンできることを確認
- 元Excelが処理中に変更されていないことを置換直前に再確認
- すべて合格した場合だけ `os.replace()` で同じパスを置換

途中で失敗した場合、元Excelは更新しません。

## 対応環境

- Windows
- macOS
- Linux
- Python 3.10+
- ブラウザ（Streamlitの画面表示用）

Microsoft Excel本体は処理時には不要です。

対応ファイル:

- `.xlsx`
- `.xlsm`（VBA保持モード。特殊機能は実ファイル検証推奨）
- `.csv`

`.xls` / `.xlsb` は対象外です。

## ローカル起動

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

```bash
cd /Users/ユーザー名/Downloads/excel_csv_safe_transfer
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

または `setup_local.command` → `run_local.command` を利用できます。

起動後、通常は `localhost` のStreamlit画面がブラウザで開きます。**ローカル起動でもUIは同じStreamlit画面です。** 違うのは、処理するPythonがローカルPC上にいるため、そのPCの実ファイルを更新できる点です。

## 数式保護

転記前に全シートの数式を取得し、転記直後と保存後に比較します。

1セルでも数式の追加・削除・変更を検出した場合は、更新対象Excelを置き換えません。

## 追記ルール

`config_example.json` で以下を指定します。

- 対象シート
- データ開始行 / 最終行
- 日付列
- 一意キー
- 年度開始月
- CSV列 → Excel列の対応

4月開始の場合、2026/04/01～2027/03/31を2026年度として扱います。

## 翌年度にレイアウトが変わる場合

設定JSONだけ差し替えられます。コード本体を変えずにCSV列とExcel列の対応を変更できます。

## `.xlsm` について

VBAは `keep_vba=True` で保持する設定です。ただし、ActiveX、特殊アドイン、Power Query、外部接続などを含む実ファイルでは、本番前に追加検証してください。

## テスト

`tests/test_ui_logic.py` では、ボタン状態を次のケースで確認します。

- 未選択
- CSVのみ
- Excelのみ
- CSV + Excel
- 事前チェック済み
- 確認済み
- 不正な拡張子

また、テストExcel A/Bについて9月→10月→11月→12月の4回連続同一パス更新を確認しています。

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
├─ tests/
│  └─ test_ui_logic.py
└─ transfer/
   ├─ __init__.py
   ├─ config.py
   ├─ csv_loader.py
   ├─ workbook_engine.py
   ├─ local_workbook_engine.py
   └─ ui_logic.py
```
