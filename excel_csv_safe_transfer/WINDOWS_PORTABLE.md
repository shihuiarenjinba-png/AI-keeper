# Safe Excel Transfer - Windows portable build

This directory can produce an **unsigned portable Windows ZIP** suitable for local verification before any sales upload.

## Build

Open PowerShell in `excel_csv_safe_transfer` and run the short wrapper:

```powershell
.\build-windows-portable.cmd 1.0.0
```

Equivalent PowerShell command:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-windows-portable.ps1 -Version 1.0.0
```

The build fails closed unless all automated checks pass:

- installs the declared runtime/build dependencies
- selects and prints a supported 64-bit CPython (3.11 preferred; 3.11-3.14 accepted)
- runs the existing pytest suite under a unique product-local `.test-tmp` directory
- compiles the Python entry points
- builds a PyInstaller one-directory application
- includes Streamlit runtime/static assets without bundling its developer-only `.agents` documentation tree
- launches the built EXE on localhost
- verifies Streamlit `/_stcore/health` returns HTTP 200
- writes the ZIP directly from staged files (without a path-length-increasing duplicate payload tree)
- writes a SHA-256 sidecar
- extracts the exact ZIP into a product-local verification directory and health-checks the EXE from that extracted copy
- promotes the ZIP and sidecar into `release` only after every check passes; an existing valid release is retained on failure

Set `OKINAWA_BUILD_PYTHON` to an explicit Python executable when a specific
supported local runtime must be used. The selected executable, version, and
architecture are printed before the build begins.

## Output

```text
release\Safe-Excel-Transfer-Windows-Portable-v1.0.0.zip
release\Safe-Excel-Transfer-Windows-Portable-v1.0.0.zip.sha256
```

You can re-check an already built or copied ZIP with:

```powershell
.\verify-windows-portable.ps1 -ZipPath .\release\Safe-Excel-Transfer-Windows-Portable-v1.0.0.zip
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
