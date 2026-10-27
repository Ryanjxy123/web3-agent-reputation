param(
    [ValidateRange(1,65535)][int]$Port = 7754,
    [switch]$EnablePublicReadOnly,
    [string]$Proxy = 'http://127.0.0.1:7897'
)

$ErrorActionPreference = 'Stop'
$projectDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $projectDirectory '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Install the project Python environment first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectDirectory 'apps/web/dist/index.html') -PathType Leaf)) {
    throw 'Build apps/web before starting the platform.'
}
if ($EnablePublicReadOnly -and [string]::IsNullOrWhiteSpace($Proxy)) { throw 'Public reads require an explicit proxy.' }
$listeners = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq $Port })
if ($listeners.Count) { throw "Port $Port already has a listener; it will not be replaced." }

& (Join-Path $PSScriptRoot 'start_local_postgres.ps1')
$logDirectory = Join-Path $projectDirectory ('runtime/background-platform-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $logDirectory | Out-Null
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$apiArguments = @('-m','uvicorn','reputation_platform.api:create_app','--factory','--host','127.0.0.1','--port',[string]$Port)
$api = Start-Process -FilePath $python -ArgumentList $apiArguments -WorkingDirectory $projectDirectory -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDirectory 'api.stdout.log') -RedirectStandardError (Join-Path $logDirectory 'api.stderr.log') -PassThru
$api.Handle | Out-Null
$apiTicks = $api.StartTime.ToUniversalTime().Ticks
$handler = [Net.Http.HttpClientHandler]::new()
$handler.UseProxy = $false
$http = [Net.Http.HttpClient]::new($handler)
$http.Timeout = [TimeSpan]::FromSeconds(1)
$ready = $false
try {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 15 -and -not $api.HasExited) {
        try {
            $response = $http.GetAsync("http://127.0.0.1:$Port/api/health").GetAwaiter().GetResult()
            $health = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
            $ready = $response.IsSuccessStatusCode -and $health.database -eq 'ready'
            $response.Dispose()
            if ($ready) { break }
        } catch { }
        Start-Sleep -Milliseconds 250
    }
} finally { $http.Dispose(); $handler.Dispose() }
if (-not $ready) {
    if (-not $api.HasExited -and $api.StartTime.ToUniversalTime().Ticks -eq $apiTicks) { $api.Kill($true) }
    throw 'The new API failed its database health check. Inspect this run directory; PostgreSQL is retained.'
}
$workerArguments = @('-m','reputation_platform.worker')
if ($EnablePublicReadOnly) { $workerArguments += @('--enable-public-readonly','--proxy',$Proxy) }
$worker = Start-Process -FilePath $python -ArgumentList $workerArguments -WorkingDirectory $projectDirectory -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDirectory 'worker.stdout.log') -RedirectStandardError (Join-Path $logDirectory 'worker.stderr.log') -PassThru
$worker.Handle | Out-Null
$receipt = [ordered]@{ started_at=[DateTime]::UtcNow.ToString('o'); project_root=$projectDirectory;
    url="http://127.0.0.1:$Port/"; api_pid=$api.Id; api_start_ticks=$apiTicks;
    worker_pid=$worker.Id; worker_start_ticks=$worker.StartTime.ToUniversalTime().Ticks;
    worker_mode=$(if ($EnablePublicReadOnly) {'online'} else {'public-off'}); independent_processes=$true }
[IO.File]::WriteAllText((Join-Path $logDirectory 'process.json'),($receipt | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
Write-Output "Platform started at http://127.0.0.1:$Port/; closing this terminal keeps the API and worker running."
Write-Output ('Process receipt: ' + (Join-Path $logDirectory 'process.json'))
