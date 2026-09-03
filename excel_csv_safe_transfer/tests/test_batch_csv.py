from pathlib import Path

import pytest

from transfer.batch_csv import load_same_month_batch
from transfer.config import AppConfig


ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text(
        "日付,伝票番号,数量,金額\n" + "\n".join(rows) + "\n",
        encoding="utf-8-sig",
    )


def test_same_month_multiple_csv_are_merged(tmp_path: Path):
    config = AppConfig.load(ROOT / "config_example.json")
    tokyo = tmp_path / "2026_09_東京.csv"
    osaka = tmp_path / "2026_09_大阪.csv"
    _write_csv(tokyo, ["2026/09/01,T1,1,100", "2026/09/02,T2,2,200"])
    _write_csv(osaka, ["2026/09/01,O1,3,300", "2026/09/03,O2,4,400"])

    batch = load_same_month_batch([str(tokyo), str(osaka)], config)

    assert (batch.year, batch.month) == (2026, 9)
    assert len(batch.sources) == 2
    assert len(batch.data.records) == 4
    assert batch.data.min_date.isoformat() == "2026-09-01"
    assert batch.data.max_date.isoformat() == "2026-09-03"
    assert [r.record_date.isoformat() for r in batch.data.records] == sorted(
        r.record_date.isoformat() for r in batch.data.records
    )


def test_mixed_months_are_rejected(tmp_path: Path):
    config = AppConfig.load(ROOT / "config_example.json")
    sep = tmp_path / "2026_09_東京.csv"
    oct_ = tmp_path / "2026_10_大阪.csv"
    _write_csv(sep, ["2026/09/01,T1,1,100"])
    _write_csv(oct_, ["2026/10/01,O1,1,100"])

    with pytest.raises(ValueError, match="同じ年月"):
        load_same_month_batch([str(sep), str(oct_)], config)


def test_duplicate_key_across_csvs_is_rejected(tmp_path: Path):
    config = AppConfig.load(ROOT / "config_example.json")
    a = tmp_path / "2026_09_東京.csv"
    b = tmp_path / "2026_09_大阪.csv"
    _write_csv(a, ["2026/09/01,DUP1,1,100"])
    _write_csv(b, ["2026/09/01,DUP1,2,200"])

    with pytest.raises(ValueError, match="複数CSV間で重複キー"):
        load_same_month_batch([str(a), str(b)], config)
