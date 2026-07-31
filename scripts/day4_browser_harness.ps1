param(
    [Parameter(Mandatory = $true)][string]$Marker,
    [Parameter(Mandatory = $true)][string]$EvidenceDir,
    [int]$ApiPort = 8014,
    [int]$WebPort = 5174,
    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$python = 'python.exe'

if (Test-Path -LiteralPath $Marker) {
    throw "Browser completion marker already exists: $Marker"
}
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null

$urlSeparator = if ($env:DATABASE_URL.Contains('?')) { '&' } else { '?' }
$env:SECURITY_DATABASE_URL = "$($env:DATABASE_URL)${urlSeparator}application_name=day4_browser_security"
$env:AUTH_REQUIRED = '1'
$env:JWT_SECRET_KEY = 'day4-browser-test-only-jwt-secret-0123456789abcdef'
$env:ADMIN_USERNAME = 'day4_browser_admin'
$env:ADMIN_PASSWORD = 'day4-browser-test-only-password-20260731'
$env:ADMIN_EMAIL = 'day4-browser-admin@example.invalid'
$env:ADMIN_DISPLAY_NAME = 'Day 4 Browser Admin'
$env:VITE_AUTH_REQUIRED = '1'
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"

& $python (Join-Path $projectRoot 'scripts\create_admin_user.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to initialize the isolated browser-test administrator.'
}

$api = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', "$ApiPort") `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput (Join-Path $EvidenceDir 'api.stdout.log') `
    -RedirectStandardError (Join-Path $EvidenceDir 'api.stderr.log') `
    -WindowStyle Hidden -PassThru

$web = Start-Process -FilePath 'npx.cmd' `
    -ArgumentList @('vite', '--host', '127.0.0.1', '--port', "$WebPort") `
    -WorkingDirectory $frontendRoot `
    -RedirectStandardOutput (Join-Path $EvidenceDir 'web.stdout.log') `
    -RedirectStandardError (Join-Path $EvidenceDir 'web.stderr.log') `
    -WindowStyle Hidden -PassThru

try {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not (Test-Path -LiteralPath $Marker)) {
        if ($api.HasExited) { throw "Local API exited before browser verification (code $($api.ExitCode))." }
        if ($web.HasExited) { throw "Local web server exited before browser verification (code $($web.ExitCode))." }
        if ((Get-Date) -ge $deadline) { throw 'Browser verification marker timed out.' }
        Start-Sleep -Seconds 1
    }
}
finally {
    foreach ($process in @($web, $api)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit(10000) | Out-Null
        }
    }
    foreach ($port in @($WebPort, $ApiPort)) {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $child = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
            if ($child.CommandLine -like "*$projectRoot*") {
                Stop-Process -Id $listener.OwningProcess -Force
            }
        }
    }
}
