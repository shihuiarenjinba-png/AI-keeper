@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo Streamlit と Excel 処理ライブラリをインストールします。
py -m pip install -r requirements.txt
echo.
echo 完了しました。run.bat で起動できます。
pause
