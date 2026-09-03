#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
echo
echo "セットアップ完了。run_local.command で起動できます。"
