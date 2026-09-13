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

$Python = (Get-Command python -ErrorAction Stop).Source

Write-Host "[1/7] Installing runtime/build dependencies..."
& $Python -m pip install --disable-pip-version-check -r "$Root\requirements.txt" -r "$Root\requirements-build.txt"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "[2/7] Running unit tests..."
& $Python -m unittest discover -s "$Root\tests" -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }

Write-Host "[3/7] Compiling Python sources..."
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

Write-Host "[4/7] Building portable Windows app..."
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
    "--collect-all", "streamlit",
    "--collect-all", "openpyxl",
    "--add-data", "$Root\app.py;.",
    "--add-data", "$Root\config_example.json;.",
    "--add-data", "$Root\transfer;transfer",
    "$Root\desktop_launcher.py"
)
& $Python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$ExePath = Join-Path $DistDir "$AppName\$AppName.exe"
if (-not (Test-Path $ExePath)) {
    throw "Built executable was not found: $ExePath"
}

Write-Host "[5/7] Starting local HTTP smoke test..."
$Port = Get-Random -Minimum 20000 -Maximum 45000
$Process = Start-Process -FilePath $ExePath -ArgumentList @("--port", "$Port", "--no-browser") -PassThru
try {
    $HealthUrl = "http://127.0.0.1:$Port/_stcore/health"
    $Deadline = (Get-Date).AddSeconds(45)
    $Healthy = $false
    while ((Get-Date) -lt $Deadline) {
        if ($Process.HasExited) {
            throw "Portable app exited before becoming healthy. ExitCode=$($Process.ExitCode)"
        }
        try {
            $Response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
            if ($Response.StatusCode -eq 200) {
                $Healthy = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Healthy) {
        throw "Portable app did not pass the health check within 45 seconds."
    }
    Write-Host "Health check PASS: $HealthUrl"
}
finally {
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit()
    }
}

Write-Host "[6/7] Creating portable ZIP..."
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

Write-Host "[7/7] Writing SHA-256..."
$Hash = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
"$Hash  $([System.IO.Path]::GetFileName($ZipPath))" | Set-Content -Path $ShaPath -Encoding ASCII

Write-Host ""
Write-Host "BUILD PASS"
Write-Host "ZIP: $ZipPath"
Write-Host "SHA256: $ShaPath"
Write-Host "EXE: $ExePath"
