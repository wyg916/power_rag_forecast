param(
    [Parameter(Mandatory = $true)][string]$ReportPath,
    [Parameter(Mandatory = $true)][string]$Wheelhouse,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [string]$MirrorBase = ""
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Path $Wheelhouse -Force | Out-Null
$report = Get-Content -LiteralPath $ReportPath -Raw -Encoding UTF8 | ConvertFrom-Json

foreach ($item in $report.install) {
    $officialUrl = [string]$item.download_info.url
    $officialUri = [System.Uri]$officialUrl
    $url = if ($MirrorBase) { $MirrorBase.TrimEnd('/') + $officialUri.AbsolutePath } else { $officialUrl }
    $name = [System.IO.Path]::GetFileName(([System.Uri]$url).AbsolutePath)
    $target = Join-Path $Wheelhouse $name
    $expected = ([string]$item.download_info.archive_info.hash) -replace '^sha256=', ''

    if (Test-Path -LiteralPath $target) {
        $current = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($current -eq $expected) {
            Add-Content -LiteralPath $LogPath -Value "SKIP verified $name $current" -Encoding UTF8
            continue
        }
    }

    Add-Content -LiteralPath $LogPath -Value "DOWNLOAD $name source=$url official=$officialUrl" -Encoding UTF8
    & curl.exe --silent --show-error --fail --location --retry 12 --retry-all-errors --retry-delay 5 --connect-timeout 60 --speed-time 300 --speed-limit 1024 --continue-at - --output $target $url 2>> $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "curl failed for $name with exit code $LASTEXITCODE"
    }

    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "SHA-256 mismatch for $name expected=$expected actual=$actual"
    }
    Add-Content -LiteralPath $LogPath -Value "VERIFIED $name $actual" -Encoding UTF8
}

Add-Content -LiteralPath $LogPath -Value "COMPLETE" -Encoding UTF8
