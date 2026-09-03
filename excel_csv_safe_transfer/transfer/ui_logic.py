from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LocalUiState:
    csv_ok: bool
    excel_ok: bool
    preflight_ok: bool
    confirmed: bool

    @property
    def can_preflight(self) -> bool:
        return self.csv_ok and self.excel_ok

    @property
    def can_execute(self) -> bool:
        return self.can_preflight and self.preflight_ok and self.confirmed

    @property
    def preflight_hint(self) -> str:
        missing: list[str] = []
        if not self.csv_ok:
            missing.append("CSV")
        if not self.excel_ok:
            missing.append("更新対象Excel")
        if not missing:
            return "準備完了です。事前チェックを実行してください。"
        return "先に " + " と ".join(missing) + " を選択してください。"

    @property
    def execute_hint(self) -> str:
        if not self.can_preflight:
            return "CSVと更新対象Excelを選択すると実行準備に進めます。"
        if not self.preflight_ok:
            return "先に事前チェックを実行してください。"
        if not self.confirmed:
            return "確認チェックを入れると更新実行できます。"
        return "更新実行できます。"


def _valid_csv_paths(csv_paths: str | Iterable[str]) -> bool:
    if isinstance(csv_paths, str):
        paths = [csv_paths] if csv_paths else []
    else:
        paths = [p for p in csv_paths if p]
    if not paths:
        return False
    return all(
        Path(p).expanduser().is_file() and Path(p).suffix.lower() == ".csv"
        for p in paths
    )


def build_local_ui_state(
    csv_paths: str | Iterable[str],
    excel_path: str,
    preflight_ok: bool,
    confirmed: bool,
) -> LocalUiState:
    excel = Path(excel_path).expanduser() if excel_path else None
    return LocalUiState(
        csv_ok=_valid_csv_paths(csv_paths),
        excel_ok=bool(
            excel
            and excel.is_file()
            and excel.suffix.lower() in {".xlsx", ".xlsm"}
        ),
        preflight_ok=bool(preflight_ok),
        confirmed=bool(confirmed),
    )
