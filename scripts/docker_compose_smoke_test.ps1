param(
    [string]$ComposeFile = "docker-compose.enterprise.yml",
    [string]$ProjectName = "power-trading-ai-smoke",
    [int]$BackendPort = 18000,
    [int]$FrontendPort = 18080,
    [int]$PostgresPort = 15432,
    [int]$RedisPort = 16379,
    [string]$DockerContext = "desktop-linux",
    [switch]$NoBuild,
    [switch]$StopAfter
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ComposePath = Join-Path $Root $ComposeFile

if (-not (Test-Path $ComposePath)) {
    throw "Compose file not found: $ComposePath"
}

$env:COMPOSE_PROJECT_NAME = $ProjectName
$env:POSTGRES_DB = "power_trading"
$env:POSTGRES_USER = "postgres"
$env:POSTGRES_PASSWORD = "postgres"
$env:POSTGRES_PORT = [string]$PostgresPort
$env:REDIS_PORT = [string]$RedisPort
$env:BACKEND_PORT = [string]$BackendPort
$env:FRONTEND_PORT = [string]$FrontendPort
$env:AUTH_REQUIRED = "0"
$env:AI_ASSISTANT_REQUIRE_EVIDENCE = "1"
$env:AI_ASSISTANT_ALLOW_EXTERNAL_FACTS = "0"

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    & docker --context $DockerContext compose -f $ComposePath @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed: $($ComposeArgs -join ' ')"
    }
}

function Wait-Http {
    param(
        [string]$Url,
        [string]$Name,
        [int]$TimeoutSeconds = 180
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "[OK] $Name $Url -> $($response.StatusCode)"
                return
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 3
    }
    throw "Timeout waiting for $Name $Url. Last error: $lastError"
}

function Assert-JsonCode {
    param(
        [string]$Url,
        [string]$Name
    )
    $payload = Invoke-RestMethod -Uri $Url -TimeoutSec 10
    if ($null -ne $payload.code -and [int]$payload.code -ne 0) {
        throw "$Name returned code=$($payload.code), message=$($payload.message)"
    }
    Write-Host "[OK] $Name"
}

Push-Location $Root
try {
    Write-Host "[INFO] Validate compose file."
    Write-Host "[INFO] Docker context: $DockerContext"
    Invoke-Compose @("config")

    if ($NoBuild) {
        Write-Host "[INFO] Start enterprise stack without rebuild."
        Invoke-Compose @("up", "-d")
    } else {
        Write-Host "[INFO] Build and start enterprise stack."
        Invoke-Compose @("up", "-d", "--build")
    }

    Wait-Http "http://127.0.0.1:$BackendPort/api/health" "backend health"
    Wait-Http "http://127.0.0.1:$FrontendPort/health" "frontend health"
    Wait-Http "http://127.0.0.1:$FrontendPort/api/health" "frontend api proxy"

    Assert-JsonCode "http://127.0.0.1:$FrontendPort/api/data/quality" "data quality api"
    Assert-JsonCode "http://127.0.0.1:$FrontendPort/api/settings/health" "settings health api"
    Assert-JsonCode "http://127.0.0.1:$FrontendPort/api/strategy/config" "strategy config api"

    Write-Host "[INFO] Check Alembic revision in backend container."
    Invoke-Compose @("exec", "-T", "backend", "alembic", "current")

    Write-Host "[INFO] Check Celery worker process."
    Invoke-Compose @("exec", "-T", "worker", "python", "-c", "from backend.app.workers.celery_app import celery_app; print('celery_app=', bool(celery_app))")

    Write-Host "[INFO] Compose service status."
    Invoke-Compose @("ps")

    Write-Host "[DONE] Docker Compose enterprise smoke test passed."
    Write-Host "[INFO] Frontend: http://127.0.0.1:$FrontendPort"
    Write-Host "[INFO] Backend docs: http://127.0.0.1:$BackendPort/docs"
} finally {
    if ($StopAfter) {
        Write-Host "[INFO] Stop containers without deleting volumes."
        Invoke-Compose @("down")
    }
    Pop-Location
}
