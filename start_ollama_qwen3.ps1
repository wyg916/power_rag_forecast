$ErrorActionPreference = "Stop"

$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) {
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $candidate) {
        $ollama = $candidate
    }
}
if (-not $ollama) {
    Write-Host "[ERROR] Ollama executable was not found."
    exit 1
}

$ready = $false
try {
    Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
    $ready = $true
} catch {
    $ready = $false
}

if (-not $ready) {
    Write-Host "[INFO] Ollama is not running. Starting it in background..."
    Start-Process -WindowStyle Hidden -FilePath $ollama -ArgumentList "serve"
    Start-Sleep -Seconds 3
}

$tags = $null
for ($i = 1; $i -le 8; $i++) {
    try {
        $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
        break
    } catch {
        Write-Host ("[WARN] Ollama tags check attempt " + $i + " failed: " + $_.Exception.Message)
        Start-Sleep -Seconds 2
    }
}
if (-not $tags) {
    Write-Host "[WARN] Ollama did not become ready in time. Continue without local model."
    exit 4
}
$names = @()
foreach ($item in $tags.models) {
    if ($item.name) {
        $names += $item.name
    } elseif ($item.model) {
        $names += $item.model
    }
}

$model = $names | Where-Object { $_ -eq "qwen3:4b" } | Select-Object -First 1
if (-not $model) {
    $model = $names | Where-Object { $_ -like "qwen3*" } | Select-Object -First 1
}
if (-not $model) {
    Write-Host ("[ERROR] Ollama is running, but qwen3 model was not found. Models: " + ($names -join ", "))
    exit 2
}

if ($env:OLLAMA_WARMUP_CHAT -ne "1") {
    Write-Host ("[OK] Ollama API is reachable. Model found: " + $model)
    Write-Host "[INFO] Skip chat warmup by default. Set OLLAMA_WARMUP_CHAT=1 to enable it."
    exit 0
}

$body = @{
    model = $model
    messages = @(
        @{ role = "system"; content = "You are a local model connectivity checker." },
        @{ role = "user"; content = "Reply exactly: model connected" }
    )
    stream = $false
    temperature = 0
} | ConvertTo-Json -Depth 5 -Compress

try {
    $resp = Invoke-RestMethod "http://127.0.0.1:11434/v1/chat/completions" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 120
    if (-not $resp.choices[0].message.content) {
        Write-Host "[ERROR] qwen3 connectivity check returned empty content."
        exit 3
    }
} catch {
    Write-Host ("[WARN] qwen3 warmup failed: " + $_.Exception.Message)
    Write-Host "[WARN] Web platform can continue; AI assistant will use evidence-first fallback until local model is available."
    exit 4
}

Write-Host ("[OK] Ollama is ready. Model: " + $model)
