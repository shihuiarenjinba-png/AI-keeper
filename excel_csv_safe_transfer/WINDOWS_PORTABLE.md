# Safe Excel Transfer - Windows portable build

This directory can produce an **unsigned portable Windows ZIP** suitable for local verification before any sales upload.

## Build

Open PowerShell in `excel_csv_safe_transfer` and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-windows-portable.ps1 -Version 1.0.0
```

The script performs these checks before creating the ZIP:

- installs the declared runtime/build dependencies
- runs the existing unit tests
- compiles the Python entry points
- builds a PyInstaller one-directory application
- launches the built EXE on localhost
- verifies Streamlit `/_stcore/health` returns HTTP 200
- creates the ZIP
- writes a SHA-256 sidecar

## Output

```text
release\Safe-Excel-Transfer-Windows-Portable-v1.0.0.zip
release\Safe-Excel-Transfer-Windows-Portable-v1.0.0.zip.sha256
```

After extracting the ZIP, keep the entire extracted folder together and start:

```text
SafeExcelTransfer.exe
```

The executable starts a local-only Streamlit server on `127.0.0.1` using a free port and opens the default browser. CSV and Excel processing stays on the Windows PC.

## Supported production input currently advertised by the app

- input data: `.csv`
- target workbook: `.xlsx`
- target workbook: `.xlsm` with the existing VBA-preservation path

`.xls` and `.xlsb` are intentionally not accepted as update targets.

## Release status

This is an **unsigned portable build**. Do not describe it as Authenticode-signed or as a Microsoft Store package. Windows reputation/security prompts can still appear on unsigned binaries.
