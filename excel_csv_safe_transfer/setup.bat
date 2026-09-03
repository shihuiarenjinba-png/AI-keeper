@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo pywin32 をインストールします。
py -m pip install -r requirements.txt
echo.
echo 完了しました。
pause
