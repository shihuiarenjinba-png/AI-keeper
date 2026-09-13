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

function Remove-OwnedDirectory([string]$Path, [string]$ExpectedParent) {
    $FullPath = [System.IO.Path]::GetFullPath($Path)
    $ParentPath = [System.IO.Path]::GetFullPath($ExpectedParent).TrimEnd('\') + '\'
    if (-not $FullPath.StartsWith($ParentPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a directory outside the owned build area: $FullPath"
    }
    if (Test-Path -LiteralPath $FullPath) {
        [System.IO.Directory]::Delete($FullPath, $true)
    }
}

function Show-LauncherLog([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Write-Host "--- launcher diagnostic log ---"
        Get-Content -LiteralPath $Path | ForEach-Object { Write-Host $_ }
        Write-Host "--- end launcher diagnostic log ---"
    }
}

function Get-Sha256([string]$Path) {
    $Algorithm = [System.Security.Cryptography.SHA256]::Create()
    $Stream = [System.IO.File]::OpenRead($Path)
    try {
        return (($Algorithm.ComputeHash($Stream) | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $Stream.Dispose()
        $Algorithm.Dispose()
    }
}

function Get-PythonInfo([string]$Executable, [string[]]$PrefixArgs) {
    $Probe = @(
        $PrefixArgs
        "-c"
        "import json,platform,struct,sys; print(json.dumps({'executable':sys.executable,'implementation':platform.python_implementation(),'major':sys.version_info.major,'minor':sys.version_info.minor,'micro':sys.version_info.micro,'bits':struct.calcsize('P')*8}))"
    )
    $Json = & $Executable @Probe
    if ($LASTEXITCODE -ne 0 -or -not $Json) {
        throw "Python runtime probe failed: $Executable"
    }
    return ($Json | Select-Object -Last 1 | ConvertFrom-Json)
}

function Resolve-BuildPython {
    if ($env:OKINAWA_BUILD_PYTHON) {
        $Resolved = (Get-Command $env:OKINAWA_BUILD_PYTHON -ErrorAction Stop).Source
        return @{ Executable = $Resolved; PrefixArgs = @() }
    }

    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        $HasPython311 = $false
        try {
            & $PyLauncher.Source -3.11 -c "import sys; print(sys.executable)" 2>$null | Out-Null
            $HasPython311 = $LASTEXITCODE -eq 0
        }
        catch {
            $HasPython311 = $false
        }
        if ($HasPython311) {
            return @{ Executable = $PyLauncher.Source; PrefixArgs = @("-3.11") }
        }
    }

    $PythonCommand = Get-Command python -ErrorAction Stop
    return @{ Executable = $PythonCommand.Source; PrefixArgs = @() }
}

function Assert-SupportedPython($Info) {
    if ($Info.implementation -ne "CPython") {
        throw "Unsupported Python implementation: $($Info.implementation). CPython is required."
    }
    if ($Info.major -ne 3 -or $Info.minor -lt 11 -or $Info.minor -gt 14) {
        throw "Unsupported Python version: $($Info.major).$($Info.minor). Supported versions are CPython 3.11 through 3.14."
    }
    if ($Info.bits -ne 64) {
        throw "Unsupported Python architecture: $($Info.bits)-bit. A 64-bit CPython is required."
    }
}

if ($Version -notmatch '^\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?$') {
    throw "Version must be a safe semantic-style value, for example 1.0.0."
}

$Bootstrap = Resolve-BuildPython
$BootstrapInfo = Get-PythonInfo $Bootstrap.Executable $Bootstrap.PrefixArgs
Assert-SupportedPython $BootstrapInfo
Write-Host "Build Python: $($BootstrapInfo.executable)"
Write-Host "Build Python version: CPython $($BootstrapInfo.major).$($BootstrapInfo.minor).$($BootstrapInfo.micro) ($($BootstrapInfo.bits)-bit)"

$PythonTag = "py$($BootstrapInfo.major)$($BootstrapInfo.minor)"
$VenvDir = Join-Path $Root ".build-venv-$PythonTag"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$RunId = [guid]::NewGuid().ToString("N")
$TestBase = Join-Path $Root ".test-tmp"
$TestTemp = Join-Path $TestBase $RunId
$StageBase = Join-Path $Root ".release-staging"
$StageRoot = Join-Path $StageBase $RunId
$BuildDir = Join-Path $StageRoot "build"
$DistDir = Join-Path $StageRoot "dist"
$SpecDir = Join-Path $StageRoot "spec"
$StageRelease = Join-Path $StageRoot "release"
$VerifyRoot = Join-Path $StageRoot "verify"
$LogsDir = Join-Path $StageRoot "logs"
$ReleaseRoot = Join-Path $Root "release"
$AppName = "SafeExcelTransfer"
$PackageName = "Safe-Excel-Transfer-Windows-Portable-v$Version"
$StagedZip = Join-Path $StageRelease "$PackageName.zip"
$StagedSha = "$StagedZip.sha256"
$FinalZip = Join-Path $ReleaseRoot "$PackageName.zip"
$FinalSha = "$FinalZip.sha256"

New-Item -ItemType Directory -Force -Path $TestTemp, $BuildDir, $DistDir, $SpecDir, $StageRelease, $LogsDir | Out-Null

try {
    Write-Host "[1/10] Preparing isolated build environment..."
    if (-not (Test-Path -LiteralPath $Python)) {
        & $Bootstrap.Executable @($Bootstrap.PrefixArgs) -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { throw "Could not create the build virtual environment." }
    }
    $VenvInfo = Get-PythonInfo $Python @()
    Assert-SupportedPython $VenvInfo
    if ($VenvInfo.major -ne $BootstrapInfo.major -or $VenvInfo.minor -ne $BootstrapInfo.minor) {
        throw "The isolated environment Python does not match the selected build Python."
    }
    Write-Host "Isolated Python: $($VenvInfo.executable)"

    Write-Host "[2/10] Installing runtime/build dependencies..."
    & $Python -m pip install --disable-pip-version-check -r "$Root\requirements.txt" -r "$Root\requirements-build.txt"
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

    Write-Host "[3/10] Running unit tests in product-local temporary storage..."
    & $Python -m pytest -q -p no:cacheprovider --basetemp $TestTemp "$Root\tests"
    if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }

    Write-Host "[4/10] Compiling Python sources..."
    & $Python -m compileall -q "$Root\app.py" "$Root\desktop_launcher.py" "$Root\transfer"
    if ($LASTEXITCODE -ne 0) { throw "Python compile check failed." }

    Write-Host "[5/10] Building in isolated staging..."
    $StreamlitStatic = Join-Path $VenvDir "Lib\site-packages\streamlit\static"
    if (-not (Test-Path -LiteralPath $StreamlitStatic)) {
        throw "Streamlit static assets were not found: $StreamlitStatic"
    }
    $PyInstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name", $AppName,
        "--workpath", $BuildDir,
        "--distpath", $DistDir,
        "--specpath", $SpecDir,
        "--paths", $Root,
        "--copy-metadata", "streamlit",
        "--exclude-module", "streamlit.testing",
        "--exclude-module", "pytest",
        "--collect-all", "openpyxl",
        "--collect-submodules", "transfer",
        "--hidden-import", "streamlit.web.cli",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.filedialog",
        "--add-data", "$Root\app.py;.",
        "--add-data", "$Root\config_example.json;.",
        "--add-data", "$StreamlitStatic;streamlit/static",
        "$Root\desktop_launcher.py"
    )
    & $Python @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $ExePath = Join-Path $DistDir "$AppName\$AppName.exe"
    if (-not (Test-Path -LiteralPath $ExePath)) {
        throw "Built executable was not found: $ExePath"
    }

    Write-Host "[6/10] Health-checking the raw staged executable..."
    $Port = Get-Random -Minimum 20000 -Maximum 45000
    $LauncherLog = Join-Path $LogsDir "raw-launcher.log"
    $PreviousLog = $env:OKINAWA_DESKTOP_LOG
    $env:OKINAWA_DESKTOP_LOG = $LauncherLog
    $Process = $null
    try {
        $Process = Start-Process -FilePath $ExePath -ArgumentList @("--port", "$Port", "--no-browser") -PassThru -WindowStyle Hidden
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
                catch {}
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
        if ($null -eq $PreviousLog) { Remove-Item Env:OKINAWA_DESKTOP_LOG -ErrorAction SilentlyContinue }
        else { $env:OKINAWA_DESKTOP_LOG = $PreviousLog }
    }

    Write-Host "[7/10] Creating the staged portable ZIP..."
    $BuildInfoLines = @(
        "Product: Safe Excel Transfer",
        "Version: $Version",
        "Build type: UNSIGNED WINDOWS PORTABLE",
        "Entry point: $AppName.exe"
    )
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $ZipStream = [System.IO.File]::Open($StagedZip, [System.IO.FileMode]::CreateNew)
    $Archive = [System.IO.Compression.ZipArchive]::new(
        $ZipStream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )
    try {
        $AppRoot = Join-Path $DistDir $AppName
        foreach ($File in Get-ChildItem -LiteralPath $AppRoot -Recurse -File) {
            $Relative = $File.FullName.Substring($AppRoot.Length).TrimStart('\').Replace('\', '/')
            $EntryName = "$PackageName/$Relative"
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $Archive,
                $File.FullName,
                $EntryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $Archive,
            "$Root\README.md",
            "$PackageName/README.md",
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
        $BuildEntry = $Archive.CreateEntry(
            "$PackageName/BUILD_INFO.txt",
            [System.IO.Compression.CompressionLevel]::Optimal
        )
        $Writer = [System.IO.StreamWriter]::new(
            $BuildEntry.Open(),
            [System.Text.UTF8Encoding]::new($true)
        )
        try { $Writer.Write(($BuildInfoLines -join "`r`n") + "`r`n") }
        finally { $Writer.Dispose() }
    }
    finally {
        $Archive.Dispose()
        $ZipStream.Dispose()
    }

    Write-Host "[8/10] Writing the staged SHA-256 sidecar..."
    $Hash = Get-Sha256 $StagedZip
    "$Hash  $([System.IO.Path]::GetFileName($FinalZip))" | Set-Content -LiteralPath $StagedSha -Encoding ASCII

    Write-Host "[9/10] Extracting and verifying the exact staged ZIP..."
    & "$Root\verify-windows-portable.ps1" -ZipPath $StagedZip -WorkingRoot $VerifyRoot -ExpectedVersion $Version
    if ($LASTEXITCODE -ne 0) { throw "Final staged ZIP verification failed." }

    Write-Host "[10/10] Promoting verified artifacts..."
    New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
    $CandidateZip = Join-Path $ReleaseRoot "$PackageName.zip.promoting-$RunId"
    $CandidateSha = Join-Path $ReleaseRoot "$PackageName.zip.sha256.promoting-$RunId"
    $BackupZip = Join-Path $ReleaseRoot "$PackageName.zip.previous-$RunId"
    $BackupSha = Join-Path $ReleaseRoot "$PackageName.zip.sha256.previous-$RunId"
    Copy-Item -LiteralPath $StagedZip -Destination $CandidateZip
    Copy-Item -LiteralPath $StagedSha -Destination $CandidateSha
    if ((Get-Sha256 $CandidateZip) -ne $Hash) {
        throw "Promoted ZIP candidate hash does not match the verified staged ZIP."
    }
    try {
        if (Test-Path -LiteralPath $FinalZip) { Move-Item -LiteralPath $FinalZip -Destination $BackupZip }
        if (Test-Path -LiteralPath $FinalSha) { Move-Item -LiteralPath $FinalSha -Destination $BackupSha }
        Move-Item -LiteralPath $CandidateZip -Destination $FinalZip
        Move-Item -LiteralPath $CandidateSha -Destination $FinalSha
        if ((Get-Sha256 $FinalZip) -ne $Hash) {
            throw "Final ZIP hash changed during promotion."
        }
        Remove-Item -LiteralPath $BackupZip, $BackupSha -Force -ErrorAction SilentlyContinue
    }
    catch {
        Remove-Item -LiteralPath $FinalZip, $FinalSha -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $BackupZip) { Move-Item -LiteralPath $BackupZip -Destination $FinalZip }
        if (Test-Path -LiteralPath $BackupSha) { Move-Item -LiteralPath $BackupSha -Destination $FinalSha }
        throw
    }

    Write-Host ""
    Write-Host "BUILD PASS"
    Write-Host "ZIP: $FinalZip"
    Write-Host "SHA256: $FinalSha"
    Write-Host "Verified staged EXE: $ExePath"
}
finally {
    Remove-OwnedDirectory $TestTemp $TestBase
    Remove-OwnedDirectory $StageRoot $StageBase
}
