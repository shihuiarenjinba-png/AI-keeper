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
        "事前チェックを実行",
        "このExcelを更新する",
    }
    assert expected.issubset(buttons.keys())

    assert buttons["事前チェックを実行"].disabled is True
    assert buttons["このExcelを更新する"].disabled is True


def test_streamlit_app_shows_local_and_browser_modes():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15).run()

    assert not at.exception, [str(e) for e in at.exception]
    tab_labels = [tab.label for tab in at.tabs]
    assert "ローカル更新" in tab_labels
    assert "ブラウザ確認用" in tab_labels
