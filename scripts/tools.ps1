param([switch]$Install)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolRoot = Join-Path $RepoRoot 'runtime/tools'
$UvEnvironment = Join-Path $ToolRoot 'uv-env'
$UvBin = Join-Path $UvEnvironment 'Scripts'
$FoundryBin = Join-Path $ToolRoot 'foundry-v1.8.4'
$PostgresRoot = Join-Path $ToolRoot 'postgresql-17.11'
$PostgresBin = Join-Path $PostgresRoot 'pgsql/bin'
$DockerBin = Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin'
if ($Install) {
    if (-not (Test-Path -LiteralPath (Join-Path $UvBin 'uv.exe'))) {
        python -m venv $UvEnvironment
        if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed' }
        & (Join-Path $UvBin 'python.exe') -m pip install 'uv==0.9.3'
        if ($LASTEXITCODE -ne 0) { throw 'uv installation failed' }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FoundryBin 'forge.exe'))) {
        $ArchivePath = Join-Path $ToolRoot 'foundry_v1.8.4_win32_amd64.zip'
        if (-not (Test-Path -LiteralPath $ArchivePath)) {
            Invoke-WebRequest -Uri 'https://github.com/foundry-rs/foundry/releases/download/v1.8.4/foundry_v1.8.4_win32_amd64.zip' -OutFile $ArchivePath
        }
        $ExpectedHash = '7927f41b36fbe815f858ebb3e9fb7ca07a9b53fed67ccca6471acd7efd203aa1'
        if ((Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) {
            throw 'Foundry archive checksum mismatch'
        }
        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $FoundryBin
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PostgresBin 'postgres.exe'))) {
        $PgArchive = Join-Path $ToolRoot 'postgresql-17.11-windows-x64.zip'
        if (-not (Test-Path -LiteralPath $PgArchive)) {
            Invoke-WebRequest -Uri 'https://sbp.enterprisedb.com/getfile.jsp?fileid=1260616' -OutFile $PgArchive
        }
        $PgExpectedHash = '80379b2c04d51c30225532e0ae04509899141e9957ed096fe749d7fd9df8f82f'
        if ((Get-FileHash -LiteralPath $PgArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $PgExpectedHash) {
            throw 'PostgreSQL archive checksum mismatch'
        }
        Expand-Archive -LiteralPath $PgArchive -DestinationPath $PostgresRoot
    }
}
$env:PATH = "$UvBin;$FoundryBin;$PostgresBin;$env:PATH"
if (Test-Path -LiteralPath $DockerBin) { $env:PATH = "$DockerBin;$env:PATH" }
$env:UV_LINK_MODE = 'copy'
Write-Output 'Project tools added to this PowerShell process only.'
