from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import re
from typing import Any

from .config import AppConfig, ColumnSpec
from .csv_loader import CsvRecord, normalize_key_part


XL_CELL_TYPE_FORMULAS = -4123
MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3


def _import_com():
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "pywin32 がインストールされていません。setup.bat を実行してください。"
        ) from e
    return pythoncom, win32com.client


@contextmanager
def excel_app():
    pythoncom, win32 = _import_com()
    pythoncom.CoInitialize()
    app = None
    try:
        app = win32.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        app.ScreenUpdating = False
        app.EnableEvents = False
        try:
            app.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
        except Exception:
            pass
        yield app
    finally:
        if app is not None:
            try:
                app.DisplayAlerts = False
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def open_workbook(app, path: str | Path, read_only: bool):
    path = str(Path(path).resolve())
    wb = app.Workbooks.Open(
        path,
        UpdateLinks=0,
        ReadOnly=read_only,
        IgnoreReadOnlyRecommended=True,
        AddToMru=False,
    )
    return wb


def get_sheet(workbook, sheet_name: str):
    try:
        return workbook.Worksheets(sheet_name)
    except Exception as e:
        raise ValueError(f"Excelにシート '{sheet_name}' がありません。") from e


def _flatten_range_values(value: Any, count: int) -> list[Any]:
    if count == 1:
        return [value]
    if isinstance(value, tuple):
        out = []
        for item in value:
            if isinstance(item, tuple):
                out.append(item[0] if item else None)
            else:
                out.append(item)
        return out
    return [value]


def excel_value_to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d", "%Y年%m月%d日"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
    return None


def normalized_excel_value(value: Any, spec: ColumnSpec) -> str:
    if value is None or value == "":
        return ""
    if spec.data_type == "date":
        d = excel_value_to_date(value)
        if d is None:
            return f"<INVALID_DATE:{value}>"
        return d.isoformat()
    if spec.data_type == "number":
        try:
            return format(Decimal(str(value)).normalize(), "f")
        except Exception:
            return f"<INVALID_NUMBER:{value}>"
    return str(value).strip()


def formula_snapshot(workbook) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for ws in workbook.Worksheets:
        try:
            formula_cells = ws.UsedRange.SpecialCells(XL_CELL_TYPE_FORMULAS)
        except Exception:
            continue
        for area in formula_cells.Areas:
            for cell in area.Cells:
                address = cell.Address(False, False)
                snapshot[f"{ws.Name}!{address}"] = str(cell.Formula)
    return snapshot


def formula_diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    keys = sorted(set(before) | set(after))
    diff: list[str] = []
    for key in keys:
        if before.get(key) != after.get(key):
            diff.append(f"{key}: BEFORE={before.get(key)!r} / AFTER={after.get(key)!r}")
    return diff


def read_date_column(ws, config: AppConfig) -> list[Any]:
    start = config.data_start_row
    end = config.data_end_row
    rng = ws.Range(f"{config.date_excel_column}{start}:{config.date_excel_column}{end}")
    return _flatten_range_values(rng.Value2, end - start + 1)


def existing_state(ws, config: AppConfig) -> dict[str, Any]:
    values = read_date_column(ws, config)
    last_offset = -1
    for i, value in enumerate(values):
        if value not in (None, ""):
            last_offset = i

    if last_offset < 0:
        return {"last_row": config.data_start_row - 1, "last_date": None, "has_gap": False}

    last_row = config.data_start_row + last_offset
    used_values = values[: last_offset + 1]
    has_gap = any(v in (None, "") for v in used_values)
    last_date = excel_value_to_date(used_values[-1])
    if last_date is None:
        raise ValueError(
            f"Excel {config.sheet_name}!{config.date_excel_column}{last_row} の日付を解釈できません。"
        )
    return {"last_row": last_row, "last_date": last_date, "has_gap": has_gap}


def validate_target_rows_empty(ws, config: AppConfig, start_row: int, end_row: int) -> None:
    if start_row > end_row:
        return
    for spec in config.columns:
        rng = ws.Range(f"{spec.excel_column}{start_row}:{spec.excel_column}{end_row}")
        values = _flatten_range_values(rng.Value2, end_row - start_row + 1)
        for offset, value in enumerate(values):
            row = start_row + offset
            cell = ws.Range(f"{spec.excel_column}{row}")
            try:
                has_formula = bool(cell.HasFormula)
            except Exception:
                has_formula = str(cell.Formula).startswith("=")
            if has_formula:
                raise ValueError(
                    f"転記先 {config.sheet_name}!{spec.excel_column}{row} に数式があります。数式セルには絶対に書き込みません。"
                )
            if value not in (None, ""):
                raise ValueError(
                    f"転記先 {config.sheet_name}!{spec.excel_column}{row} に既存値があります。上書きを防止するため停止します。"
                )


def read_existing_keys(ws, config: AppConfig, last_row: int) -> set[tuple[str, ...]]:
    if last_row < config.data_start_row:
        return set()
    key_specs = [config.spec_by_csv_header(h) for h in config.key_csv_headers]
    result: set[tuple[str, ...]] = set()
    for row in range(config.data_start_row, last_row + 1):
        parts = []
        for spec in key_specs:
            value = ws.Range(f"{spec.excel_column}{row}").Value2
            parts.append(normalized_excel_value(value, spec))
        result.add(tuple(parts))
    return result


def validate_workbook_fiscal_year(ws, config: AppConfig, expected_fiscal_year: int) -> None:
    if not config.workbook_fiscal_year_cell:
        return
    value = ws.Range(config.workbook_fiscal_year_cell).Value
    text = "" if value is None else str(value)
    match = re.search(r"(19|20)\d{2}", text)
    if not match:
        raise ValueError(
            f"年度確認セル {config.workbook_fiscal_year_cell} から年度を読み取れません: {text!r}"
        )
    workbook_year = int(match.group(0))
    if workbook_year != expected_fiscal_year:
        raise ValueError(
            f"CSVは {expected_fiscal_year}年度ですが、Excelの年度確認セルは {workbook_year}年度です。転記先ファイルを確認してください。"
        )


def to_excel_value(value: Any, spec: ColumnSpec) -> Any:
    if value is None:
        return None
    if spec.data_type == "date":
        return datetime(value.year, value.month, value.day)
    if spec.data_type == "number":
        return float(value)
    return str(value)


def write_records(ws, config: AppConfig, records: tuple[CsvRecord, ...], start_row: int) -> tuple[int, int]:
    if not records:
        return start_row, start_row - 1
    end_row = start_row + len(records) - 1
    for spec in config.columns:
        matrix = tuple((to_excel_value(record.values[spec.csv_header], spec),) for record in records)
        rng = ws.Range(f"{spec.excel_column}{start_row}:{spec.excel_column}{end_row}")
        rng.Value = matrix
    return start_row, end_row


def validate_written_values(ws, config: AppConfig, records: tuple[CsvRecord, ...], start_row: int) -> list[str]:
    errors: list[str] = []
    for offset, record in enumerate(records):
        row = start_row + offset
        for spec in config.columns:
            actual = ws.Range(f"{spec.excel_column}{row}").Value2
            actual_norm = normalized_excel_value(actual, spec)
            expected_norm = normalize_key_part(record.values[spec.csv_header], spec)
            if actual_norm != expected_norm:
                errors.append(
                    f"{config.sheet_name}!{spec.excel_column}{row}: expected={expected_norm!r}, actual={actual_norm!r}"
                )
                if len(errors) >= 50:
                    return errors
    return errors
