param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "This build script must run on Windows."
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Show-LauncherLog([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Write-Host "--- launcher diagnostic log ---"
        Get-Content -LiteralPath $Path | ForEach-Object { Write-Host $_ }
        Write-Host "--- end launcher diagnostic log ---"
    }
}

$BootstrapPython = (Get-Command python -ErrorAction Stop).Source
$VenvDir = Join-Path $Root ".build-venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "[1/9] Preparing isolated build environment..."
if (-not (Test-Path -LiteralPath $Python)) {
    & $BootstrapPython -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Could not create the build virtual environment." }
}

Write-Host "[2/9] Installing runtime/build dependencies..."
& $Python -m pip install --disable-pip-version-check -r "$Root\requirements.txt" -r "$Root\requirements-build.txt"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "[3/9] Running unit tests..."
& $Python -m pytest -q "$Root\tests"
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }

Write-Host "[4/9] Compiling Python sources..."
& $Python -m py_compile "$Root\app.py" "$Root\desktop_launcher.py"
if ($LASTEXITCODE -ne 0) { throw "Python compile check failed." }

$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist"
$ReleaseRoot = Join-Path $Root "release"
$AppName = "SafeExcelTransfer"
$PackageName = "Safe-Excel-Transfer-Windows-Portable-v$Version"
$PayloadDir = Join-Path $ReleaseRoot $PackageName
$ZipPath = Join-Path $ReleaseRoot "$PackageName.zip"
$ShaPath = "$ZipPath.sha256"

Write-Host "[5/9] Building portable Windows app..."
Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $DistDir $AppName) -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $PayloadDir -ErrorAction SilentlyContinue
Remove-Item -Force $ZipPath -ErrorAction SilentlyContinue
Remove-Item -Force $ShaPath -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null

$PyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", $AppName,
    "--paths", $Root,
    "--collect-all", "streamlit",
    "--collect-all", "openpyxl",
    "--collect-submodules", "transfer",
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.filedialog",
    "--add-data", "$Root\app.py;.",
    "--add-data", "$Root\config_example.json;.",
    "$Root\desktop_launcher.py"
)
& $Python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$ExePath = Join-Path $DistDir "$AppName\$AppName.exe"
if (-not (Test-Path $ExePath)) {
    throw "Built executable was not found: $ExePath"
}

Write-Host "[6/9] Starting local HTTP smoke test..."
$Port = Get-Random -Minimum 20000 -Maximum 45000
$LauncherLog = Join-Path $env:TEMP ("SafeExcelTransfer-launcher-" + [guid]::NewGuid().ToString("N") + ".log")
$PreviousLog = $env:OKINAWA_DESKTOP_LOG
$env:OKINAWA_DESKTOP_LOG = $LauncherLog
$Process = $null
try {
    $Process = Start-Process -FilePath $ExePath -ArgumentList @("--port", "$Port", "--no-browser") -PassThru
    $HealthUrls = @("http://127.0.0.1:$Port/_stcore/health", "http://127.0.0.1:$Port/")
    $Deadline = (Get-Date).AddSeconds(90)
    $Healthy = $false
    while ((Get-Date) -lt $Deadline) {
        if ($Process.HasExited) {
            Show-LauncherLog $LauncherLog
            throw "Portable app exited before becoming healthy. ExitCode=$($Process.ExitCode)"
        }
        foreach ($HealthUrl in $HealthUrls) {
            try {
                $Response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
                if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500) {
                    $Healthy = $true
                    Write-Host "Health check PASS: $HealthUrl"
                    break
                }
            }
            catch {
            }
        }
        if ($Healthy) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $Healthy) {
        Show-LauncherLog $LauncherLog
        throw "Portable app did not pass the health check within 90 seconds."
    }
}
finally {
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit()
    }
    if ($null -eq $PreviousLog) {
        Remove-Item Env:OKINAWA_DESKTOP_LOG -ErrorAction SilentlyContinue
    }
    else {
        $env:OKINAWA_DESKTOP_LOG = $PreviousLog
    }
    Remove-Item -LiteralPath $LauncherLog -Force -ErrorAction SilentlyContinue
}

Write-Host "[7/9] Creating portable ZIP..."
New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null
Copy-Item -Path (Join-Path $DistDir "$AppName\*") -Destination $PayloadDir -Recurse -Force
Copy-Item -Path "$Root\README.md" -Destination (Join-Path $PayloadDir "README.md") -Force
@(
    "Product: Safe Excel Transfer",
    "Version: $Version",
    "Build type: UNSIGNED WINDOWS PORTABLE",
    "Entry point: $AppName.exe",
    "Generated: $((Get-Date).ToString('s'))"
) | Set-Content -Path (Join-Path $PayloadDir "BUILD_INFO.txt") -Encoding UTF8

Compress-Archive -Path $PayloadDir -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "[8/9] Writing SHA-256..."
$Hash = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
"$Hash  $([System.IO.Path]::GetFileName($ZipPath))" | Set-Content -Path $ShaPath -Encoding ASCII

Write-Host "[9/9] Verifying the exact ZIP artifact..."
& "$Root\verify-windows-portable.ps1" -ZipPath $ZipPath

Write-Host ""
Write-Host "BUILD PASS"
Write-Host "ZIP: $ZipPath"
Write-Host "SHA256: $ShaPath"
Write-Host "EXE: $ExePath"
