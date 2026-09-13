param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,
    [string]$WorkingRoot = "",
    [string]$ExpectedVersion = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "This verifier must run on Windows."
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Remove-OwnedDirectory([string]$Path, [string]$ExpectedParent) {
    $FullPath = [System.IO.Path]::GetFullPath($Path)
    $ParentPath = [System.IO.Path]::GetFullPath($ExpectedParent).TrimEnd('\') + '\'
    if (-not $FullPath.StartsWith($ParentPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a directory outside the verifier work area: $FullPath"
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

$ResolvedZip = (Resolve-Path -LiteralPath $ZipPath).Path
$ZipLeaf = [System.IO.Path]::GetFileName($ResolvedZip)
if ($ZipLeaf -notmatch '^Safe-Excel-Transfer-Windows-Portable-v(.+)\.zip$') {
    throw "Unexpected product ZIP name: $ZipLeaf"
}
$VersionFromName = $Matches[1]
if ($ExpectedVersion -and $VersionFromName -ne $ExpectedVersion) {
    throw "ZIP version mismatch. Expected=$ExpectedVersion Actual=$VersionFromName"
}

$ShaPath = "$ResolvedZip.sha256"
if (-not (Test-Path -LiteralPath $ShaPath)) {
    throw "Required SHA-256 sidecar was not found: $ShaPath"
}
$ShaParts = ((Get-Content -LiteralPath $ShaPath -TotalCount 1).Trim() -split "\s+")
if ($ShaParts.Count -lt 2 -or $ShaParts[0] -notmatch '^[0-9a-fA-F]{64}$') {
    throw "SHA-256 sidecar format is invalid."
}
if ($ShaParts[1] -ne $ZipLeaf) {
    throw "SHA-256 sidecar names a different ZIP. Expected=$ZipLeaf Actual=$($ShaParts[1])"
}
$ExpectedHash = $ShaParts[0].ToLowerInvariant()
$ActualHash = Get-Sha256 $ResolvedZip
if ($ExpectedHash -ne $ActualHash) {
    throw "ZIP SHA-256 mismatch. Expected=$ExpectedHash Actual=$ActualHash"
}
Write-Host "SHA-256 PASS: $ActualHash"

if ($WorkingRoot) {
    $VerifyRoot = [System.IO.Path]::GetFullPath($WorkingRoot)
    $CleanupParent = Split-Path -Parent $VerifyRoot
}
else {
    $CleanupParent = Join-Path $Root ".verify-tmp"
    $VerifyRoot = Join-Path $CleanupParent ([guid]::NewGuid().ToString("N"))
}
$ExtractRoot = Join-Path $VerifyRoot "extracted"
$LauncherLog = Join-Path $VerifyRoot "launcher.log"
$PreviousLog = $env:OKINAWA_DESKTOP_LOG
New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null

try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $ExpectedFolder = "Safe-Excel-Transfer-Windows-Portable-v$VersionFromName"
    $ExpectedExeEntry = "$ExpectedFolder/SafeExcelTransfer.exe"
    $ExeEntryCount = 0
    $Archive = [System.IO.Compression.ZipFile]::OpenRead($ResolvedZip)
    try {
        foreach ($Entry in $Archive.Entries) {
            $Name = $Entry.FullName.Replace('/', '\')
            if ([System.IO.Path]::IsPathRooted($Name) -or $Name -match '(^|\\)\.\.(\\|$)' -or $Name.Contains(':')) {
                throw "Unsafe ZIP entry path: $($Entry.FullName)"
            }
            $Prefix = "$ExpectedFolder/"
            if ($Entry.FullName -ne "$ExpectedFolder/" -and -not $Entry.FullName.StartsWith($Prefix, [System.StringComparison]::Ordinal)) {
                throw "ZIP entry is outside the expected product directory: $($Entry.FullName)"
            }

            $EntryLeaf = [System.IO.Path]::GetFileName($Entry.FullName)
            $EntryExtension = [System.IO.Path]::GetExtension($Entry.FullName)
            if ($EntryLeaf -match '(?i)(^\.env($|\.)|secret|private[_-]?key|api[_-]?key|webhook)' -or
                $EntryExtension -match '(?i)^\.(pfx|p12|key)$') {
                throw "Potential secret/private-key material was found in the ZIP: $EntryLeaf"
            }
            if ($EntryExtension -ieq ".pem") {
                $PemReader = [System.IO.StreamReader]::new($Entry.Open())
                try { $PemText = $PemReader.ReadToEnd() }
                finally { $PemReader.Dispose() }
                if ($PemText -match '-----BEGIN (RSA |EC |ENCRYPTED )?PRIVATE KEY-----') {
                    throw "Private-key material was found in the ZIP: $EntryLeaf"
                }
            }
            if ($Entry.FullName -ieq $ExpectedExeEntry) {
                $ExeEntryCount++
            }
            elseif ($EntryLeaf -ieq "SafeExcelTransfer.exe") {
                throw "SafeExcelTransfer.exe was found outside the product root."
            }

            $Relative = $Entry.FullName.Substring($ExpectedFolder.Length).TrimStart('/').Replace('/', '\')
            if (-not $Relative) { continue }
            $Destination = [System.IO.Path]::GetFullPath((Join-Path $ExtractRoot $Relative))
            $ExtractPrefix = [System.IO.Path]::GetFullPath($ExtractRoot).TrimEnd('\') + '\'
            if (-not $Destination.StartsWith($ExtractPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Unsafe extracted destination: $Destination"
            }
            if (-not $Entry.Name) {
                New-Item -ItemType Directory -Force -Path $Destination | Out-Null
                continue
            }
            $DestinationParent = Split-Path -Parent $Destination
            New-Item -ItemType Directory -Force -Path $DestinationParent | Out-Null
            $InputStream = $Entry.Open()
            $OutputStream = [System.IO.File]::Create($Destination)
            try { $InputStream.CopyTo($OutputStream) }
            finally {
                $OutputStream.Dispose()
                $InputStream.Dispose()
            }
        }
    }
    finally {
        $Archive.Dispose()
    }
    if ($ExeEntryCount -ne 1) {
        throw "Expected exactly one root SafeExcelTransfer.exe; found $ExeEntryCount."
    }
    $PackageDir = $ExtractRoot
    $BuildInfo = Join-Path $PackageDir "BUILD_INFO.txt"
    $Readme = Join-Path $PackageDir "README.md"
    if (-not (Test-Path -LiteralPath $BuildInfo) -or -not (Test-Path -LiteralPath $Readme)) {
        throw "Required BUILD_INFO.txt or README.md is missing."
    }
    $BuildText = Get-Content -LiteralPath $BuildInfo -Raw
    if ($BuildText -notmatch '(?m)^Product: Safe Excel Transfer\s*$' -or
        $BuildText -notmatch "(?m)^Version: $([regex]::Escape($VersionFromName))\s*$" -or
        $BuildText -notmatch '(?m)^Build type: UNSIGNED WINDOWS PORTABLE\s*$') {
        throw "Product marker, version, or build type is invalid."
    }
    if ($BuildText -match 'LOCAL TEST|SIGNED SALES|MICROSOFT STORE') {
        throw "A conflicting distribution-track marker was found."
    }

    $ExePath = Join-Path $PackageDir "SafeExcelTransfer.exe"
    if (-not (Test-Path -LiteralPath $ExePath)) {
        throw "SafeExcelTransfer.exe was not extracted at the product root."
    }

    $Port = Get-Random -Minimum 20000 -Maximum 45000
    $env:OKINAWA_DESKTOP_LOG = $LauncherLog
    $Process = Start-Process -FilePath $ExePath -ArgumentList @("--port", "$Port", "--no-browser") -PassThru -WindowStyle Hidden
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
                catch {}
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
    if ($null -eq $PreviousLog) { Remove-Item Env:OKINAWA_DESKTOP_LOG -ErrorAction SilentlyContinue }
    else { $env:OKINAWA_DESKTOP_LOG = $PreviousLog }
    Remove-OwnedDirectory $VerifyRoot $CleanupParent
}

Write-Host "VERIFY PASS: $ResolvedZip"
