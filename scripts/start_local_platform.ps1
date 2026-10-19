param(
    [ValidateRange(1, 65535)]
    [int]$Port = 7754,
    [switch]$EnablePublicReadOnly,
    [string]$Proxy = 'http://127.0.0.1:7897',
    [switch]$Once
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
$profilesFile = Join-Path $projectRoot 'runtime/platform-config/profiles.json'
$logDirectory = Join-Path $projectRoot 'runtime/platform-logs'

if ((Split-Path $projectRoot -Leaf) -ne 'block_chain_new_new' -or
    -not (Test-Path -LiteralPath (Join-Path $projectRoot 'pyproject.toml') -PathType Leaf)) {
    throw 'Run this launcher from the independent block_chain_new_new project.'
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The project .venv Python is missing.'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'apps/web/dist/index.html') -PathType Leaf)) {
    throw 'Build apps/web first; its dist/index.html is required.'
}
$profiles = @()
try {
    if (Test-Path -LiteralPath $profilesFile -PathType Leaf) {
        $profiles = @(Get-Content -LiteralPath $profilesFile -Raw | ConvertFrom-Json)
    }
} catch {
    throw 'The private profiles.json file must contain valid JSON.'
}
foreach ($profile in $profiles) {
    $requiredProfileFields = @('registration_reference', 'candidate_key', 'policy_id', 'history_run', 'plan_run')
    switch ([string]$profile.policy_id) {
        'liquidity-history-v1' { $requiredProfileFields += 'context_run' }
        'prediction-history-v1' { }
        default { throw 'A private worker profile uses an unsupported policy.' }
    }
    foreach ($field in $requiredProfileFields) {
        if ([string]::IsNullOrWhiteSpace([string]$profile.$field)) {
            throw 'A private worker profile is incomplete.'
        }
    }
    if ($profile.policy_id -eq 'liquidity-history-v1' -and
        ($null -eq $profile.rpc_runs -or @($profile.rpc_runs).Count -eq 0)) {
        throw 'A private worker profile is missing its retained RPC evidence directories.'
    }
}
if ($EnablePublicReadOnly -and [string]::IsNullOrWhiteSpace($Proxy)) {
    throw 'Public read-only execution requires an explicit HTTP proxy.'
}
$listeners = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq $Port })
if ($listeners.Count -gt 0) {
    throw "API port $Port is occupied; its existing service will not be changed or reused."
}

& (Join-Path $PSScriptRoot 'start_local_postgres.ps1')

$previousUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')
$previousEncoding = [Environment]::GetEnvironmentVariable('PYTHONIOENCODING', 'Process')
$apiProcess = $null
$apiStartTicks = $null
$http = $null
$handler = $null
$locationPushed = $false
try {
    [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', 'utf-8', 'Process')
    Push-Location -LiteralPath $projectRoot
    $locationPushed = $true
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $runName = 'platform-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $stdout = Join-Path $logDirectory ($runName + '.api.stdout.log')
    $stderr = Join-Path $logDirectory ($runName + '.api.stderr.log')
    $apiArguments = @('-m', 'uvicorn', 'reputation_platform.api:create_app', '--factory', '--host', '127.0.0.1', '--port', [string]$Port)
    $apiProcess = Start-Process -FilePath $python -ArgumentList $apiArguments -WorkingDirectory $projectRoot `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    # Retain the original process handle so cleanup cannot target a later recycled PID.
    $apiProcess.Handle | Out-Null
    $apiStartTicks = $apiProcess.StartTime.ToUniversalTime().Ticks

    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object Net.Http.HttpClientHandler
    $handler.UseProxy = $false
    $http = New-Object Net.Http.HttpClient($handler)
    $http.Timeout = [Threading.Timeout]::InfiniteTimeSpan
    $healthUrl = "http://127.0.0.1:$Port/api/health"
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $ready = $false
    while ($timer.ElapsedMilliseconds -lt 15000) {
        if ($apiProcess.HasExited) { throw 'The new API process exited before becoming healthy; inspect its runtime logs.' }
        $remaining = 15000 - $timer.ElapsedMilliseconds
        $cancellation = New-Object Threading.CancellationTokenSource
        $cancellation.CancelAfter([int][Math]::Min(1000, $remaining))
        $response = $null
        try {
            $response = $http.GetAsync($healthUrl, $cancellation.Token).GetAwaiter().GetResult()
            if ($response.StatusCode -eq [Net.HttpStatusCode]::OK) {
                $health = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
                if ($health.status -eq 'ok' -and $health.database -eq 'ready') {
                    $ready = $true
                }
            }
        } catch {
            # Startup connections may fail while uvicorn initializes; the deadline remains fixed.
        } finally {
            if ($null -ne $response) { $response.Dispose() }
            $cancellation.Dispose()
        }
        if ($ready) { break }
        $remaining = 15000 - $timer.ElapsedMilliseconds
        if ($remaining -gt 0) { Start-Sleep -Milliseconds ([int][Math]::Min(250, $remaining)) }
    }
    if (-not $ready -or $apiProcess.HasExited) {
        throw 'The new API did not pass its database health check within 15 seconds; inspect its runtime logs.'
    }
    Write-Output "Platform ready at http://127.0.0.1:$Port/; stopping this launcher also stops its API."
    Write-Output 'PostgreSQL remains running; use scripts/stop_local_postgres.ps1 to stop that project instance.'
    $workerArguments = @('-m', 'reputation_platform.worker')
    if ($EnablePublicReadOnly) {
        $workerArguments += @('--enable-public-readonly', '--proxy', $Proxy)
    }
    if ($Once) { $workerArguments += '--once' }
    & $python @workerArguments
    if ($LASTEXITCODE -ne 0) { throw "The foreground worker exited with code $LASTEXITCODE." }
} finally {
    if ($null -ne $http) { $http.Dispose() }
    if ($null -ne $handler) { $handler.Dispose() }
    try {
        if ($null -ne $apiProcess -and -not $apiProcess.HasExited -and
            $apiProcess.StartTime.ToUniversalTime().Ticks -eq $apiStartTicks) {
            $apiProcess.Kill()
            $apiProcess.WaitForExit(5000) | Out-Null
        }
    } finally {
        if ($null -ne $apiProcess) { $apiProcess.Dispose() }
        if ($locationPushed) { Pop-Location }
        [Environment]::SetEnvironmentVariable('PYTHONUTF8', $previousUtf8, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONIOENCODING', $previousEncoding, 'Process')
    }
}
