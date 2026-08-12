param(
    [Parameter(Mandatory = $true)][string]$Marker,
    [Parameter(Mandatory = $true)][string]$EvidenceDir,
    [int]$ApiPort = 8026,
    [int]$WebPort = 5186,
    [int]$TimeoutSeconds = 3600
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$gitCommon = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
$gitCommonPath = if ([System.IO.Path]::IsPathRooted($gitCommon)) { $gitCommon } else { Join-Path $projectRoot $gitCommon }
$gitCommonPath = (Resolve-Path -LiteralPath $gitCommonPath).Path
$sharedRoot = Split-Path -Parent $gitCommonPath
$python = Join-Path $sharedRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Approved project Python runtime was not found: $python"
}
if (Test-Path -LiteralPath $Marker) {
    throw "Browser completion marker already exists: $Marker"
}
New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null

$env:AUTH_REQUIRED = '1'
$env:JWT_SECRET_KEY = 'final-functional-isolated-jwt-only-20260812-abcdef'
$env:FINAL_FUNCTIONAL_TEST_PASSWORD = 'FinalFunctionalOnly_20260812!'
$env:VITE_AUTH_REQUIRED = '1'
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
$env:AI_ASSISTANT_LLM_ENABLED = '1'
$env:TASK_EXECUTION_MODE = 'local_thread'
if (
    $env:RAG_PROFILE -ne 'enterprise' -or
    $env:RAG_RUNTIME_TARGET_MODE -ne 'preproduction_candidate' -or
    $env:RAG_RELEASE_ID -ne 'RAG-R1' -or
    $env:RAG_QDRANT_COLLECTION -ne 'rag_chunks_RAG-R1' -or
    $env:RAG_QDRANT_ALIAS -or
    $env:RAG_FILE_FALLBACK_ENABLED -ne '0' -or
    $env:RAG_PREWARM_ON_STARTUP -ne '1' -or
    $env:RAG_EMBEDDING_DIM -ne '1024' -or
    -not $env:RAG_QDRANT_API_KEY -or
    $env:QDRANT_ADMIN_API_KEY
) {
    throw 'Approved API-only RAG runtime profile was not inherited by the browser harness.'
}

& $python -X utf8 (Join-Path $projectRoot 'scripts\final_functional_acceptance_fixture.py') provision --output (Join-Path $EvidenceDir 'identity_provision.json')
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to initialize isolated functional-acceptance identities.'
}

$api = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', "$ApiPort", '--log-level', 'info') `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput (Join-Path $EvidenceDir 'api.stdout.log') `
    -RedirectStandardError (Join-Path $EvidenceDir 'api.stderr.log') `
    -WindowStyle Hidden -PassThru

$viteNode = Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $viteNode)) {
    throw "Workspace Vite runtime was not found: $viteNode"
}
$node = (Get-Command node.exe -ErrorAction Stop).Source
$web = Start-Process -FilePath $node `
    -ArgumentList @($viteNode, '--host', '127.0.0.1', '--port', "$WebPort") `
    -WorkingDirectory $frontendRoot `
    -RedirectStandardOutput (Join-Path $EvidenceDir 'web.stdout.log') `
    -RedirectStandardError (Join-Path $EvidenceDir 'web.stderr.log') `
    -WindowStyle Hidden -PassThru

try {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $healthUrl = "http://127.0.0.1:$ApiPort/api/health"
    while ($true) {
        if ($api.HasExited) { throw "Local API exited during RAG prewarm (code $($api.ExitCode))." }
        if ((Get-Date) -ge $deadline) { throw 'Local API RAG prewarm timed out.' }
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 5
            if ($health.StatusCode -eq 200) { break }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    while (-not (Test-Path -LiteralPath $Marker)) {
        if ($api.HasExited) { throw "Local API exited before browser verification (code $($api.ExitCode))." }
        if ($web.HasExited) { throw "Local web server exited before browser verification (code $($web.ExitCode))." }
        if ((Get-Date) -ge $deadline) { throw 'Browser verification marker timed out.' }
        Start-Sleep -Seconds 1
    }
}
finally {
    try {
        & $python (Join-Path $projectRoot 'scripts\final_functional_acceptance_fixture.py') cleanup --output (Join-Path $EvidenceDir 'identity_cleanup.json')
    }
    finally {
        foreach ($process in @($web, $api)) {
            if ($process -and -not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
                $process.WaitForExit(10000) | Out-Null
            }
        }
    }
}
