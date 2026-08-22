[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'start-debug', 'status', 'logs', 'stop', 'restart', 'doctor')]
    [string]$Action = 'start',
    [switch]$Silent,
    [switch]$Json,
    [int]$Lines = 40
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$actualRoot = [System.IO.Path]::GetFullPath((git -C $projectRoot rev-parse --show-toplevel)).TrimEnd('\')
if ($actualRoot -ne $projectRoot.TrimEnd('\')) {
    Write-Error "Runtime control rejected the wrong worktree: $actualRoot"
    exit 2
}

$commonDir = (git -C $projectRoot rev-parse --git-common-dir).Trim()
if (-not [System.IO.Path]::IsPathRooted($commonDir)) {
    $commonDir = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $commonDir))
}
$sharedRoot = Split-Path -Parent $commonDir
$python = $env:PYTHON_EXE
if (-not $python -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $localPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $sharedPython = Join-Path $sharedRoot '.venv\Scripts\python.exe'
    $python = if (Test-Path -LiteralPath $localPython -PathType Leaf) { $localPython } else { $sharedPython }
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error 'Approved E-drive Python runtime was not found.'
    exit 2
}

$controller = Join-Path $projectRoot 'scripts\runtime_control.py'
$arguments = @('-X', 'utf8', $controller, $Action, '--lines', [string]$Lines)
if ($Json) { $arguments += '--json' }
if ($Silent) { $arguments += '--silent' }

$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
if ($Silent) {
    Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden
    exit 0
}

& $python @arguments
exit $LASTEXITCODE
