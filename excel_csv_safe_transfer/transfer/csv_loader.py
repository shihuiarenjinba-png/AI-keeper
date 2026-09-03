from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import hashlib
from typing import Any

from .config import AppConfig, ColumnSpec


ENCODING_CANDIDATES = ("utf-8-sig", "cp932", "shift_jis", "utf-8")


@dataclass(frozen=True)
class CsvRecord:
    csv_row_number: int
    values: dict[str, Any]
    record_date: date
    key: tuple[str, ...]


@dataclass(frozen=True)
class CsvData:
    path: Path
    encoding: str
    headers: tuple[str, ...]
    records: tuple[CsvRecord, ...]
    min_date: date
    max_date: date
    fiscal_year: int
    sha256: str


def file_sha256(path: str | Path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_text(path: Path) -> tuple[str, str]:
    last_error: Exception | None = None
    raw = path.read_bytes()
    for enc in ENCODING_CANDIDATES:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError as e:
            last_error = e
    raise ValueError(f"CSVの文字コードを判定できませんでした: {last_error}")


def _parse_date(text: str, formats: tuple[str, ...]) -> date:
    value = text.strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"日付形式を解釈できません: {text!r}")


def _parse_number(text: str) -> Decimal:
    value = text.strip().replace(",", "")
    if value == "":
        raise ValueError("数値が空欄です。")

    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = "-" + value[1:-1]

    for mark in ("¥", "￥", "$"):
        value = value.replace(mark, "")

    try:
        return Decimal(value)
    except InvalidOperation as e:
        raise ValueError(f"数値として解釈できません: {text!r}") from e


def parse_value(raw: str | None, spec: ColumnSpec, config: AppConfig) -> Any:
    text = "" if raw is None else str(raw)
    if text.strip() == "":
        if spec.required:
            raise ValueError(f"必須項目 '{spec.csv_header}' が空欄です。")
        return None

    if spec.data_type == "text":
        return text.strip()
    if spec.data_type == "number":
        return _parse_number(text)
    if spec.data_type == "date":
        return _parse_date(text, config.date_formats)
    raise ValueError(f"未対応の型です: {spec.data_type}")


def normalize_key_part(value: Any, spec: ColumnSpec) -> str:
    if value is None:
        return ""
    if spec.data_type == "date":
        return value.isoformat()
    if spec.data_type == "number":
        return format(value.normalize(), "f")
    return str(value).strip()


def fiscal_year_for(d: date, start_month: int) -> int:
    return d.year if d.month >= start_month else d.year - 1


def load_csv(path: str | Path, config: AppConfig) -> CsvData:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"CSVが見つかりません: {path}")

    text, encoding = _read_text(path)
    reader = csv.DictReader(text.splitlines())

    if reader.fieldnames is None:
        raise ValueError("CSVヘッダーが見つかりません。")

    headers = tuple(h.strip() for h in reader.fieldnames)
    required_headers = {c.csv_header for c in config.columns}
    missing = sorted(required_headers - set(headers))
    if missing:
        raise ValueError(f"CSVに必要な列がありません: {', '.join(missing)}")

    records: list[CsvRecord] = []
    seen_keys: dict[tuple[str, ...], int] = {}
    previous_date: date | None = None

    for row_number, row in enumerate(reader, start=2):
        if all((v is None or str(v).strip() == "") for v in row.values()):
            continue

        parsed: dict[str, Any] = {}
        try:
            for spec in config.columns:
                parsed[spec.csv_header] = parse_value(
                    row.get(spec.csv_header), spec, config
                )
        except Exception as e:
            raise ValueError(f"CSV {row_number}行目: {e}") from e

        record_date = parsed[config.date_csv_header]
        if not isinstance(record_date, date):
            raise ValueError(f"CSV {row_number}行目: 日付列の解釈に失敗しました。")

        if (
            config.require_date_ascending
            and previous_date is not None
            and record_date < previous_date
        ):
            raise ValueError(
                f"CSV {row_number}行目: 日付順が逆転しています "
                f"({record_date} < {previous_date})。安全のため停止します。"
            )
        previous_date = record_date

        key_parts: list[str] = []
        for key_header in config.key_csv_headers:
            spec = config.spec_by_csv_header(key_header)
            key_parts.append(normalize_key_part(parsed[key_header], spec))
        key = tuple(key_parts)

        if key in seen_keys:
            raise ValueError(
                f"CSV内に重複キーがあります。{seen_keys[key]}行目 と {row_number}行目: {key}"
            )
        seen_keys[key] = row_number

        records.append(
            CsvRecord(
                csv_row_number=row_number,
                values=parsed,
                record_date=record_date,
                key=key,
            )
        )

    if not records:
        raise ValueError("CSVに転記対象データがありません。")

    fiscal_years = {
        fiscal_year_for(r.record_date, config.fiscal_year_start_month)
        for r in records
    }
    if len(fiscal_years) != 1:
        raise ValueError(
            "CSV内に複数年度のデータが混在しています。年度ごとにCSVを分けてください。"
        )

    dates = [r.record_date for r in records]
    return CsvData(
        path=path,
        encoding=encoding,
        headers=headers,
        records=tuple(records),
        min_date=min(dates),
        max_date=max(dates),
        fiscal_year=next(iter(fiscal_years)),
        sha256=file_sha256(path),
    )
