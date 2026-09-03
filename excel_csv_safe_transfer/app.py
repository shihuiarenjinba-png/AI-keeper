from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from transfer.service import PreflightPlan, TransferService


class SafeTransferApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV → Excel 安全転記")
        self.geometry("900x700")
        self.minsize(780, 620)

        self.service = TransferService()
        self.plan: PreflightPlan | None = None

        self.csv_var = tk.StringVar()
        self.excel_var = tk.StringVar()
        self.config_var = tk.StringVar(
            value=str((Path(__file__).parent / "config_example.json").resolve())
        )
        self.status_var = tk.StringVar(value="ファイルを選択してください。")

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="CSV → Excel 安全転記", font=("", 18, "bold"))
        title.pack(anchor="w", pady=(0, 14))

        note = ttk.Label(
            main,
            text=(
                "原本Excelへ直接書き込まず、コピーで転記・数式照合・値照合を行い、"
                "全検査合格時だけ原本を更新します。"
            ),
            wraplength=820,
        )
        note.pack(anchor="w", pady=(0, 14))

        form = ttk.Frame(main)
        form.pack(fill="x")
        self._file_row(
            form, 0, "CSVファイル", self.csv_var,
            lambda: self._browse_file(self.csv_var, [("CSV", "*.csv"), ("すべて", "*.*")]),
        )
        self._file_row(
            form, 1, "転記先Excel", self.excel_var,
            lambda: self._browse_file(
                self.excel_var,
                [("Excel", "*.xlsx *.xlsm *.xlsb *.xls"), ("すべて", "*.*")],
            ),
        )
        self._file_row(
            form, 2, "設定ファイル", self.config_var,
            lambda: self._browse_file(self.config_var, [("JSON", "*.json"), ("すべて", "*.*")]),
        )
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=14)
        self.preflight_btn = ttk.Button(actions, text="① 事前検査", command=self._start_preflight)
        self.preflight_btn.pack(side="left")
        self.execute_btn = ttk.Button(
            actions, text="② 転記実行", command=self._confirm_execute, state="disabled"
        )
        self.execute_btn.pack(side="left", padx=(10, 0))
        self.status_label = ttk.Label(actions, textvariable=self.status_var)
        self.status_label.pack(side="left", padx=(18, 0))

        ttk.Separator(main).pack(fill="x", pady=(0, 12))
        ttk.Label(main, text="検査・処理結果", font=("", 11, "bold")).pack(anchor="w")
        self.output = tk.Text(main, wrap="word", height=26)
        self.output.pack(fill="both", expand=True, pady=(6, 0))
        self.output.configure(state="disabled")

    def _file_row(self, parent, row, label, var, command):
        ttk.Label(parent, text=label, width=14).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=5)
        entry.bind("<KeyRelease>", lambda _e: self._invalidate_plan())
        ttk.Button(parent, text="選択", command=command).grid(row=row, column=2, pady=5)

    def _browse_file(self, var: tk.StringVar, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)
            self._invalidate_plan()

    def _invalidate_plan(self):
        self.plan = None
        self.execute_btn.configure(state="disabled")
        self.status_var.set("事前検査が必要です。")

    def _set_output(self, text: str):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def _append_output(self, text: str):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _set_busy(self, busy: bool, message: str):
        self.status_var.set(message)
        self.preflight_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.execute_btn.configure(state="disabled")
        elif self.plan is not None:
            self.execute_btn.configure(state="normal")

    def _validate_paths(self) -> bool:
        if not self.csv_var.get().strip():
            messagebox.showerror("入力不足", "CSVファイルを選択してください。")
            return False
        if not self.excel_var.get().strip():
            messagebox.showerror("入力不足", "転記先Excelを選択してください。")
            return False
        if not self.config_var.get().strip():
            messagebox.showerror("入力不足", "設定ファイルを選択してください。")
            return False
        return True

    def _start_preflight(self):
        if not self._validate_paths():
            return
        self.plan = None
        self._set_output("事前検査中です...\n")
        self._set_busy(True, "事前検査中")
        threading.Thread(target=self._preflight_worker, daemon=True).start()

    def _preflight_worker(self):
        try:
            plan = self.service.preflight(
                self.csv_var.get(), self.excel_var.get(), self.config_var.get()
            )
            self.after(0, lambda: self._preflight_success(plan))
        except Exception as e:
            self.after(0, lambda: self._operation_failed("事前検査エラー", e))

    def _preflight_success(self, plan: PreflightPlan):
        self.plan = plan
        self._set_output(plan.summary_text())
        self._set_busy(False, "事前検査 OK")
        self.execute_btn.configure(state="normal")

    def _confirm_execute(self):
        if self.plan is None:
            messagebox.showerror("事前検査", "先に事前検査を実行してください。")
            return

        msg = (
            "以下の内容で転記します。\n\n"
            f"対象年度: {self.plan.fiscal_year}年度\n"
            f"CSV期間: {self.plan.min_date} ～ {self.plan.max_date}\n"
            f"件数: {self.plan.record_count:,}件\n"
            f"転記行: {self.plan.target_start_row} ～ {self.plan.target_end_row}\n\n"
            "原本Excelはバックアップ後、コピー上で検証し、"
            "数式・値の照合がすべて合格した場合のみ更新します。\n\n"
            "実行しますか？"
        )
        if not messagebox.askyesno("転記実行確認", msg):
            return

        self._append_output("\n転記処理を開始します...\n")
        self._set_busy(True, "転記・検証中")
        threading.Thread(target=self._execute_worker, daemon=True).start()

    def _execute_worker(self):
        try:
            assert self.plan is not None
            result = self.service.execute(self.plan)
            self.after(0, lambda: self._execute_success(result))
        except Exception as e:
            self.after(0, lambda: self._operation_failed("転記エラー", e))

    def _execute_success(self, result):
        text = (
            "\n【転記完了】\n"
            f"追加件数　　　: {result['record_count']:,} 件\n"
            f"転記行　　　　: {result['target_start_row']} ～ {result['target_end_row']}\n"
            f"数式保護確認　: {result['formula_count']:,} セル OK\n"
            f"バックアップ　: {result['backup_path']}\n"
            f"処理ログ　　　: {result['log_path']}\n\n"
            "全検査に合格し、原本Excelを更新しました。\n"
        )
        self._append_output(text)
        self.plan = None
        self._set_busy(False, "正常終了")
        self.execute_btn.configure(state="disabled")
        messagebox.showinfo("完了", "転記と検証が正常に完了しました。")

    def _operation_failed(self, title: str, error: Exception):
        self.plan = None
        self._set_busy(False, "停止")
        self.execute_btn.configure(state="disabled")
        self._set_output(
            f"【{title}】\n\n{error}\n\n安全のため原本Excelへの更新は行っていません。"
        )
        messagebox.showerror(title, str(error))


if __name__ == "__main__":
    app = SafeTransferApp()
    app.mainloop()
