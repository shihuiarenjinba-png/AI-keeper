from pathlib import Path

from transfer.ui_logic import build_local_ui_state


def test_ui_button_state_flow(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("日付,伝票番号,数量,金額\n2026/09/01,T1,1,100\n", encoding="utf-8")

    excel_path = tmp_path / "sample.xlsx"
    excel_path.write_bytes(b"dummy")

    wrong_path = tmp_path / "sample.txt"
    wrong_path.write_text("dummy", encoding="utf-8")

    cases = [
        ("", "", False, False, False, False),
        (str(csv_path), "", False, False, False, False),
        ("", str(excel_path), False, False, False, False),
        (str(csv_path), str(excel_path), False, False, True, False),
        (str(csv_path), str(excel_path), True, False, True, False),
        (str(csv_path), str(excel_path), True, True, True, True),
        (str(wrong_path), str(excel_path), True, True, False, False),
    ]

    for csv, excel, preflight, confirmed, expected_preflight, expected_execute in cases:
        state = build_local_ui_state(csv, excel, preflight, confirmed)
        assert state.can_preflight is expected_preflight
        assert state.can_execute is expected_execute


def test_ui_hints(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("x", encoding="utf-8")
    excel_path = tmp_path / "sample.xlsx"
    excel_path.write_bytes(b"dummy")

    state = build_local_ui_state("", "", False, False)
    assert "CSV" in state.preflight_hint
    assert "Excel" in state.preflight_hint

    state = build_local_ui_state(str(csv_path), str(excel_path), False, False)
    assert "事前チェック" in state.execute_hint

    state = build_local_ui_state(str(csv_path), str(excel_path), True, False)
    assert "確認チェック" in state.execute_hint

    state = build_local_ui_state(str(csv_path), str(excel_path), True, True)
    assert "更新実行できます" in state.execute_hint
