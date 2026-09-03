from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import streamlit as st

from transfer.config import AppConfig
from transfer.csv_loader import load_csv
from transfer.workbook_engine import WorkbookEngine, PreflightReport, file_sha256


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_DIR / "config_example.json"

st.set_page_config(page_title="CSV → Excel 安全転記", page_icon="📄", layout="centered")

st.markdown(
    """
    <style>
      .block-container {max-width: 980px; padding-top: 2rem; padding-bottom: 3rem;}
      .hero {padding:1.35rem 1.5rem;border:1px solid rgba(128,128,128,.25);border-radius:16px;margin-bottom:1.25rem;}
      .hero h1 {font-size:2rem;margin:0 0 .35rem 0;}
      .hero p {margin:0;opacity:.78;}
      .step-title {font-weight:700;font-size:1.05rem;margin:.8rem 0 .35rem 0;}
      div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.22);border-radius:12px;padding:.75rem 1rem;}
      .okbox {border:1px solid rgba(50,170,90,.35);border-radius:12px;padding:.9rem 1rem;margin:.5rem 0 1rem 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>CSV → Excel 安全転記</h1>
      <p>CSVを読み込み、指定したローカルExcelそのものを安全に更新します。更新前には同じ場所へ自動バックアップを作成します。</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _choose_excel_file() -> str:
    """ローカル実行時にOS標準のファイル選択画面を開く。"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="更新するExcelを選択",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("すべてのファイル", "*.*")],
        )
        root.destroy()
        return selected or ""
    except Exception as exc:
        st.warning(
            "OSのファイル選択画面を開けませんでした。下のパス欄へExcelのパスを直接貼り付けてください。"
            f" ({exc})"
        )
        return ""


def _uploaded_hash(uploaded) -> str:
    if uploaded is None:
        return ""
    return hashlib.sha256(uploaded.getvalue()).hexdigest()


def _load_config(config_upload) -> AppConfig:
    if config_upload is None:
        return AppConfig.load(DEFAULT_CONFIG_PATH)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(config_upload.getvalue())
        tmp_path = Path(tmp.name)
    try:
        return AppConfig.load(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _load_csv_upload(csv_upload, config: AppConfig):
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / csv_upload.name
        csv_path.write_bytes(csv_upload.getvalue())
        return load_csv(csv_path, config)


if "excel_path" not in st.session_state:
    st.session_state["excel_path"] = ""

st.markdown('<div class="step-title">1. 転記するCSVを選択</div>', unsafe_allow_html=True)
csv_upload = st.file_uploader(
    "CSVファイル",
    type=["csv"],
    help="今回追加する月のCSVを選択してください。",
    label_visibility="collapsed",
)

st.markdown('<div class="step-title">2. 更新するExcelを選択</div>', unsafe_allow_html=True)
st.caption("ここで選択したExcelファイル自体が更新されます。ダウンロード用の別ファイルは作りません。")
col_path, col_browse = st.columns([5, 1])
with col_browse:
    if st.button("参照…", use_container_width=True):
        chosen = _choose_excel_file()
        if chosen:
            st.session_state["excel_path"] = chosen
            st.rerun()
with col_path:
    excel_path = st.text_input(
        "更新対象Excelのパス",
        key="excel_path",
        placeholder="例: /Users/name/Documents/2026年度.xlsx または C:\\Data\\2026年度.xlsx",
        label_visibility="collapsed",
    )

if excel_path:
    resolved = Path(excel_path).expanduser()
    if resolved.is_file():
        st.success(f"更新対象: {resolved.resolve()}")
    else:
        st.warning("指定したExcelが見つかりません。パスを確認してください。")

with st.expander("詳細設定（通常は触らなくて大丈夫です）"):
    st.caption("年度変更などで列・シート構成が変わった場合のみ、設定JSONを差し替えます。")
    config_upload = st.file_uploader(
        "転記設定JSON（任意）",
        type=["json"],
        label_visibility="collapsed",
    )

excel_signature = ""
if excel_path and Path(excel_path).expanduser().is_file():
    try:
        excel_signature = file_sha256(Path(excel_path).expanduser())
    except OSError:
        excel_signature = ""

current_signature = "|".join([
    _uploaded_hash(csv_upload),
    excel_signature,
    _uploaded_hash(config_upload),
    str(excel_path),
])
if st.session_state.get("input_signature") != current_signature:
    st.session_state["input_signature"] = current_signature
    st.session_state.pop("preflight", None)
    st.session_state.pop("preflight_excel_sha", None)
    st.session_state.pop("done_result", None)

st.markdown('<div class="step-title">3. 事前チェック</div>', unsafe_allow_html=True)

ready = bool(csv_upload and excel_path and Path(excel_path).expanduser().is_file())
if not ready:
    st.info("CSVと更新対象Excelを指定すると事前チェックを実行できます。")
else:
    if st.button("事前チェックを実行", type="primary", use_container_width=True):
        try:
            with st.spinner("CSV・Excel・数式・重複を確認しています…"):
                config = _load_config(config_upload)
                csv_data = _load_csv_upload(csv_upload, config)
                engine = WorkbookEngine(config)
                path = Path(excel_path).expanduser().resolve()
                st.session_state["preflight"] = engine.preflight_file(csv_data, path)
                st.session_state["preflight_excel_sha"] = file_sha256(path)
        except Exception as exc:
            st.session_state.pop("preflight", None)
            st.session_state.pop("preflight_excel_sha", None)
            st.error(f"事前チェックで停止しました：{exc}")

report: PreflightReport | None = st.session_state.get("preflight")

if report:
    st.success("事前チェックに合格しました。")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("追加件数", f"{report.record_count:,}")
    c2.metric("対象年度", f"{report.fiscal_year}年度")
    c3.metric("転記開始行", f"{report.target_start_row}")
    c4.metric("保護数式", f"{report.formula_count:,}")

    st.markdown(
        f"""
        <div class="okbox">
          <b>CSV期間</b>：{report.min_date} ～ {report.max_date}<br>
          <b>Excel既存最終日</b>：{report.existing_last_date or "データなし"}<br>
          <b>転記予定行</b>：{report.target_start_row} ～ {report.target_end_row}<br>
          <b>更新対象</b>：{Path(excel_path).expanduser().resolve()}<br>
          <b>安全確認</b>：既存値への上書きなし / 数式セルへの書込みなし / 重複なし
        </div>
        """,
        unsafe_allow_html=True,
    )

    for warning in report.warnings:
        st.warning(warning)

    st.markdown('<div class="step-title">4. このExcelを更新</div>', unsafe_allow_html=True)
    st.warning(
        "実行すると、上記のExcelファイル自体を更新します。更新前の原本は同じフォルダの "
        "_backup フォルダへ自動保存します。"
    )

    confirm = st.checkbox("更新対象とCSV内容を確認しました")
    if st.button(
        "Excelを安全に更新",
        type="primary",
        use_container_width=True,
        disabled=not confirm,
    ):
        try:
            with st.spinner("バックアップ → 転記 → 数式照合 → 値照合 → 元Excel更新中…"):
                config = _load_config(config_upload)
                csv_data = _load_csv_upload(csv_upload, config)
                engine = WorkbookEngine(config)
                result = engine.process_in_place(
                    csv_data=csv_data,
                    excel_path=excel_path,
                    expected_sha256=st.session_state["preflight_excel_sha"],
                )
                st.session_state["done_result"] = result
                st.session_state.pop("preflight", None)
                st.session_state.pop("preflight_excel_sha", None)
            st.rerun()
        except Exception as exc:
            st.error(f"更新処理を停止しました：{exc}")

if st.session_state.get("done_result"):
    result = st.session_state["done_result"]
    st.success(
        f"更新完了：{result.record_count:,}件を追加しました。指定したExcelファイルを更新済みです。"
    )
    st.write(f"**更新したExcel:** `{result.excel_path}`")
    st.write(f"**バックアップ:** `{result.backup_path}`")
    st.write(f"**転記行:** {result.target_start_row} ～ {result.target_end_row}")
    st.write(f"**保護確認した数式:** {result.formula_count:,}セル")

st.divider()
st.caption(
    "ローカル利用専用です。ログイン・アカウント接続・クラウド認証はありません。"
    "更新対象Excelは、転記時に閉じておいてください。"
)
