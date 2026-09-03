from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any


@dataclass(frozen=True)
class ColumnSpec:
    csv_header: str
    excel_column: str
    data_type: str
    required: bool = True


@dataclass(frozen=True)
class AppConfig:
    sheet_name: str
    data_start_row: int
    data_end_row: int
    date_csv_header: str
    date_excel_column: str
    key_csv_headers: tuple[str, ...]
    fiscal_year_start_month: int
    require_date_ascending: bool
    require_strictly_after_last_date: bool
    workbook_fiscal_year_cell: str | None
    date_formats: tuple[str, ...]
    backup_subfolder: str
    log_subfolder: str
    columns: tuple[ColumnSpec, ...]

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))

        columns = tuple(
            ColumnSpec(
                csv_header=str(item["csv_header"]).strip(),
                excel_column=str(item["excel_column"]).strip().upper(),
                data_type=str(item.get("type", "text")).strip().lower(),
                required=bool(item.get("required", True)),
            )
            for item in data["columns"]
        )

        config = cls(
            sheet_name=str(data["sheet_name"]).strip(),
            data_start_row=int(data["data_start_row"]),
            data_end_row=int(data["data_end_row"]),
            date_csv_header=str(data["date_csv_header"]).strip(),
            date_excel_column=str(data["date_excel_column"]).strip().upper(),
            key_csv_headers=tuple(str(x).strip() for x in data["key_csv_headers"]),
            fiscal_year_start_month=int(data.get("fiscal_year_start_month", 4)),
            require_date_ascending=bool(data.get("require_date_ascending", True)),
            require_strictly_after_last_date=bool(
                data.get("require_strictly_after_last_date", True)
            ),
            workbook_fiscal_year_cell=(
                str(data["workbook_fiscal_year_cell"]).strip()
                if data.get("workbook_fiscal_year_cell")
                else None
            ),
            date_formats=tuple(
                data.get("date_formats", ["%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"])
            ),
            backup_subfolder=str(data.get("backup_subfolder", "_backup")),
            log_subfolder=str(data.get("log_subfolder", "_logs")),
            columns=columns,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.sheet_name:
            raise ValueError("sheet_name が空です。")
        if self.data_start_row < 1 or self.data_end_row < self.data_start_row:
            raise ValueError("data_start_row / data_end_row の指定が不正です。")
        if not 1 <= self.fiscal_year_start_month <= 12:
            raise ValueError("fiscal_year_start_month は 1～12 で指定してください。")
        if not self.key_csv_headers:
            raise ValueError(
                "key_csv_headers は必須です。二重転記防止のため、一意キーを指定してください。"
            )
        if not self.columns:
            raise ValueError("columns が空です。")

        headers = [c.csv_header for c in self.columns]
        if len(headers) != len(set(headers)):
            raise ValueError("columns の csv_header に重複があります。")

        excel_cols = [c.excel_column for c in self.columns]
        if len(excel_cols) != len(set(excel_cols)):
            raise ValueError("columns の excel_column に重複があります。")

        supported = {"text", "number", "date"}
        bad_types = [c.data_type for c in self.columns if c.data_type not in supported]
        if bad_types:
            raise ValueError(f"未対応の type があります: {bad_types}")

        if self.date_csv_header not in headers:
            raise ValueError("date_csv_header は columns 内に存在する必要があります。")

        date_spec = self.spec_by_csv_header(self.date_csv_header)
        if date_spec.data_type != "date":
            raise ValueError("date_csv_header に対応する columns の type は date にしてください。")
        if date_spec.excel_column != self.date_excel_column:
            raise ValueError(
                "date_excel_column と、date_csv_header に対応する excel_column が一致していません。"
            )

        for key in self.key_csv_headers:
            if key not in headers:
                raise ValueError(f"key_csv_headers の '{key}' が columns にありません。")

    def spec_by_csv_header(self, header: str) -> ColumnSpec:
        for spec in self.columns:
            if spec.csv_header == header:
                return spec
        raise KeyError(header)

    @property
    def mapped_excel_columns(self) -> tuple[str, ...]:
        return tuple(spec.excel_column for spec in self.columns)
