# CSV → Excel 安全転記システム

WindowsローカルPCで使う **Streamlit UI** 版です。

ログイン・CSV/Excelのクラウドアップロードは使いません。画面はブラウザに表示されますが、`run.bat` でローカル起動した場合、CSV読込・バックアップ・Excel更新はそのWindows PC上で実行されます。

## 実運用の基本フロー

1. **同じ月のCSVを1個または複数指定**
2. **更新するExcelを指定**
3. **選択したCSVをまとめて事前チェック**
4. **このExcelを一括更新**

画面では入力欄の左に **`パス =`** を固定表示します。利用者はファイルパスだけを貼り付けます。

## Windowsでのパス入力

エクスプローラーで対象ファイルを Shift + 右クリック、または「パスのコピー」を使って、そのまま貼り付けてください。

CSV例:

```text
C:\Users\Mitsuki\Downloads\2026_09_東京.csv
C:\Users\Mitsuki\Downloads\2026_09_大阪.csv
C:\Users\Mitsuki\Downloads\2026_09_名古屋.csv
```

Excel例:

```text
C:\Users\Mitsuki\Documents\2026年度.xlsx
```

Windowsの「パスのコピー」で次のようにダブルクォートが付いても自動で除去します。

```text
"C:\Users\Mitsuki\Documents\2026年度.xlsx"
```

複数CSVは **1行に1ファイル** を入力します。`CSV参照` / `Excel参照` ボタンからローカルファイル選択画面を開くこともできます。

## 同じ月の複数CSV

実運用では、9月・10月・11月を一度に処理するのではなく、同じ月について複数拠点・部門のCSVをまとめて処理します。

例:

```text
2026_09_東京.csv
2026_09_大阪.csv
2026_09_名古屋.csv
```

### バッチの安全ルール

- 同じバッチでは年月が完全一致している必要があります。
- 9月CSVと10月CSVを同時に指定すると停止します。
- CSV内・CSV間で一意キーが重複すると停止します。
- Excel既存データとの重複も停止します。
- 結合後は日付順に並べてから転記します。

## 更新対象Excel

更新対象はアップロードコピーではなく、指定した **ローカル実ファイルそのもの** です。

処理の流れ:

1. CSV群を検査・結合
2. Excelを事前チェック
3. 元Excelを `_backup` に保存
4. 一時ファイル上で転記
5. 数式を転記前後で全件比較
6. 保存後に再読込して数式を再比較
7. 転記値を全件照合
8. 元Excelが処理中に変更されていないことを再確認
9. すべて合格した場合のみ同じパスのExcelを置換

途中で失敗した場合、元Excelは更新しません。

## バックアップ

更新対象Excelと同じフォルダに `_backup` を自動作成します。

```text
Documents/
├─ 2026年度.xlsx
└─ _backup/
   └─ 20260903_173000_123456_2026年度.xlsx
```

## データをGitHubへ入れないための設定

リポジトリの `.gitignore` で、次をGit管理対象外にしています。

```text
*.csv
*.xlsx
*.xlsm
*.xls
*.xlsb
_backup/
work/
```

コードはGitHubで管理し、実データはローカルPCにだけ置く運用を想定しています。

## Windowsでの起動

初回:

```text
setup.bat
```

通常:

```text
run.bat
```

手動の場合:

```text
py -m streamlit run app.py
```

## 対応形式

- Windows
- Python 3.10+
- Streamlit
- `.csv`
- `.xlsx`
- `.xlsm`（VBA保持モード）

`.xls` / `.xlsb` は更新対象外です。

## テスト対象

- 未入力時に事前チェック・更新ボタンが無効
- CSVのみ / Excelのみでは実行不可
- 複数CSVの同月判定
- CSV内・CSV間重複の拒否
- Excel既存データとの重複拒否
- 数式全件一致
- バックアップ作成
- Windowsローカルパス入力UI
- CSV/Excel本体のブラウザアップロードUIを表示しない
