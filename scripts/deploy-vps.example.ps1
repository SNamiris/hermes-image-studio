[CmdletBinding()]
param(
    [string]$HostAddress = $env:HERMES_VPS_HOST,
    [string]$KeyPath = $env:HERMES_VPS_KEY,
    [int]$SocksProxyPort = $(if ($env:HERMES_SOCKS_PORT) { [int]$env:HERMES_SOCKS_PORT } else { 0 }),
    [string]$GitBinDir = 'C:\Program Files\Git\mingw64\bin',
    [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($HostAddress)) {
    throw "Missing -HostAddress (or env HERMES_VPS_HOST), e.g. 'ubuntu@your-server-ip'."
}
if ([string]::IsNullOrWhiteSpace($KeyPath)) {
    throw "Missing -KeyPath (or env HERMES_VPS_KEY), e.g. 'C:\path\to\your-key.pem'."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$novelaiDir = Join-Path $repoRoot 'plugins\image_gen\novelai'
$skillFile = Join-Path $repoRoot 'skills\novelai-prompting\SKILL.md'

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "SSH key not found: $KeyPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $novelaiDir '__init__.py') -PathType Leaf)) {
    throw "NovelAI plugin not found in $novelaiDir"
}
if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
    throw "NovelAI skill not found at $skillFile"
}

$previousPath = $env:Path
try {
    if ($GitBinDir -and (Test-Path -LiteralPath $GitBinDir -PathType Container)) {
        $env:Path = "$GitBinDir;$previousPath"
    }

    $sshCommon = @(
        '-i', $KeyPath
        '-o', 'BatchMode=yes'
        '-o', 'IdentitiesOnly=yes'
        '-o', 'StrictHostKeyChecking=yes'
        '-o', 'ConnectTimeout=15'
    )

    if ($SocksProxyPort -gt 0 -and
        (Get-NetTCPConnection -LocalPort $SocksProxyPort -State Listen -ErrorAction SilentlyContinue) -and
        (Test-Path -LiteralPath (Join-Path $GitBinDir 'connect.exe') -PathType Leaf)) {
        Write-Host "Using SOCKS5 proxy 127.0.0.1:$SocksProxyPort"
        $sshCommon += @('-o', "ProxyCommand=connect.exe -5 -S 127.0.0.1:$SocksProxyPort %h %p")
    }

    Write-Host "Ensuring target directories on $HostAddress..."
    & ssh.exe @sshCommon $HostAddress 'mkdir -p ~/.hermes/plugins/image_gen/novelai ~/.hermes/skills/creative/novelai-prompting'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host 'Uploading NovelAI plugin...'
    & scp.exe @sshCommon `
        (Join-Path $novelaiDir 'plugin.yaml') `
        (Join-Path $novelaiDir '__init__.py') `
        "${HostAddress}:~/.hermes/plugins/image_gen/novelai/"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host 'Uploading NovelAI prompting skill...'
    & scp.exe @sshCommon `
        $skillFile `
        "${HostAddress}:~/.hermes/skills/creative/novelai-prompting/"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if (-not $NoRestart) {
        Write-Host 'Restarting hermes-gateway.service...'
        & ssh.exe @sshCommon $HostAddress 'systemctl --user restart hermes-gateway.service && systemctl --user is-active hermes-gateway.service'
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    Write-Host 'Deploy complete.'
}
finally {
    $env:Path = $previousPath
}
