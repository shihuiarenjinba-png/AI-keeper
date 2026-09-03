from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import streamlit as st

from transfer.batch_csv import load_same_month_batch
from transfer.config import AppConfig
from transfer.local_workbook_engine import LocalWorkbookEngine, file_sha256
from transfer.ui_logic import build_local_ui_state


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = APP_DIR / "config_example.json"

st.set_page_config(page_title="CSV → Excel 安全転記", page_icon="📄", layout="centered")

st.markdown(
    """
    <style>
      .block-container {max-width: 1040px; padding-top: 1.5rem; padding-bottom: 3rem;}
      .hero {padding:1.2rem 1.4rem;border:1px solid rgba(128,128,128,.25);border-radius:16px;margin-bottom:1rem;}
      .hero h1 {font-size:1.9rem;margin:0 0 .3rem 0;}
      .hero p {margin:0;opacity:.78;}
      .step {padding:.95rem 1rem;border:1px solid rgba(128,128,128,.2);border-radius:14px;margin:.8rem 0;}
      .step-title {font-weight:750;font-size:1.08rem;margin-bottom:.35rem;}
      .okbox {border:1px solid rgba(50,170,90,.35);border-radius:12px;padding:.9rem 1rem;margin:.6rem 0;}
      .path-label {padding-top:.55rem;font-weight:750;white-space:nowrap;}
      div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.22);border-radius:12px;padding:.65rem .8rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>CSV → Excel 安全転記</h1>
      <p>Windowsローカル専用。CSVとExcelのパスを指定し、このPC内だけで検査・更新します。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info(
    "実運用はWindows PC上で `run.bat` から起動してください。"
    "CSV・Excel本体をStreamlit Cloudへアップロードする方式は使いません。"
)


def _choose_local_files(kind: str) -> list[str]:
    """Windowsローカルのファイル選択ダイアログを開く。"""
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
            selected = filedialog.askopenfilenames(
                title="同じ月のCSVを複数選択できます",
                filetypes=[("CSV", "*.csv"), ("すべてのファイル", "*.*")],
            )
            result = list(selected)
        else:
            selected_one = filedialog.askopenfilename(
                title="更新するExcelを選択",
                filetypes=[("Excel", "*.xlsx *.xlsm"), ("すべてのファイル", "*.*")],
            )
            result = [selected_one] if selected_one else []
        root.destroy()
        return result
    except Exception as exc:
        st.warning(
            "Windowsのファイル選択画面を開けませんでした。パス欄へ直接貼り付けてください。"
            f"\n\n詳細: {exc}"
        )
        return []


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


def _clean_path_text(text: str) -> str:
    """Windowsの「パスのコピー」で付く引用符と前後空白を除去する。"""
    value = str(text or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def _paths_from_text(text: str) -> list[str]:
    """1行1パスを読み、空行を除外してWindowsパス文字列を返す。"""
    paths: list[str] = []
    for line in str(text or "").splitlines():
        cleaned = _clean_path_text(line)
        if cleaned:
            paths.append(cleaned)
    return paths


if "csv_paths_text" not in st.session_state:
    st.session_state["csv_paths_text"] = ""
if "excel_path" not in st.session_state:
    st.session_state["excel_path"] = ""

st.markdown('<div class="step"><div class="step-title">1. 同じ月のCSVを指定</div>', unsafe_allow_html=True)
st.caption(
    "エクスプローラーで「パスのコピー」をして貼り付けます。複数CSVは1行に1ファイル。"
    "コピー時に付くダブルクォートは自動で除去します。"
)

csv_label_col, csv_input_col, csv_button_col = st.columns([1.15, 6.85, 2.0])
with csv_label_col:
    st.markdown('<div class="path-label">パス =</div>', unsafe_allow_html=True)
with csv_button_col:
    if st.button("CSV参照", use_container_width=True, key="browse_csvs"):
        chosen = _choose_local_files("csv")
        if chosen:
            st.session_state["csv_paths_text"] = "\n".join(chosen)
            st.rerun()
with csv_input_col:
    csv_text = st.text_area(
        "CSVパス（1行に1ファイル）",
        key="csv_paths_text",
        height=115,
        placeholder=(
            "C:\\Users\\Mitsuki\\Downloads\\2026_09_東京.csv\n"
            "C:\\Users\\Mitsuki\\Downloads\\2026_09_大阪.csv\n"
            "C:\\Users\\Mitsuki\\Downloads\\2026_09_名古屋.csv"
        ),
        label_visibility="collapsed",
    )

st.caption(r"記入例：C:\Users\Mitsuki\Downloads\2026_09_東京.csv")
csv_paths = _paths_from_text(csv_text)

if csv_paths:
    valid_count = 0
    for index, csv_path in enumerate(csv_paths, start=1):
        p = Path(csv_path).expanduser()
        if p.is_file() and p.suffix.lower() == ".csv":
            valid_count += 1
            st.write(f"✓ **{index}. {p.stem}**  —  `{p}`")
        else:
            st.error(f"{index}. CSVが見つかりません: {csv_path}")
    if valid_count == len(csv_paths):
        st.success(f"{valid_count}個のCSVを確認しました。")
else:
    st.caption("ファイルパスを貼り付けるか、「CSV参照」から選択してください。1ファイルだけでも利用できます。")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="step"><div class="step-title">2. 更新するExcelを指定</div>', unsafe_allow_html=True)
st.caption("更新したいExcel本体のWindowsパスを貼り付けます。")

excel_label_col, excel_input_col, excel_button_col = st.columns([1.15, 6.85, 2.0])
with excel_label_col:
    st.markdown('<div class="path-label">パス =</div>', unsafe_allow_html=True)
with excel_button_col:
    if st.button("Excel参照", use_container_width=True, key="browse_excel"):
        chosen = _choose_local_files("excel")
        if chosen:
            st.session_state["excel_path"] = chosen[0]
            st.rerun()
with excel_input_col:
    excel_path_raw = st.text_input(
        "Excelパス",
        key="excel_path",
        placeholder=r"C:\Users\Mitsuki\Documents\2026年度.xlsx",
        label_visibility="collapsed",
    )

excel_path = _clean_path_text(excel_path_raw)
st.caption(r"記入例：C:\Users\Mitsuki\Documents\2026年度.xlsx")

if excel_path and Path(excel_path).expanduser().is_file():
    st.success(f"更新対象: {Path(excel_path).expanduser().resolve()}")
elif excel_path:
    st.error(f"Excelが見つかりません: {excel_path}")
else:
    st.caption("ここで指定したExcelファイル自体が更新されます。")
st.markdown('</div>', unsafe_allow_html=True)

with st.expander("詳細設定（通常は変更不要）"):
    config_upload = st.file_uploader("設定JSON", type=["json"], key="local_config")
    st.caption(
        "設定JSONだけは必要に応じて選択できます。CSV・Excel本体はアップロードせず、上のローカルパスを使います。"
    )

csv_signature_parts: list[str] = []
for csv_path in csv_paths:
    p = Path(csv_path).expanduser()
    if p.is_file():
        try:
            csv_signature_parts.append(f"{p.resolve()}:{file_sha256(p)}")
        except OSError:
            csv_signature_parts.append(str(p))
    else:
        csv_signature_parts.append(csv_path)

excel_signature = ""
if excel_path and Path(excel_path).expanduser().is_file():
    try:
        excel_signature = file_sha256(Path(excel_path).expanduser())
    except OSError:
        pass

signature = "|".join(
    csv_signature_parts
    + [str(excel_path), excel_signature, _uploaded_hash(config_upload)]
)
if st.session_state.get("local_signature") != signature:
    st.session_state["local_signature"] = signature
    st.session_state.pop("preflight", None)
    st.session_state.pop("preflight_excel_sha", None)
    st.session_state.pop("batch_sources", None)
    st.session_state.pop("batch_month", None)
    st.session_state.pop("done_result", None)

report = st.session_state.get("preflight")
preflight_state = build_local_ui_state(csv_paths, excel_path, report is not None, False)

st.markdown('<div class="step"><div class="step-title">3. まとめて事前チェック</div>', unsafe_allow_html=True)
st.caption(preflight_state.preflight_hint)
if st.button(
    "選択したCSVをまとめてチェック",
    type="primary",
    use_container_width=True,
    disabled=not preflight_state.can_preflight,
    key="preflight_button",
):
    try:
        with st.spinner("CSV同士の年月・重複と、Excelの年度・転記先・数式を確認しています…"):
            config = _load_config(config_upload)
            batch = load_same_month_batch(csv_paths, config)
            engine = LocalWorkbookEngine(config)
            target = Path(excel_path).expanduser().resolve()
            st.session_state["preflight"] = engine.preflight_file(batch.data, target)
            st.session_state["preflight_excel_sha"] = file_sha256(target)
            st.session_state["batch_sources"] = batch.sources
            st.session_state["batch_month"] = (batch.year, batch.month)
        st.rerun()
    except Exception as exc:
        st.session_state.pop("preflight", None)
        st.session_state.pop("preflight_excel_sha", None)
        st.session_state.pop("batch_sources", None)
        st.error(f"事前チェックで停止しました：{exc}")

report = st.session_state.get("preflight")
if report:
    year, month = st.session_state["batch_month"]
    sources = st.session_state.get("batch_sources", ())
    st.success(f"{year}年{month}月のバッチとして事前チェック OK")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("CSVファイル", f"{len(sources)}個")
    m2.metric("追加件数", f"{report.record_count:,}")
    m3.metric("転記開始行", report.target_start_row)
    m4.metric("保護数式", f"{report.formula_count:,}")

    st.markdown("**今回の内訳**")
    for source in sources:
        st.write(
            f"- **{month}月 ｜ {source.label}** — {source.record_count:,}件 "
            f"({source.min_date} ～ {source.max_date})"
        )

    st.markdown(
        f"""
        <div class="okbox">
          対象月: <b>{year}年{month}月</b><br>
          CSV全体期間: <b>{report.min_date} ～ {report.max_date}</b><br>
          Excel最終日: <b>{report.existing_last_date or 'データなし'}</b><br>
          転記行: <b>{report.target_start_row} ～ {report.target_end_row}</b><br>
          確認済み: CSV間重複なし / 既存値上書きなし / 数式セルへの書込みなし
        </div>
        """,
        unsafe_allow_html=True,
    )
    for warning in report.warnings:
        st.warning(warning)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="step"><div class="step-title">4. 一括更新を実行</div>', unsafe_allow_html=True)
confirmed = st.checkbox(
    "更新対象Excelと、上記のCSV内訳を確認しました",
    key="confirmed_batch",
    disabled=report is None,
)
execute_state = build_local_ui_state(csv_paths, excel_path, report is not None, confirmed)
st.caption(execute_state.execute_hint)
st.warning(
    "すべてのCSVを結合・検証してから1回だけExcelを更新します。"
    "更新前の原本は `_backup` フォルダへ自動保存します。"
)
if st.button(
    "このExcelを一括更新する",
    type="primary",
    use_container_width=True,
    disabled=not execute_state.can_execute,
    key="execute_button",
):
    try:
        with st.spinner("バックアップ → 一括転記 → 数式照合 → 値照合 → Excel更新中…"):
            config = _load_config(config_upload)
            batch = load_same_month_batch(csv_paths, config)
            expected_month = st.session_state.get("batch_month")
            if expected_month != (batch.year, batch.month):
                raise RuntimeError("事前チェック後にCSVの対象月が変わっています。再チェックしてください。")
            engine = LocalWorkbookEngine(config)
            result = engine.process_in_place(
                csv_data=batch.data,
                excel_path=excel_path,
                expected_sha256=st.session_state["preflight_excel_sha"],
            )
            st.session_state["done_result"] = result
            st.session_state["done_file_count"] = len(batch.sources)
            st.session_state["done_month"] = (batch.year, batch.month)
            st.session_state.pop("preflight", None)
            st.session_state.pop("preflight_excel_sha", None)
        st.rerun()
    except Exception as exc:
        st.error(f"更新処理を停止しました：{exc}")

if st.session_state.get("done_result"):
    result = st.session_state["done_result"]
    done_year, done_month = st.session_state["done_month"]
    st.success(
        f"更新完了：{done_year}年{done_month}月のCSV "
        f"{st.session_state['done_file_count']}個・合計{result.record_count:,}件を同じExcelへ追加しました。"
    )
    st.write(f"**更新したExcel:** `{result.excel_path}`")
    st.write(f"**バックアップ:** `{result.backup_path}`")
    st.write(f"**転記行:** {result.target_start_row} ～ {result.target_end_row}")
    st.write(f"**保護確認した数式:** {result.formula_count:,}セル")
st.markdown('</div>', unsafe_allow_html=True)

st.divider()
st.caption(
    "Windowsでは `run.bat` で起動できます。手動起動は `py -m streamlit run app.py`。"
    "CSV・Excelの読込、バックアップ、Excel更新はローカルPC上で実行されます。"
)
