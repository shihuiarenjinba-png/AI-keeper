from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_renders_main_local_actions():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15).run()

    assert not at.exception, [str(e) for e in at.exception]

    buttons = {button.label: button for button in at.button}
    expected = {
        "CSV参照",
        "Excel参照",
        "選択したCSVをまとめてチェック",
        "このExcelを一括更新する",
    }
    assert expected.issubset(buttons.keys())

    assert buttons["選択したCSVをまとめてチェック"].disabled is True
    assert buttons["このExcelを一括更新する"].disabled is True


def test_streamlit_app_is_windows_local_path_first():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15).run()

    assert not at.exception, [str(e) for e in at.exception]

    text_areas = list(at.text_area)
    text_inputs = list(at.text_input)
    assert any(item.key == "csv_paths_text" for item in text_areas)
    assert any(item.key == "excel_path" for item in text_inputs)

    # CSV / Excel 本体のブラウザアップロードUIは置かない。
    uploader_labels = [item.label for item in at.file_uploader]
    assert "同じ月のCSVを複数アップロード" not in uploader_labels
    assert "Excelをアップロード" not in uploader_labels


def test_streamlit_app_shows_clear_errors_for_unsupported_existing_files(tmp_path: Path):
    unsupported_csv = tmp_path / "売上 データ.txt"
    unsupported_excel = tmp_path / "帳票.xls"
    unsupported_csv.write_text("dummy", encoding="utf-8")
    unsupported_excel.write_bytes(b"dummy")

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15).run()
    at.text_area(key="csv_paths_text").set_value(str(unsupported_csv))
    at.text_input(key="excel_path").set_value(str(unsupported_excel))
    at.run()

    errors = [item.value for item in at.error]
    assert any("このファイル形式には対応していません（CSVのみ）" in item for item in errors)
    assert any("このファイル形式には対応していません（.xlsx / .xlsm のみ）" in item for item in errors)
