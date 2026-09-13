param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "This verifier must run on Windows."
}

function Show-LauncherLog([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Write-Host "--- launcher diagnostic log ---"
        Get-Content -LiteralPath $Path | ForEach-Object { Write-Host $_ }
        Write-Host "--- end launcher diagnostic log ---"
    }
}

$ResolvedZip = (Resolve-Path -LiteralPath $ZipPath).Path
$ShaPath = "$ResolvedZip.sha256"

if (Test-Path -LiteralPath $ShaPath) {
    $ExpectedHash = ((Get-Content -LiteralPath $ShaPath -TotalCount 1).Trim() -split "\s+")[0].ToLowerInvariant()
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ResolvedZip).Hash.ToLowerInvariant()
    if ($ExpectedHash -ne $ActualHash) {
        throw "ZIP SHA-256 mismatch. Expected=$ExpectedHash Actual=$ActualHash"
    }
    Write-Host "SHA-256 PASS: $ActualHash"
}
else {
    Write-Host "SHA-256 sidecar not found; continuing with runtime verification."
}

$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("safe-excel-transfer-verify-" + [guid]::NewGuid().ToString("N"))
$LauncherLog = Join-Path ([System.IO.Path]::GetTempPath()) ("SafeExcelTransfer-verify-" + [guid]::NewGuid().ToString("N") + ".log")
$PreviousLog = $env:OKINAWA_DESKTOP_LOG
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

try {
    Expand-Archive -LiteralPath $ResolvedZip -DestinationPath $TempRoot -Force
    $Exe = Get-ChildItem -LiteralPath $TempRoot -Recurse -File -Filter "SafeExcelTransfer.exe" | Select-Object -First 1
    if (-not $Exe) {
        throw "SafeExcelTransfer.exe was not found inside the ZIP."
    }

    $Port = Get-Random -Minimum 20000 -Maximum 45000
    $env:OKINAWA_DESKTOP_LOG = $LauncherLog
    $Process = Start-Process -FilePath $Exe.FullName -ArgumentList @("--port", "$Port", "--no-browser") -PassThru
    try {
        $HealthUrls = @("http://127.0.0.1:$Port/_stcore/health", "http://127.0.0.1:$Port/")
        $Deadline = (Get-Date).AddSeconds(90)
        $Healthy = $false
        while ((Get-Date) -lt $Deadline) {
            if ($Process.HasExited) {
                Show-LauncherLog $LauncherLog
                throw "Packaged app exited before becoming healthy. ExitCode=$($Process.ExitCode)"
            }
            foreach ($HealthUrl in $HealthUrls) {
                try {
                    $Response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
                    if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500) {
                        $Healthy = $true
                        Write-Host "ZIP runtime PASS: $HealthUrl"
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
            throw "Packaged app did not pass the health check within 90 seconds."
        }
    }
    finally {
        if ($Process -and -not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            $Process.WaitForExit()
        }
    }
}
finally {
    if ($null -eq $PreviousLog) {
        Remove-Item Env:OKINAWA_DESKTOP_LOG -ErrorAction SilentlyContinue
    }
    else {
        $env:OKINAWA_DESKTOP_LOG = $PreviousLog
    }
    Remove-Item -LiteralPath $LauncherLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "VERIFY PASS: $ResolvedZip"
