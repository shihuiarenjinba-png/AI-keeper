"""
run_all.py  ─  FF5遅行ファクター分析 完全パイプライン
=======================================================
使い方:
    cd ff5_project          ← このスクリプトがあるフォルダに移動
    python run_all.py --fred-api-key a578d4c9bfdaabd0b502321ffaea965b

オプション:
    --start-year  2006      サンプル開始年（デフォルト）
    --end-year    2025      サンプル終了年（デフォルト）
    --skip-kernel           カーネル検定をスキップ（高速化、約30分短縮）

必要パッケージのインストール（初回のみ）:
    pip install pandas numpy scipy scikit-learn statsmodels openpyxl \
                pandas_datareader fredapi matplotlib seaborn requests

所要時間の目安:
    Step1  データ取得          約2〜5分
    Step2  線形グレンジャー     約3分
    Step3  ランダムフォレスト   約5〜10分
    Step4  線形レポート生成     約1分
    Step5  サブサンプル分析     約3分
    Step6  閾値グレンジャー     約5分
    Step7  カーネル検定         約15〜30分（--skip-kernelで省略可）
    Step8  ローリング分析       約5分
    Step9  非線形レポート生成   約1分
    合計:  約40〜60分（カーネルあり）／約15〜20分（カーネルなし）

出力ファイル:
    outputs/ff5_linear_report.xlsx     線形グレンジャー + ランダムフォレスト
    outputs/ff5_nonlinear_report.xlsx  非線形・体制転換分析
    data/merged_data.csv               FF5+FRED統合データ（再利用可）
"""

import argparse, subprocess, sys, os

BASE   = os.path.dirname(os.path.abspath(__file__))
LINEAR = os.path.join(BASE, "ff5-macro-analysis", "scripts")
NL     = os.path.join(BASE, "nonlinear-granger", "scripts")


def run(cmd, desc, step):
    print(f"\n{'='*60}")
    print(f"▶ Step {step}: {desc}")
    print(f"{'='*60}")
    rc = subprocess.run(f"{sys.executable} {cmd}", shell=True).returncode
    if rc != 0:
        print(f"⚠️  エラー発生（returncode={rc}）。続行します。")
    return rc


def main():
    parser = argparse.ArgumentParser(description="FF5遅行ファクター分析 完全パイプライン")
    parser.add_argument("--fred-api-key", required=True)
    parser.add_argument("--start-year",   type=int, default=2006)
    parser.add_argument("--end-year",     type=int, default=2025)
    parser.add_argument("--skip-kernel",  action="store_true",
                        help="カーネル検定をスキップ（高速化）")
    args = parser.parse_args()

    for d in ["data", "results", "outputs"]:
        os.makedirs(os.path.join(BASE, d), exist_ok=True)

    # ── 線形分析 ─────────────────────────────────────────────────────────
    run(f'{LINEAR}/01_data_collection.py '
        f'--start-year {args.start_year} --end-year {args.end_year} '
        f'--fred-api-key {args.fred_api_key} '
        f'--output {BASE}/data/merged_data.csv',
        "FF5 + FREDデータ取得", 1)

    run(f'{LINEAR}/02_granger_analysis.py '
        f'--data {BASE}/data/merged_data.csv --max-lag 6 --alpha 0.05 '
        f'--output {BASE}/results/granger_results.csv',
        "線形グレンジャー因果性検定（35ペア）", 2)

    run(f'{LINEAR}/03_random_forest.py '
        f'--data {BASE}/data/merged_data.csv --train-ratio 0.7 --n-estimators 500 '
        f'--output {BASE}/results/rf_results.csv',
        "ランダムフォレスト分析", 3)

    run(f'{LINEAR}/04_generate_report.py '
        f'--granger        {BASE}/results/granger_results.csv '
        f'--granger-matrix {BASE}/results/granger_results_pmatrix.csv '
        f'--rf             {BASE}/results/rf_results.csv '
        f'--importance     {BASE}/results/rf_results_feature_importance.csv '
        f'--output         {BASE}/outputs/ff5_linear_report.xlsx',
        "線形分析Excelレポート生成", 4)

    # ── 非線形分析 ───────────────────────────────────────────────────────
    run(f'{NL}/01_subsample.py '
        f'--data {BASE}/data/merged_data.csv '
        f'--output {BASE}/results/subsample_results.csv',
        "サブサンプル分析（危機期 / 平常期 / 低金利期 / 高金利期）", 5)

    run(f'{NL}/02_threshold_granger.py '
        f'--data {BASE}/data/merged_data.csv --threshold-var DEF_SPREAD '
        f'--output {BASE}/results/tar_results.csv',
        "閾値グレンジャー検定（TAR / DEF_SPREAD体制）", 6)

    if args.skip_kernel:
        print("\n⚠️  Step 7: カーネル検定をスキップ（--skip-kernelオプション）")
    else:
        run(f'{NL}/03_kernel_granger.py '
            f'--data {BASE}/data/merged_data.csv --n-permutations 199 '
            f'--output {BASE}/results/kernel_results.csv',
            "カーネルグレンジャー検定（置換検定 n=199）", 7)

    run(f'{NL}/04_rolling_granger.py '
        f'--data {BASE}/data/merged_data.csv --window 60 '
        f'--output {BASE}/results/rolling_results.csv',
        "ローリングウィンドウ分析（時変因果性、window=60ヶ月）", 8)

    run(f'{NL}/05_generate_nonlinear_report.py '
        f'--subsample {BASE}/results/subsample_results.csv '
        f'--tar       {BASE}/results/tar_results.csv '
        f'--kernel    {BASE}/results/kernel_results.csv '
        f'--rolling   {BASE}/results/rolling_results.csv '
        f'--linear    {BASE}/results/granger_results.csv '
        f'--output    {BASE}/outputs/ff5_nonlinear_report.xlsx',
        "非線形分析Excelレポート生成", 9)

    # ── 完了メッセージ ────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("【全分析完了】出力ファイル:")
    for f in ["outputs/ff5_linear_report.xlsx",
              "outputs/ff5_nonlinear_report.xlsx",
              "data/merged_data.csv"]:
        path = os.path.join(BASE, f)
        size = os.path.getsize(path) / 1024 if os.path.exists(path) else 0
        mark = "✓" if os.path.exists(path) else "✗"
        print(f"  {mark} {f}  ({size:.0f} KB)")
    print("="*60)


if __name__ == "__main__":
    main()
