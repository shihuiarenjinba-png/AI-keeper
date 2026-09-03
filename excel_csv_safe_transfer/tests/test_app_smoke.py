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
