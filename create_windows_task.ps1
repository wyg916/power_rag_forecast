param (
    [string]$TaskName,
    [string]$RunTime,
    [string]$Mode,
    [bool]$Highest
)

$ErrorActionPreference = 'Stop'

if (-not $TaskName) { $TaskName = 'PowerMarketDailyAutomation' }
if (-not $RunTime) { $RunTime = '06:30' }
if (-not $Mode) { $Mode = 'refresh_data' }
if ($PSBoundParameters.ContainsKey('Highest') -eq $false) { $Highest = $true }

if ($Mode -notin @(
    'fast_forecast',
    'refresh_fast_forecast',
    'retrain_model',
    'model_auto_optimize',
    'full',
    'refresh_data',
    'skip_prediction',
    'prediction_report_only',
    'model_ops_daily',
    'health_check',
    'smoke_test',
    'web_smoke_test'
)) {
    throw 'Mode must be one of: fast_forecast, refresh_fast_forecast, retrain_model, model_auto_optimize, full, refresh_data, skip_prediction, prediction_report_only, model_ops_daily, health_check, smoke_test, web_smoke_test'
}

if ($RunTime -notmatch '^\d{2}:\d{2}$') {
    throw 'RunTime must use HH:mm, for example 06:30'
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$batchMap = @{
    fast_forecast = 'run_daily_pipeline_fast_forecast.bat'
    refresh_fast_forecast = 'run_daily_pipeline_refresh_fast_forecast.bat'
    retrain_model = 'run_daily_pipeline_retrain_model.bat'
    model_auto_optimize = 'run_model_auto_optimize.bat'
    full = 'run_daily_pipeline.bat'
    refresh_data = 'run_daily_pipeline_refresh_data.bat'
    skip_prediction = 'run_daily_pipeline_skip_prediction.bat'
    prediction_report_only = 'run_daily_pipeline_prediction_report_only.bat'
    model_ops_daily = 'run_model_ops_daily.bat'
    health_check = 'run_health_check.bat'
    smoke_test = 'run_smoke_test.bat'
    web_smoke_test = 'run_web_smoke_test.bat'
}

$batchPath = Join-Path $projectRoot $batchMap[$Mode]
if (-not (Test-Path $batchPath)) {
    throw "Batch file not found: $batchPath"
}

$taskCommand = "cmd.exe /c `"set NO_PAUSE=1&& call `"`"$batchPath`"`"`""
$arguments = @(
    '/Create',
    '/F',
    '/SC', 'DAILY',
    '/TN', $TaskName,
    '/TR', $taskCommand,
    '/ST', $RunTime
)

if ($Highest) {
    $arguments += @('/RL', 'HIGHEST')
}

$output = & schtasks.exe @arguments 2>&1
$verify = & schtasks.exe /Query /TN $TaskName /FO LIST /V 2>&1

Write-Host 'Task scheduler entry created.'
Write-Host "TaskName: $TaskName"
Write-Host "Mode: $Mode"
Write-Host "RunTime: $RunTime"
Write-Host "BatchPath: $batchPath"
Write-Host ''
Write-Host 'CreateResult:'
$output | ForEach-Object { Write-Host $_ }
Write-Host ''
Write-Host 'TaskDetails:'
$verify | ForEach-Object { Write-Host $_ }
