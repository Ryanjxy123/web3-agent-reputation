$ErrorActionPreference = 'Stop'

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeDirectory = Join-Path $projectRoot 'runtime'
$dataDirectory = [IO.Path]::GetFullPath((Join-Path $runtimeDirectory 'platform-postgres'))
$configDirectory = [IO.Path]::GetFullPath((Join-Path $runtimeDirectory 'platform-config'))
$toolDirectory = 'D:\web3-runtime\tools\postgresql-17.11\pgsql\bin'
$markerFile = Join-Path $configDirectory 'postgres-instance.json'
$pgCtl = Join-Path $toolDirectory 'pg_ctl.exe'
$nativePathEncoding = [Text.Encoding]::GetEncoding((Get-WinSystemLocale).TextInfo.ANSICodePage)

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'pyproject.toml'))) {
    throw 'Run the script from the web3-agent-reputation project.'
}
foreach ($directory in @($runtimeDirectory, $dataDirectory, $configDirectory)) {
    if ((Test-Path -LiteralPath $directory) -and
        ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The project PostgreSQL directories must not be links or junctions.'
    }
}
if (-not (Test-Path -LiteralPath $dataDirectory)) {
    Write-Output 'The project PostgreSQL instance has not been initialized.'
    exit 0
}
if (-not (Test-Path -LiteralPath $markerFile -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $dataDirectory 'PG_VERSION') -PathType Leaf)) {
    throw 'The data directory is not a confirmed project PostgreSQL instance.'
}
$marker = Get-Content -LiteralPath $markerFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($marker.purpose -ne 'web3-reputation-local-postgres-v1' -or
    $marker.project_root -ne $projectRoot -or $marker.data_directory -ne $dataDirectory -or
    $marker.tool_directory -ne $toolDirectory -or $marker.port -ne 55438 -or
    $marker.role -ne 'reputation' -or $marker.database -ne 'reputation' -or
    (Get-Content -LiteralPath (Join-Path $dataDirectory 'PG_VERSION') -Raw).Trim() -ne '17') {
    throw 'The data directory belongs to a different PostgreSQL configuration.'
}
if (-not (Test-Path -LiteralPath $pgCtl -PathType Leaf)) {
    throw 'The pinned PostgreSQL control tool is unavailable.'
}
$status = & $pgCtl -D $dataDirectory status 2>&1
if ($LASTEXITCODE -eq 3) {
    Write-Output 'The project PostgreSQL instance is already stopped.'
    exit 0
}
if ($LASTEXITCODE -ne 0) { throw 'The project PostgreSQL status could not be confirmed.' }
$pidLines = @([IO.File]::ReadAllLines((Join-Path $dataDirectory 'postmaster.pid'), $nativePathEncoding))
$serverProcessId = [int]$pidLines[0]
$serverProcess = Get-Process -Id $serverProcessId -ErrorAction Stop
if ($pidLines.Count -lt 4 -or [IO.Path]::GetFullPath($pidLines[1]) -ne $dataDirectory -or
    [int]$pidLines[3] -ne 55438 -or $serverProcess.Path -ne (Join-Path $toolDirectory 'postgres.exe')) {
    throw 'The process in postmaster.pid is not the confirmed project PostgreSQL instance.'
}
$listeners = @(Get-NetTCPConnection -LocalPort 55438 -State Listen -ErrorAction SilentlyContinue)
if (@($listeners | Where-Object { $_.OwningProcess -ne $serverProcessId }).Count -gt 0) {
    throw 'Port 55438 is owned by another process; nothing will be stopped.'
}
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$process = Start-Process -FilePath $pgCtl -ArgumentList @('-D', ('"' + $dataDirectory + '"'), 'stop', '-m', 'fast', '-w', '-t', '30') `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $configDirectory ('pg-stop-' + $stamp + '.stdout.log')) `
    -RedirectStandardError (Join-Path $configDirectory ('pg-stop-' + $stamp + '.stderr.log'))
$process.Handle | Out-Null
$process.WaitForExit()
if ($process.ExitCode -ne 0) { throw 'Stopping the project PostgreSQL instance failed; its data is retained.' }
Write-Output 'The project PostgreSQL instance is stopped; its data and credentials are retained.'
