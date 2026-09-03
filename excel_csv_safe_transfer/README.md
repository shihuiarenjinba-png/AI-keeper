# CSV → Excel 安全転記システム

ローカルPCで使う **Streamlit UI** 版です。

ログイン・アカウント接続・クラウド連携はありません。画面はブラウザに表示されますが、ローカル起動時の処理はそのPC上で実行されます。

## 実運用の基本フロー

画面には常に次の4ステップを表示します。

1. **同じ月のCSVを1個または複数選択**
2. **更新するExcelを選択**
3. **選択したCSVをまとめて事前チェック**
4. **このExcelを一括更新**

事前チェック・更新ボタンは最初から表示し、条件が足りない場合はグレーアウトして理由を表示します。

## 同じ月の複数CSVに対応

実運用では、9月・10月・11月を一度に選ぶより、同じ9月について複数拠点・部門のCSVをまとめて処理することを想定しています。

例:

```text
2026_09_東京.csv
2026_09_大阪.csv
2026_09_名古屋.csv
```

この3ファイルを同時に選択すると、システムは1つの9月バッチとしてまとめて検査し、1回だけExcelを更新します。

### バッチの安全ルール

- 同じバッチでは **年月が完全一致**している必要があります。
- 9月CSVと10月CSVを同時に選ぶと停止します。
- CSV同士で一意キーが重複していると停止します。
- 各CSV内の重複も停止します。
- 結合後は日付順に並べ直してからExcelへ追記します。
- Excel既存データとの重複も停止します。

### 第2ラベル

ファイル名から「東京」「大阪」「営業所A」などの識別ラベルを自動表示します。

画面例:

```text
9月 ｜ 東京       30件
9月 ｜ 大阪       30件
9月 ｜ 名古屋     30件
```

このラベルはまず **入力ファイルの識別用** です。Excelへ拠点名・部門名として実際に書き込む場合は、CSV側の列または設定JSONで明示的に転記列を指定してください。安全のため、システムが勝手にExcel列を追加することはありません。

## 更新対象Excel

更新対象Excelはアップロードコピーではありません。ローカル更新タブで選択した **実ファイルそのものを更新**します。

処理の流れ:

1. CSV群を検査・結合
2. Excelを事前チェック
3. 元Excelを `_backup` へ保存
4. 一時ファイル上で転記
5. 数式を転記前後で全件比較
6. 保存後に再読込して数式を再比較
7. 転記値を全件照合
8. 元Excelが処理中に変更されていないことを再確認
9. すべて合格した場合のみ同じパスのExcelを置換

途中で失敗した場合、元Excelは更新しません。

## ローカル更新とブラウザ確認用の違い

### ローカル更新

実運用はこちらです。

Streamlit画面自体はブラウザに表示されますが、PythonはローカルPC上で動くため、そのPCのCSV・Excelを選択して実ファイルを更新できます。

### ブラウザ確認用

相手にUIを見せるための確認用です。

CSV・Excelをブラウザへアップロードして選択画面を確認できますが、GitHub/クラウド上のアプリから利用者PCの元Excelを直接更新することはできません。

## バックアップ

更新対象Excelと同じフォルダに `_backup` を自動作成します。

```text
Documents/
├─ 2026年度.xlsx
└─ _backup/
   └─ 20260903_173000_123456_2026年度.xlsx
```

バックアップのSHA-256が原本と一致することを確認してから更新を続行します。

## 数式保護

転記前に全シートの数式を取得し、次のタイミングで全件比較します。

- 転記直後
- 保存後の再読込後

1セルでも数式の追加・削除・変更を検出した場合、元Excelを置換しません。

## 対応環境

- Windows
- macOS
- Linux
- Python 3.10+
- Streamlit
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

```bash
cd /Users/ユーザー名/Downloads/excel_csv_safe_transfer
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

または `setup_local.command` → `run_local.command` を利用できます。

ローカル起動でも **同じStreamlit UI** がブラウザで開きます。

## テスト済み内容

- UIボタン状態: 未選択 / CSVのみ / Excelのみ / 複数CSV / 事前チェック済み / 確認済み
- Excel A/B: 9月→10月→11月→12月の4回連続同一パス更新
- 同月複数CSV: 9月を東京・大阪・名古屋の3ファイルに分割して一括更新
- 3CSV合計90件をExcel A/Bへ1回で更新
- 数式全件一致
- バックアップ作成
- 9月＋10月混在の拒否
- 複数CSV間の重複キー拒否

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
│  ├─ test_app_smoke.py
│  ├─ test_ui_logic.py
│  └─ test_batch_csv.py
└─ transfer/
   ├─ __init__.py
   ├─ batch_csv.py
   ├─ config.py
   ├─ csv_loader.py
   ├─ workbook_engine.py
   ├─ local_workbook_engine.py
   └─ ui_logic.py
```
