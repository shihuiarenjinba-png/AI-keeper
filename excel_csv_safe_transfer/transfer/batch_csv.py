from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from .config import AppConfig
from .csv_loader import CsvData, CsvRecord, load_csv


@dataclass(frozen=True)
class BatchSource:
    path: str
    label: str
    record_count: int
    min_date: str
    max_date: str


@dataclass(frozen=True)
class BatchCsv:
    data: CsvData
    sources: tuple[BatchSource, ...]
    year: int
    month: int


def infer_second_label(path: str | Path, year: int, month: int) -> str:
    stem = Path(path).stem
    patterns = [
        rf"{year}[-_ ]?{month:02d}",
        rf"{year}[-_ ]?{month}",
        rf"{month:02d}月",
        rf"{month}月",
    ]
    label = stem
    for pattern in patterns:
        label = re.sub(pattern, "", label, flags=re.IGNORECASE)
    label = re.sub(r"^[\s_\-]+|[\s_\-]+$", "", label)
    return label or stem


def load_same_month_batch(paths: list[str] | tuple[str, ...], config: AppConfig) -> BatchCsv:
    if not paths:
        raise ValueError("CSVが選択されていません。")

    loaded: list[CsvData] = [load_csv(Path(p).expanduser().resolve(), config) for p in paths]

    months = {
        (record.record_date.year, record.record_date.month)
        for csv_data in loaded
        for record in csv_data.records
    }
    if len(months) != 1:
        found = ", ".join(f"{y}-{m:02d}" for y, m in sorted(months))
        raise ValueError(
            "同じバッチには同じ年月のCSVだけを選択してください。"
            f"現在の選択: {found}"
        )
    year, month = next(iter(months))

    fiscal_years = {csv_data.fiscal_year for csv_data in loaded}
    if len(fiscal_years) != 1:
        raise ValueError("選択CSVの年度が一致していません。")

    headers = loaded[0].headers
    for csv_data in loaded[1:]:
        if csv_data.headers != headers:
            raise ValueError(
                f"CSVヘッダーが一致していません: {loaded[0].path.name} / {csv_data.path.name}"
            )

    seen: dict[tuple[str, ...], str] = {}
    records: list[CsvRecord] = []
    for csv_data in loaded:
        for record in csv_data.records:
            if record.key in seen:
                raise ValueError(
                    "複数CSV間で重複キーを検出しました。"
                    f"キー={record.key}, 先={seen[record.key]}, 後={csv_data.path.name}"
                )
            seen[record.key] = csv_data.path.name
            records.append(record)

    records.sort(key=lambda r: (r.record_date, r.key, r.csv_row_number))
    digest = sha256()
    for csv_data in sorted(loaded, key=lambda x: str(x.path)):
        digest.update(str(csv_data.path).encode("utf-8"))
        digest.update(csv_data.sha256.encode("ascii"))

    data = CsvData(
        path=Path(f"batch_{year}_{month:02d}.csv"),
        encoding="multiple",
        headers=headers,
        records=tuple(records),
        min_date=min(r.record_date for r in records),
        max_date=max(r.record_date for r in records),
        fiscal_year=next(iter(fiscal_years)),
        sha256=digest.hexdigest(),
    )
    sources = tuple(
        BatchSource(
            path=str(csv_data.path),
            label=infer_second_label(csv_data.path, year, month),
            record_count=len(csv_data.records),
            min_date=csv_data.min_date.isoformat(),
            max_date=csv_data.max_date.isoformat(),
        )
        for csv_data in loaded
    )
    return BatchCsv(data=data, sources=sources, year=year, month=month)
