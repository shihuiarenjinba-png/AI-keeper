from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import getpass
import json
import os
import shutil
import socket
import uuid
from typing import Any

from .config import AppConfig
from .csv_loader import file_sha256, load_csv
from .excel_com import (
    excel_app,
    existing_state,
    formula_diff,
    formula_snapshot,
    get_sheet,
    open_workbook,
    read_existing_keys,
    validate_target_rows_empty,
    validate_workbook_fiscal_year,
    validate_written_values,
    write_records,
)


@dataclass(frozen=True)
class PreflightPlan:
    csv_path: str
    excel_path: str
    config_path: str
    csv_sha256: str
    excel_sha256: str
    config_sha256: str
    csv_encoding: str
    record_count: int
    min_date: str
    max_date: str
    fiscal_year: int
    existing_last_row: int
    existing_last_date: str | None
    target_start_row: int
    target_end_row: int
    formula_count: int
    created_at: str

    def summary_text(self) -> str:
        last_date = self.existing_last_date or "（データなし）"
        return (
            "【事前検査 OK】\n"
            f"CSV件数　　　　: {self.record_count:,} 件\n"
            f"CSV期間　　　　: {self.min_date} ～ {self.max_date}\n"
            f"対象年度　　　 : {self.fiscal_year}年度\n"
            f"既存Excel最終日: {last_date}\n"
            f"転記予定行　　 : {self.target_start_row} ～ {self.target_end_row}\n"
            f"保護対象数式　 : {self.formula_count:,} セル\n"
            f"CSV文字コード　: {self.csv_encoding}\n\n"
            "・既存値への上書きなし\n"
            "・転記先数式セルなし\n"
            "・CSV内重複キーなし\n"
            "・Excel既存データとの重複キーなし\n"
            "・転記後に全数式を再照合します\n"
        )


class TransferService:
    def preflight(self, csv_path: str, excel_path: str, config_path: str) -> PreflightPlan:
        csv_p = Path(csv_path).resolve()
        excel_p = Path(excel_path).resolve()
        config_p = Path(config_path).resolve()

        self._validate_extensions(csv_p, excel_p, config_p)
        self._assert_not_locked(excel_p)

        config = AppConfig.load(config_p)
        csv_data = load_csv(csv_p, config)
        excel_hash = file_sha256(excel_p)
        config_hash = file_sha256(config_p)

        with excel_app() as app:
            wb = open_workbook(app, excel_p, read_only=True)
            try:
                ws = get_sheet(wb, config.sheet_name)
                validate_workbook_fiscal_year(ws, config, csv_data.fiscal_year)
                state = existing_state(ws, config)
                if state["has_gap"]:
                    raise ValueError(
                        f"Excelの日付列 {config.date_excel_column} に途中の空欄があります。追記位置を誤る恐れがあるため停止します。"
                    )

                last_row = int(state["last_row"])
                last_date = state["last_date"]
                start_row = last_row + 1
                end_row = start_row + len(csv_data.records) - 1

                if end_row > config.data_end_row:
                    raise ValueError(
                        f"Excelの転記可能行が不足しています。必要最終行={end_row}, 設定上限={config.data_end_row}。安全のため自動で行挿入はしません。"
                    )

                if (
                    config.require_strictly_after_last_date
                    and last_date is not None
                    and csv_data.min_date <= last_date
                ):
                    raise ValueError(
                        f"Excel最終日 {last_date} に対し、CSV開始日 {csv_data.min_date} が後の日付ではありません。過去データの上書き・重複を防ぐため停止します。"
                    )

                validate_target_rows_empty(ws, config, start_row, end_row)
                existing_keys = read_existing_keys(ws, config, last_row)
                duplicate_keys = [r.key for r in csv_data.records if r.key in existing_keys]
                if duplicate_keys:
                    raise ValueError(
                        f"Excel既存データと重複するキーがあります。例: {duplicate_keys[:5]}。二重転記を防ぐため停止します。"
                    )
                formulas = formula_snapshot(wb)
            finally:
                wb.Close(SaveChanges=False)

        return PreflightPlan(
            csv_path=str(csv_p), excel_path=str(excel_p), config_path=str(config_p),
            csv_sha256=csv_data.sha256, excel_sha256=excel_hash, config_sha256=config_hash,
            csv_encoding=csv_data.encoding, record_count=len(csv_data.records),
            min_date=csv_data.min_date.isoformat(), max_date=csv_data.max_date.isoformat(),
            fiscal_year=csv_data.fiscal_year, existing_last_row=last_row,
            existing_last_date=last_date.isoformat() if last_date else None,
            target_start_row=start_row, target_end_row=end_row,
            formula_count=len(formulas), created_at=datetime.now().isoformat(timespec="seconds"),
        )

    def execute(self, plan: PreflightPlan) -> dict[str, Any]:
        csv_p = Path(plan.csv_path)
        excel_p = Path(plan.excel_path)
        config_p = Path(plan.config_path)

        self._assert_not_locked(excel_p)
        self._assert_unchanged(csv_p, plan.csv_sha256, "CSV")
        self._assert_unchanged(excel_p, plan.excel_sha256, "Excel")
        self._assert_unchanged(config_p, plan.config_sha256, "設定ファイル")

        config = AppConfig.load(config_p)
        csv_data = load_csv(csv_p, config)
        if len(csv_data.records) != plan.record_count:
            raise RuntimeError("事前検査後にCSV件数が変わっています。処理を中止します。")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = excel_p.parent / config.backup_subfolder
        log_dir = excel_p.parent / config.log_subfolder
        backup_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        backup_path = backup_dir / f"{timestamp}_{excel_p.name}"
        shutil.copy2(excel_p, backup_path)
        temp_path = excel_p.parent / f".__transfer_tmp_{uuid.uuid4().hex}{excel_p.suffix}"
        shutil.copy2(excel_p, temp_path)

        log: dict[str, Any] = {
            "status": "STARTED",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "user": getpass.getuser(),
            "computer": socket.gethostname(),
            "csv_path": str(csv_p),
            "excel_path": str(excel_p),
            "config_path": str(config_p),
            "backup_path": str(backup_path),
            "record_count": len(csv_data.records),
            "date_range": [csv_data.min_date.isoformat(), csv_data.max_date.isoformat()],
            "fiscal_year": csv_data.fiscal_year,
            "csv_sha256": plan.csv_sha256,
            "excel_sha256_before": plan.excel_sha256,
            "config_sha256": plan.config_sha256,
            "target_rows": [plan.target_start_row, plan.target_end_row],
        }

        try:
            with excel_app() as app:
                wb = open_workbook(app, temp_path, read_only=False)
                try:
                    ws = get_sheet(wb, config.sheet_name)
                    validate_workbook_fiscal_year(ws, config, csv_data.fiscal_year)
                    state = existing_state(ws, config)
                    if state["has_gap"]:
                        raise RuntimeError("実行時検査: Excel日付列に空欄ギャップがあります。")
                    if int(state["last_row"]) != plan.existing_last_row:
                        raise RuntimeError("実行時検査: Excel最終行が事前検査時と一致しません。")

                    start_row = int(state["last_row"]) + 1
                    end_row = start_row + len(csv_data.records) - 1
                    if start_row != plan.target_start_row or end_row != plan.target_end_row:
                        raise RuntimeError("実行時検査: 転記予定行が事前検査時と一致しません。")

                    validate_target_rows_empty(ws, config, start_row, end_row)
                    existing_keys = read_existing_keys(ws, config, int(state["last_row"]))
                    overlap = [r.key for r in csv_data.records if r.key in existing_keys]
                    if overlap:
                        raise RuntimeError(f"実行時検査: 既存Excelとの重複キーを検出しました: {overlap[:5]}")

                    formulas_before = formula_snapshot(wb)
                    if len(formulas_before) != plan.formula_count:
                        raise RuntimeError("実行時検査: 数式セル数が事前検査時と一致しません。")

                    write_records(ws, config, csv_data.records, start_row)
                    diff = formula_diff(formulas_before, formula_snapshot(wb))
                    if diff:
                        raise RuntimeError("転記直後に数式変更を検出しました。処理を中止します。\n" + "\n".join(diff[:20]))
                    wb.Save()
                finally:
                    wb.Close(SaveChanges=False)

                wb2 = open_workbook(app, temp_path, read_only=True)
                try:
                    ws2 = get_sheet(wb2, config.sheet_name)
                    formulas_after_save = formula_snapshot(wb2)
                    diff2 = formula_diff(formulas_before, formulas_after_save)
                    if diff2:
                        raise RuntimeError("保存後の再検証で数式変更を検出しました。原本は変更しません。\n" + "\n".join(diff2[:20]))
                    value_errors = validate_written_values(ws2, config, csv_data.records, start_row)
                    if value_errors:
                        raise RuntimeError("保存後の値照合で不一致を検出しました。原本は変更しません。\n" + "\n".join(value_errors[:20]))
                finally:
                    wb2.Close(SaveChanges=False)

            self._assert_unchanged(excel_p, plan.excel_sha256, "原本Excel")
            os.replace(temp_path, excel_p)

            log["status"] = "SUCCESS"
            log["finished_at"] = datetime.now().isoformat(timespec="seconds")
            log["excel_sha256_after"] = file_sha256(excel_p)
            log["formula_count_after"] = len(formulas_after_save)
            log_path = self._write_log(log_dir, timestamp, log)
            return {
                "status": "SUCCESS",
                "record_count": len(csv_data.records),
                "backup_path": str(backup_path),
                "log_path": str(log_path),
                "target_start_row": start_row,
                "target_end_row": end_row,
                "formula_count": len(formulas_after_save),
            }
        except Exception as e:
            log["status"] = "FAILED"
            log["finished_at"] = datetime.now().isoformat(timespec="seconds")
            log["error"] = str(e)
            try:
                self._write_log(log_dir, timestamp, log)
            except Exception:
                pass
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    @staticmethod
    def _validate_extensions(csv_p: Path, excel_p: Path, config_p: Path) -> None:
        if csv_p.suffix.lower() != ".csv":
            raise ValueError("転記元は .csv ファイルを指定してください。")
        if excel_p.suffix.lower() not in {".xlsx", ".xlsm", ".xlsb", ".xls"}:
            raise ValueError("転記先は Excel ファイルを指定してください。")
        if config_p.suffix.lower() != ".json":
            raise ValueError("設定ファイルは .json を指定してください。")
        for p in (csv_p, excel_p, config_p):
            if not p.is_file():
                raise FileNotFoundError(f"ファイルが見つかりません: {p}")

    @staticmethod
    def _assert_unchanged(path: Path, expected_hash: str, label: str) -> None:
        if file_sha256(path) != expected_hash:
            raise RuntimeError(
                f"{label} が事前検査後に変更されています。安全のため再度「事前検査」を実行してください。"
            )

    @staticmethod
    def _assert_not_locked(excel_path: Path) -> None:
        lock_path = excel_path.parent / f"~${excel_path.name}"
        if lock_path.exists():
            raise RuntimeError(
                f"Excelファイルが開かれている可能性があります: {excel_path.name}\n対象Excelを閉じてから実行してください。"
            )

    @staticmethod
    def _write_log(log_dir: Path, timestamp: str, log: dict[str, Any]) -> Path:
        log_path = log_dir / f"transfer_{timestamp}.json"
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return log_path
