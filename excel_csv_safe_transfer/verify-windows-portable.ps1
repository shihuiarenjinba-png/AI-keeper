param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "This verifier must run on Windows."
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
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

try {
    Expand-Archive -LiteralPath $ResolvedZip -DestinationPath $TempRoot -Force
    $Exe = Get-ChildItem -LiteralPath $TempRoot -Recurse -File -Filter "SafeExcelTransfer.exe" | Select-Object -First 1
    if (-not $Exe) {
        throw "SafeExcelTransfer.exe was not found inside the ZIP."
    }

    $Port = Get-Random -Minimum 20000 -Maximum 45000
    $Process = Start-Process -FilePath $Exe.FullName -ArgumentList @("--port", "$Port", "--no-browser") -PassThru
    try {
        $HealthUrl = "http://127.0.0.1:$Port/_stcore/health"
        $Deadline = (Get-Date).AddSeconds(45)
        $Healthy = $false
        while ((Get-Date) -lt $Deadline) {
            if ($Process.HasExited) {
                throw "Packaged app exited before becoming healthy. ExitCode=$($Process.ExitCode)"
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
            throw "Packaged app did not pass the health check within 45 seconds."
        }
        Write-Host "ZIP runtime PASS: $HealthUrl"
    }
    finally {
        if ($Process -and -not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            $Process.WaitForExit()
        }
    }
}
finally {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "VERIFY PASS: $ResolvedZip"
