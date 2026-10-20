$ErrorActionPreference = 'Stop'

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeDirectory = Join-Path $projectRoot 'runtime'
$dataDirectory = [IO.Path]::GetFullPath((Join-Path $runtimeDirectory 'platform-postgres'))
$configDirectory = [IO.Path]::GetFullPath((Join-Path $runtimeDirectory 'platform-config'))
$toolDirectory = 'D:\web3-runtime\tools\postgresql-17.11\pgsql\bin'
$port = 55438
$role = 'reputation'
$database = 'reputation'
$markerFile = Join-Path $configDirectory 'postgres-instance.json'
$passwordFile = Join-Path $configDirectory 'db-password.txt'
$urlFile = Join-Path $configDirectory 'database-url.txt'
$postgres = Join-Path $toolDirectory 'postgres.exe'
$pgCtl = Join-Path $toolDirectory 'pg_ctl.exe'
$psql = Join-Path $toolDirectory 'psql.exe'
$utf8 = New-Object Text.UTF8Encoding($false)
# Windows PostgreSQL writes native paths using the system ANSI code page.
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
foreach ($name in @('postgres.exe', 'initdb.exe', 'pg_ctl.exe', 'pg_isready.exe', 'psql.exe', 'createdb.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $toolDirectory $name) -PathType Leaf)) {
        throw 'The pinned PostgreSQL 17.11 tools are unavailable.'
    }
}
$version = & $postgres --version
if ($LASTEXITCODE -ne 0 -or $version -notmatch 'PostgreSQL\) 17\.11(?:\s|$)') {
    throw 'The PostgreSQL tools do not match the pinned 17.11 version.'
}

$versionFile = Join-Path $dataDirectory 'PG_VERSION'
$initialized = Test-Path -LiteralPath $versionFile -PathType Leaf
if (Test-Path -LiteralPath $markerFile -PathType Leaf) {
    $marker = Get-Content -LiteralPath $markerFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($marker.purpose -ne 'web3-reputation-local-postgres-v1' -or
        $marker.project_root -ne $projectRoot -or $marker.data_directory -ne $dataDirectory -or
        $marker.tool_directory -ne $toolDirectory -or $marker.port -ne $port -or
        $marker.role -ne $role -or $marker.database -ne $database) {
        throw 'The existing PostgreSQL instance marker belongs to a different configuration.'
    }
} elseif ($initialized -or
          ((Test-Path -LiteralPath $dataDirectory) -and (Get-ChildItem -LiteralPath $dataDirectory -Force | Select-Object -First 1)) -or
          ((Test-Path -LiteralPath $configDirectory) -and (Get-ChildItem -LiteralPath $configDirectory -Force | Select-Object -First 1))) {
    throw 'Existing unmarked PostgreSQL data or configuration will not be changed.'
}
if ($initialized -and (Get-Content -LiteralPath $versionFile -Raw).Trim() -ne '17') {
    throw 'The retained data directory is not PostgreSQL 17.'
}
if (-not $initialized -and (Test-Path -LiteralPath $dataDirectory) -and
    (Get-ChildItem -LiteralPath $dataDirectory -Force | Select-Object -First 1)) {
    throw 'The incomplete data directory is retained; it will not be deleted or reinitialized.'
}

$listeners = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq $port })
if ($listeners.Count -gt 0) {
    $pidFile = Join-Path $dataDirectory 'postmaster.pid'
    if (-not $initialized -or -not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
        throw 'Port 55438 is occupied; the existing process will not be changed.'
    }
    $pidLines = @([IO.File]::ReadAllLines($pidFile, $nativePathEncoding))
    $serverProcessId = [int]$pidLines[0]
    $serverProcess = Get-Process -Id $serverProcessId -ErrorAction Stop
    $controlStatus = & $pgCtl -D $dataDirectory status 2>&1
    $controlExitCode = $LASTEXITCODE
    if ($pidLines.Count -lt 4 -or [IO.Path]::GetFullPath($pidLines[1]) -ne $dataDirectory -or
        [int]$pidLines[3] -ne $port -or $serverProcess.Path -ne $postgres -or
        $controlExitCode -ne 0 -or
        @($listeners | Where-Object { $_.Address.ToString() -ne '127.0.0.1' }).Count -gt 0) {
        throw 'Port 55438 does not belong exclusively to this project instance.'
    }
}

[IO.Directory]::CreateDirectory($configDirectory) | Out-Null
function Write-NewPrivateFile([string]$Path, [string]$Text) {
    $stream = New-Object IO.FileStream($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    try {
        $bytes = $utf8.GetBytes($Text)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally {
        $stream.Dispose()
    }
}
function Invoke-HiddenTool([string]$Executable, [string[]]$Arguments, [string]$Label) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
    $stdout = Join-Path $configDirectory ($Label + '-' + $stamp + '.stdout.log')
    $stderr = Join-Path $configDirectory ($Label + '-' + $stamp + '.stderr.log')
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    # Start-Process -Wait also waits for pg_ctl's persistent server descendants on Windows.
    $process.Handle | Out-Null
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw ($Label + ' failed; retained logs are in runtime/platform-config.')
    }
}

if (-not (Test-Path -LiteralPath $markerFile)) {
    $marker = [ordered]@{
        purpose = 'web3-reputation-local-postgres-v1'
        project_root = $projectRoot
        data_directory = $dataDirectory
        tool_directory = $toolDirectory
        port = $port
        role = $role
        database = $database
    }
    Write-NewPrivateFile $markerFile ($marker | ConvertTo-Json)
}
if ($initialized -and (-not (Test-Path -LiteralPath $passwordFile -PathType Leaf) -or
                      -not (Test-Path -LiteralPath $urlFile -PathType Leaf))) {
    throw 'The initialized instance is missing its existing credential files; no password will be replaced.'
}
if (-not (Test-Path -LiteralPath $passwordFile)) {
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $bytes = New-Object byte[] 32
        $random.GetBytes($bytes)
        $dbPassword = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
    } finally {
        $random.Dispose()
    }
    Write-NewPrivateFile $passwordFile $dbPassword
} else {
    $dbPassword = [IO.File]::ReadAllText($passwordFile).Trim()
}
if ($dbPassword -notmatch '^[0-9a-f]{64}$') {
    throw 'The existing credential file is not the project-generated password format.'
}
$connectionUrl = "postgresql://reputation:${dbPassword}@127.0.0.1:55438/reputation"
if (-not (Test-Path -LiteralPath $urlFile)) {
    Write-NewPrivateFile $urlFile $connectionUrl
} elseif ([IO.File]::ReadAllText($urlFile).Trim() -cne $connectionUrl) {
    throw 'The retained connection file differs from this project instance; it will not be replaced.'
}

if (-not $initialized) {
    Invoke-HiddenTool (Join-Path $toolDirectory 'initdb.exe') @(
        '-D', ('"' + $dataDirectory + '"'), '--username=reputation', '--encoding=UTF8', '--locale=C',
        '--auth-local=scram-sha-256', '--auth-host=scram-sha-256', ('--pwfile="' + $passwordFile + '"')
    ) 'initdb'
    $settings = @"

# Independent Web3 Reputation local platform instance.
listen_addresses = '127.0.0.1'
port = 55438
password_encryption = 'scram-sha-256'
log_statement = 'none'
"@
    [IO.File]::AppendAllText((Join-Path $dataDirectory 'postgresql.conf'), $settings, $utf8)
    $hba = @"
# Only the project role, over local TCP, authenticated with SCRAM.
host postgres,reputation reputation 127.0.0.1/32 scram-sha-256
host postgres,reputation reputation ::1/128 scram-sha-256
host reputation_verification reputation 127.0.0.1/32 scram-sha-256
"@
    [IO.File]::WriteAllText((Join-Path $dataDirectory 'pg_hba.conf'), $hba, $utf8)
}
$configuredPort = & $postgres -D $dataDirectory -C port
if ($LASTEXITCODE -ne 0 -or $configuredPort.Trim() -ne '55438') {
    throw 'The retained PostgreSQL port configuration does not match this project.'
}
$configuredListen = & $postgres -D $dataDirectory -C listen_addresses
if ($LASTEXITCODE -ne 0 -or $configuredListen.Trim() -ne '127.0.0.1') {
    throw 'The retained PostgreSQL configuration does not bind exclusively to IPv4 loopback.'
}
if ($listeners.Count -eq 0) {
    Invoke-HiddenTool $pgCtl @('-D', ('"' + $dataDirectory + '"'), '-l',
        ('"' + (Join-Path $configDirectory 'postgresql.log') + '"'), 'start', '-w', '-t', '30') 'pg-start'
}

$previousPgPassword = [Environment]::GetEnvironmentVariable('PGPASSWORD', 'Process')
try {
    [Environment]::SetEnvironmentVariable('PGPASSWORD', $dbPassword, 'Process')
    & (Join-Path $toolDirectory 'pg_isready.exe') -h 127.0.0.1 -p 55438 -U reputation -d postgres -t 5 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'The project PostgreSQL readiness check failed.' }
    $psqlArguments = @('-h', '127.0.0.1', '-p', '55438', '-U', 'reputation', '-w', '-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1')
    # Hex avoids PowerShell/psql transcoding of PostgreSQL's native Windows path.
    $identity = & $psql @psqlArguments -d postgres -c "SELECT encode(current_setting('data_directory')::bytea, 'hex'), current_setting('port'), current_setting('listen_addresses'), current_setting('server_version_num');"
    if ($LASTEXITCODE -ne 0) { throw 'The project PostgreSQL authentication check failed.' }
    $fields = ($identity.Trim() -split '\|')
    $pathBytes = @(for ($index = 0; $index -lt $fields[0].Length; $index += 2) {
        [Convert]::ToByte($fields[0].Substring($index, 2), 16)
    })
    $reportedDirectory = $nativePathEncoding.GetString([byte[]]$pathBytes)
    if ($fields.Count -ne 4 -or [IO.Path]::GetFullPath($reportedDirectory) -ne $dataDirectory -or
        $fields[1] -ne '55438' -or $fields[2] -ne '127.0.0.1' -or $fields[3] -ne '170011') {
        throw 'The authenticated PostgreSQL identity does not match the expected project instance.'
    }
    $exists = & $psql @psqlArguments -d postgres -c "SELECT 1 FROM pg_database WHERE datname = 'reputation';"
    if ($LASTEXITCODE -ne 0) { throw 'The project database lookup failed.' }
    if (-not $exists) {
        & (Join-Path $toolDirectory 'createdb.exe') -h 127.0.0.1 -p 55438 -U reputation -w -O reputation -E UTF8 reputation
        if ($LASTEXITCODE -ne 0) { throw 'Creating the project reputation database failed.' }
    }
    $databaseIdentity = & $psql @psqlArguments -d reputation -c "SELECT current_database(), current_user, current_setting('server_version_num');"
    if ($LASTEXITCODE -ne 0 -or $databaseIdentity.Trim() -ne 'reputation|reputation|170011') {
        throw 'The final project database connection check failed.'
    }
} finally {
    [Environment]::SetEnvironmentVariable('PGPASSWORD', $previousPgPassword, 'Process')
    $dbPassword = $null
    $connectionUrl = $null
}
Write-Output 'PostgreSQL 17.11 is ready at 127.0.0.1:55438; database=reputation; role=reputation.'
Write-Output 'Connection file: runtime/platform-config/database-url.txt (contents are not printed).'
