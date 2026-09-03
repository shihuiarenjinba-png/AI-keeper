from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import streamlit as st

from transfer.config import AppConfig
from transfer.csv_loader import load_csv
from transfer.workbook_engine import WorkbookEngine, PreflightReport


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_DIR / "config_example.json"


st.set_page_config(
    page_title="CSV → Excel 安全転記",
    page_icon="📄",
    layout="centered",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 980px; padding-top: 2rem; padding-bottom: 3rem;}
      .hero {
        padding: 1.35rem 1.5rem;
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 16px;
        margin-bottom: 1.25rem;
      }
      .hero h1 {font-size: 2rem; margin: 0 0 .35rem 0;}
      .hero p {margin: 0; opacity: .78;}
      .step-title {font-weight: 700; font-size: 1.05rem; margin-bottom: .35rem;}
      div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.22);
        border-radius: 12px;
        padding: .75rem 1rem;
      }
      .okbox {
        border: 1px solid rgba(50,170,90,.35);
        border-radius: 12px;
        padding: .9rem 1rem;
        margin: .5rem 0 1rem 0;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>CSV → Excel 安全転記</h1>
      <p>CSVと元Excelを選ぶだけ。元ファイルは上書きせず、数式を確認して転記済みExcelを作成します。</p>
    </div>
    """,
    unsafe_allow_html=True,
)


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


def _run_preflight(csv_upload, excel_upload, config_upload) -> PreflightReport:
    config = _load_config(config_upload)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        csv_path = td_path / csv_upload.name
        csv_path.write_bytes(csv_upload.getvalue())
        csv_data = load_csv(csv_path, config)

    engine = WorkbookEngine(config)
    return engine.preflight(
        csv_data=csv_data,
        workbook_bytes=excel_upload.getvalue(),
        workbook_name=excel_upload.name,
    )


def _make_output(csv_upload, excel_upload, config_upload):
    config = _load_config(config_upload)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        csv_path = td_path / csv_upload.name
        csv_path.write_bytes(csv_upload.getvalue())
        csv_data = load_csv(csv_path, config)

    engine = WorkbookEngine(config)
    return engine.process(
        csv_data=csv_data,
        workbook_bytes=excel_upload.getvalue(),
        workbook_name=excel_upload.name,
    )


st.markdown('<div class="step-title">1. ファイルを選択</div>', unsafe_allow_html=True)
left, right = st.columns(2)
with left:
    csv_upload = st.file_uploader(
        "転記するCSV",
        type=["csv"],
        help="今回追加する月のCSVを選択してください。",
    )
with right:
    excel_upload = st.file_uploader(
        "元になるExcel",
        type=["xlsx", "xlsm"],
        help="数式が入っている元Excelを選択してください。元ファイル自体は変更しません。",
    )

with st.expander("詳細設定（通常は触らなくて大丈夫です）"):
    st.caption(
        "年度が変わって列位置やシート名が変わった場合だけ設定JSONを差し替えます。"
        "未指定の場合は config_example.json を使います。"
    )
    config_upload = st.file_uploader(
        "転記設定JSON（任意）",
        type=["json"],
        label_visibility="collapsed",
    )

current_signature = "|".join(
    [
        _uploaded_hash(csv_upload),
        _uploaded_hash(excel_upload),
        _uploaded_hash(config_upload),
    ]
)
if st.session_state.get("input_signature") != current_signature:
    st.session_state["input_signature"] = current_signature
    st.session_state.pop("preflight", None)
    st.session_state.pop("output_bytes", None)
    st.session_state.pop("output_name", None)
    st.session_state.pop("output_result", None)

st.markdown('<div class="step-title">2. 事前チェック</div>', unsafe_allow_html=True)

if not csv_upload or not excel_upload:
    st.info("CSVとExcelの2ファイルを選択すると、事前チェックを実行できます。")
else:
    if st.button("事前チェックを実行", type="primary", use_container_width=True):
        try:
            with st.spinner("CSV・Excel・数式・重複を確認しています…"):
                st.session_state["preflight"] = _run_preflight(
                    csv_upload, excel_upload, config_upload
                )
        except Exception as exc:
            st.session_state.pop("preflight", None)
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
          <b>確認</b>：既存値への上書きなし / 数式セルへの書込みなし / 重複なし
        </div>
        """,
        unsafe_allow_html=True,
    )

    for warning in report.warnings:
        st.warning(warning)

    st.markdown('<div class="step-title">3. 転記済みExcelを作成</div>', unsafe_allow_html=True)
    st.caption("元Excelは変更しません。検証済みの新しいExcelファイルを作ります。")

    if st.button("転記済みExcelを作成", type="primary", use_container_width=True):
        try:
            with st.spinner("転記 → 保存 → 再読込 → 数式再照合を行っています…"):
                result = _make_output(csv_upload, excel_upload, config_upload)
                st.session_state["output_bytes"] = result.workbook_bytes
                st.session_state["output_name"] = result.output_name
                st.session_state["output_result"] = result
        except Exception as exc:
            st.session_state.pop("output_bytes", None)
            st.error(f"転記処理を停止しました：{exc}")

if st.session_state.get("output_bytes"):
    result = st.session_state["output_result"]
    st.success(
        f"転記完了：{result.record_count:,}件を追加し、"
        f"{result.formula_count:,}個の数式が変更されていないことを確認しました。"
    )
    st.download_button(
        "転記済みExcelを保存",
        data=st.session_state["output_bytes"],
        file_name=st.session_state["output_name"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

st.divider()
st.caption(
    "ローカル利用前提です。ログイン・アカウント接続・クラウド連携はありません。"
    "対応形式は .xlsx / .xlsm です。特殊なマクロ・外部接続・アドインを含むブックは本番前に実ファイルで検証してください。"
)
