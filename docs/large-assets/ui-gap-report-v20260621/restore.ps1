[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$assetDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $assetDirectory '..\..\..'))
$manifestPath = Join-Path $assetDirectory 'manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $projectRoot ($manifest.original_path -replace '/', '\')
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path (Get-Location).Path $OutputPath
}

$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "Output file already exists and was not overwritten: $OutputPath. Use -OutputPath or explicitly pass -Force."
}

$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}

$output = [System.IO.File]::Open(
    $OutputPath,
    [System.IO.FileMode]::Create,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None
)

try {
    foreach ($part in $manifest.parts) {
        $partPath = Join-Path $assetDirectory $part.name
        if (-not (Test-Path -LiteralPath $partPath)) {
            throw "Missing asset part: $partPath"
        }

        $partHash = (Get-FileHash -LiteralPath $partPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($partHash -ne $part.sha256) {
            throw "Asset part checksum mismatch: $($part.name)"
        }

        $input = [System.IO.File]::OpenRead($partPath)
        try {
            $input.CopyTo($output)
        }
        finally {
            $input.Dispose()
        }
    }
}
finally {
    $output.Dispose()
}

$restored = Get-Item -LiteralPath $OutputPath
$restoredHash = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($restored.Length -ne [int64]$manifest.original_size) {
    throw "Restored file size mismatch: actual $($restored.Length), expected $($manifest.original_size)."
}
if ($restoredHash -ne $manifest.original_sha256) {
    throw "Restored file SHA-256 mismatch: $restoredHash."
}

Write-Host "Restore succeeded: $OutputPath"
Write-Host "Size: $($restored.Length)"
Write-Host "SHA-256: $restoredHash"
