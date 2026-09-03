from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import hashlib
import os
import shutil
import tempfile

from .csv_loader import CsvData
from .workbook_engine import WorkbookEngine, PreflightReport


@dataclass(frozen=True)
class InPlaceResult:
    excel_path: str
    backup_path: str
    record_count: int
    formula_count: int
    target_start_row: int
    target_end_row: int
    sha256_before: str
    sha256_after: str


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class LocalWorkbookEngine(WorkbookEngine):
    """既存の検証済みWorkbookEngineに、ローカル実ファイル更新だけを追加する。"""

    def preflight_file(self, csv_data: CsvData, excel_path: str | Path) -> PreflightReport:
        path = Path(excel_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Excelが見つかりません: {path}")
        return self.preflight(csv_data, path.read_bytes(), path.name)

    def process_in_place(
        self,
        csv_data: CsvData,
        excel_path: str | Path,
        expected_sha256: str | None = None,
    ) -> InPlaceResult:
        path = Path(excel_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Excelが見つかりません: {path}")
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("更新対象Excelは .xlsx または .xlsm を指定してください。")

        lock_file = path.parent / f"~${path.name}"
        if lock_file.exists():
            raise RuntimeError(
                f"Excelが開かれている可能性があります: {path.name}\n"
                "対象Excelを閉じてから再実行してください。"
            )

        sha_before = file_sha256(path)
        if expected_sha256 and sha_before != expected_sha256:
            raise RuntimeError(
                "事前チェック後に更新対象Excelが変更されています。"
                "安全のため、もう一度事前チェックを実行してください。"
            )

        source_bytes = path.read_bytes()

        # 既存エンジンで転記・数式照合・保存後の値照合まで全て実施する。
        result = self.process(csv_data, source_bytes, path.name)

        # 元ファイルはまだ触らず、先にバックアップを確定する。
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_dir = path.parent / "_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{timestamp}_{path.name}"
        shutil.copy2(path, backup_path)
        if file_sha256(backup_path) != sha_before:
            raise RuntimeError("バックアップのハッシュが原本と一致しません。更新を中止します。")

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.stem}_transfer_",
            suffix=path.suffix,
            dir=str(path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)

        try:
            temp_path.write_bytes(result.workbook_bytes)

            # ディスク書込み後のバイト列が検証済み出力と一致することを確認。
            if temp_path.read_bytes() != result.workbook_bytes:
                raise RuntimeError("一時Excelの書込み内容が検証済みデータと一致しません。")

            # 一時Excelが実際に再オープンできることも確認。
            reopened = self._load(temp_path.read_bytes(), path.name)
            reopened.close()

            # 処理中にユーザー等が元Excelを変更していないか、置換直前に再確認。
            if file_sha256(path) != sha_before:
                raise RuntimeError(
                    "処理中に更新対象Excelが変更されました。元ファイルは更新しません。"
                )

            # 同じパスを原子的に置換。ここで初めて元Excelが更新される。
            os.replace(temp_path, path)
            sha_after = file_sha256(path)

            return InPlaceResult(
                excel_path=str(path),
                backup_path=str(backup_path),
                record_count=result.record_count,
                formula_count=result.formula_count,
                target_start_row=result.target_start_row,
                target_end_row=result.target_end_row,
                sha256_before=sha_before,
                sha256_after=sha_after,
            )
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise
