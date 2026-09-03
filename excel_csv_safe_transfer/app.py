from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import streamlit as st

from transfer.config import AppConfig
from transfer.csv_loader import load_csv
from transfer.local_workbook_engine import LocalWorkbookEngine, file_sha256
from transfer.ui_logic import build_local_ui_state


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_DIR / "config_example.json"

st.set_page_config(page_title="CSV → Excel 安全転記", page_icon="📄", layout="centered")

st.markdown(
    """
    <style>
      .block-container {max-width: 1000px; padding-top: 1.6rem; padding-bottom: 3rem;}
      .hero {padding:1.2rem 1.4rem;border:1px solid rgba(128,128,128,.25);border-radius:16px;margin-bottom:1rem;}
      .hero h1 {font-size:1.9rem;margin:0 0 .3rem 0;}
      .hero p {margin:0;opacity:.78;}
      .step {padding:.9rem 1rem;border:1px solid rgba(128,128,128,.2);border-radius:14px;margin:.75rem 0;}
      .step-title {font-weight:750;font-size:1.08rem;margin-bottom:.35rem;}
      .muted {opacity:.7;font-size:.92rem;}
      .okbox {border:1px solid rgba(50,170,90,.35);border-radius:12px;padding:.9rem 1rem;margin:.6rem 0;}
      div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.22);border-radius:12px;padding:.65rem .8rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>CSV → Excel 安全転記</h1>
      <p>ローカルPC上のExcelを、バックアップと数式検証を行って安全に更新します。</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _choose_local_file(kind: str) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        if kind == "csv":
            selected = filedialog.askopenfilename(
                title="転記するCSVを選択",
                filetypes=[("CSV", "*.csv"), ("すべてのファイル", "*.*")],
            )
        else:
            selected = filedialog.askopenfilename(
                title="更新するExcelを選択",
                filetypes=[("Excel", "*.xlsx *.xlsm"), ("すべてのファイル", "*.*")],
            )
        root.destroy()
        return selected or ""
    except Exception as exc:
        st.warning(
            "OSのファイル選択画面を開けませんでした。パス欄へ直接貼り付けてください。"
            f"\n\n詳細: {exc}"
        )
        return ""


def _uploaded_hash(uploaded) -> str:
    return hashlib.sha256(uploaded.getvalue()).hexdigest() if uploaded else ""


def _load_config(config_upload) -> AppConfig:
    if config_upload is None:
        return AppConfig.load(DEFAULT_CONFIG_PATH)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(config_upload.getvalue())
        path = Path(tmp.name)
    try:
        return AppConfig.load(path)
    finally:
        path.unlink(missing_ok=True)


def _load_csv_from_path(csv_path: str, config: AppConfig):
    return load_csv(Path(csv_path).expanduser().resolve(), config)


def _load_csv_upload(csv_upload, config: AppConfig):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / csv_upload.name
        path.write_bytes(csv_upload.getvalue())
        return load_csv(path, config)


for key in ("csv_path", "excel_path"):
    if key not in st.session_state:
        st.session_state[key] = ""

mode_local, mode_demo = st.tabs(["ローカル更新", "ブラウザ確認用"])

with mode_local:
    st.info(
        "実運用はこちらを使います。Streamlitの画面はブラウザに表示されますが、処理はこのPC上で動き、指定したExcel本体を更新します。"
    )

    st.markdown('<div class="step"><div class="step-title">1. CSVを選択</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([5, 1])
    with c2:
        if st.button("CSV参照", use_container_width=True, key="browse_csv"):
            chosen = _choose_local_file("csv")
            if chosen:
                st.session_state["csv_path"] = chosen
                st.rerun()
    with c1:
        csv_path = st.text_input(
            "CSVパス",
            key="csv_path",
            placeholder="例: /Users/name/Downloads/2026_09.csv",
            label_visibility="collapsed",
        )
    if csv_path and Path(csv_path).expanduser().is_file():
        st.success(f"CSV: {Path(csv_path).expanduser().resolve()}")
    elif csv_path:
        st.error("CSVが見つかりません。パスを確認してください。")
    else:
        st.caption("「CSV参照」を押すか、CSVのパスを貼り付けてください。")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="step"><div class="step-title">2. 更新するExcelを選択</div>', unsafe_allow_html=True)
    e1, e2 = st.columns([5, 1])
    with e2:
        if st.button("Excel参照", use_container_width=True, key="browse_excel"):
            chosen = _choose_local_file("excel")
            if chosen:
                st.session_state["excel_path"] = chosen
                st.rerun()
    with e1:
        excel_path = st.text_input(
            "Excelパス",
            key="excel_path",
            placeholder="例: /Users/name/Documents/2026年度.xlsx",
            label_visibility="collapsed",
        )
    if excel_path and Path(excel_path).expanduser().is_file():
        st.success(f"更新対象: {Path(excel_path).expanduser().resolve()}")
    elif excel_path:
        st.error("Excelが見つかりません。パスを確認してください。")
    else:
        st.caption("ここで指定したExcelファイル自体が更新されます。")
    st.markdown('</div>', unsafe_allow_html=True)

    with st.expander("詳細設定（通常は変更不要）"):
        config_upload = st.file_uploader("設定JSON", type=["json"], key="local_config")

    csv_signature = ""
    excel_signature = ""
    if csv_path and Path(csv_path).expanduser().is_file():
        try:
            csv_signature = file_sha256(Path(csv_path).expanduser())
        except OSError:
            pass
    if excel_path and Path(excel_path).expanduser().is_file():
        try:
            excel_signature = file_sha256(Path(excel_path).expanduser())
        except OSError:
            pass

    signature = "|".join([
        str(csv_path), csv_signature, str(excel_path), excel_signature, _uploaded_hash(config_upload)
    ])
    if st.session_state.get("local_signature") != signature:
        st.session_state["local_signature"] = signature
        st.session_state.pop("preflight", None)
        st.session_state.pop("preflight_excel_sha", None)
        st.session_state.pop("done_result", None)
        st.session_state["confirmed"] = False

    preflight_ok = st.session_state.get("preflight") is not None
    confirmed = st.checkbox(
        "更新対象ExcelとCSVを確認しました",
        key="confirmed",
        disabled=not preflight_ok,
    )
    state = build_local_ui_state(csv_path, excel_path, preflight_ok, confirmed)

    st.markdown('<div class="step"><div class="step-title">3. 事前チェック</div>', unsafe_allow_html=True)
    st.caption(state.preflight_hint)
    if st.button(
        "事前チェックを実行",
        type="primary",
        use_container_width=True,
        disabled=not state.can_preflight,
        key="preflight_button",
    ):
        try:
            with st.spinner("日付・年度・重複・転記先・数式を確認しています…"):
                config = _load_config(config_upload)
                csv_data = _load_csv_from_path(csv_path, config)
                engine = LocalWorkbookEngine(config)
                target = Path(excel_path).expanduser().resolve()
                st.session_state["preflight"] = engine.preflight_file(csv_data, target)
                st.session_state["preflight_excel_sha"] = file_sha256(target)
                st.session_state["confirmed"] = False
            st.rerun()
        except Exception as exc:
            st.session_state.pop("preflight", None)
            st.session_state.pop("preflight_excel_sha", None)
            st.error(f"事前チェックで停止しました：{exc}")

    report = st.session_state.get("preflight")
    if report:
        st.success("事前チェック OK")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("追加件数", f"{report.record_count:,}")
        m2.metric("対象年度", f"{report.fiscal_year}年度")
        m3.metric("開始行", report.target_start_row)
        m4.metric("保護数式", f"{report.formula_count:,}")
        st.markdown(
            f"""
            <div class="okbox">
              CSV期間: <b>{report.min_date} ～ {report.max_date}</b><br>
              Excel最終日: <b>{report.existing_last_date or 'データなし'}</b><br>
              転記行: <b>{report.target_start_row} ～ {report.target_end_row}</b><br>
              確認済み: 既存値上書きなし / 数式セルへの書込みなし / 重複なし
            </div>
            """,
            unsafe_allow_html=True,
        )
        for warning in report.warnings:
            st.warning(warning)
    st.markdown('</div>', unsafe_allow_html=True)

    # stateを最新のcheckbox状態でもう一度作る。
    state = build_local_ui_state(csv_path, excel_path, report is not None, confirmed)
    st.markdown('<div class="step"><div class="step-title">4. 更新を実行</div>', unsafe_allow_html=True)
    st.caption(state.execute_hint)
    st.warning("実行前に原本を `_backup` フォルダへ自動保存します。検証に失敗した場合、元Excelは更新しません。")
    if st.button(
        "このExcelを更新する",
        type="primary",
        use_container_width=True,
        disabled=not state.can_execute,
        key="execute_button",
    ):
        try:
            with st.spinner("バックアップ → 転記 → 数式照合 → 値照合 → Excel更新中…"):
                config = _load_config(config_upload)
                csv_data = _load_csv_from_path(csv_path, config)
                engine = LocalWorkbookEngine(config)
                result = engine.process_in_place(
                    csv_data=csv_data,
                    excel_path=excel_path,
                    expected_sha256=st.session_state["preflight_excel_sha"],
                )
                st.session_state["done_result"] = result
                st.session_state.pop("preflight", None)
                st.session_state.pop("preflight_excel_sha", None)
                st.session_state["confirmed"] = False
            st.rerun()
        except Exception as exc:
            st.error(f"更新処理を停止しました：{exc}")

    if st.session_state.get("done_result"):
        result = st.session_state["done_result"]
        st.success(f"更新完了：{result.record_count:,}件を同じExcelファイルへ追加しました。")
        st.write(f"**更新したExcel:** `{result.excel_path}`")
        st.write(f"**バックアップ:** `{result.backup_path}`")
        st.write(f"**転記行:** {result.target_start_row} ～ {result.target_end_row}")
        st.write(f"**保護確認した数式:** {result.formula_count:,}セル")
    st.markdown('</div>', unsafe_allow_html=True)

with mode_demo:
    st.warning(
        "ここは相手に画面を見せるための確認用です。GitHub/クラウド上で動かす場合、あなたのPC上のExcel実ファイルは直接更新できません。"
    )
    st.markdown("#### 画面確認用ファイル")
    demo_csv = st.file_uploader("CSVをアップロード", type=["csv"], key="demo_csv")
    demo_excel = st.file_uploader("Excelをアップロード", type=["xlsx", "xlsm"], key="demo_excel")
    if demo_csv and demo_excel:
        st.success("2ファイルを受け取りました。これはUI確認用で、元のローカルExcel本体は更新しません。")
    else:
        st.info("CSVとExcelをアップロードすると、選択済み表示を確認できます。")

st.divider()
st.caption(
    "ローカル運用では `python3 -m streamlit run app.py` で起動します。画面はブラウザですが処理はローカルPCで実行されます。"
)
