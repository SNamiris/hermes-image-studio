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
$comfyuiDir = Join-Path $repoRoot 'plugins\image_gen\comfyui'
$novelaiSkill = Join-Path $repoRoot 'skills\novelai-prompting\SKILL.md'
$comfyuiSkill = Join-Path $repoRoot 'skills\comfyui-workflow\SKILL.md'
$workflowsDir = Join-Path $repoRoot 'workflows'

if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
    throw "SSH key not found: $KeyPath"
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
        '-o', 'ServerAliveInterval=5'
        '-o', 'ServerAliveCountMax=3'
    )

    if ($SocksProxyPort -gt 0 -and
        (Get-NetTCPConnection -LocalPort $SocksProxyPort -State Listen -ErrorAction SilentlyContinue) -and
        (Test-Path -LiteralPath (Join-Path $GitBinDir 'connect.exe') -PathType Leaf)) {
        Write-Host "Using SOCKS5 proxy 127.0.0.1:$SocksProxyPort"
        $sshCommon += @('-o', "ProxyCommand=connect.exe -5 -S 127.0.0.1:$SocksProxyPort %h %p")
    }

    Write-Host "Ensuring target directories on $HostAddress..."
    & ssh.exe @sshCommon $HostAddress 'mkdir -p ~/.hermes/plugins/image_gen/novelai ~/.hermes/plugins/image_gen/comfyui ~/.hermes/skills/creative/novelai-prompting ~/.hermes/skills/creative/comfyui-workflow ~/.hermes/comfyui/workflows'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host 'Uploading NovelAI plugin...'
    $novelaiFiles = @((Join-Path $novelaiDir 'plugin.yaml')) + (
        Get-ChildItem -LiteralPath $novelaiDir -Filter '*.py' -File | Select-Object -ExpandProperty FullName
    )
    & scp.exe @sshCommon @novelaiFiles "${HostAddress}:~/.hermes/plugins/image_gen/novelai/"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host 'Uploading ComfyUI plugin...'
    $comfyuiFiles = @((Join-Path $comfyuiDir 'plugin.yaml')) + (
        Get-ChildItem -LiteralPath $comfyuiDir -Filter '*.py' -File | Select-Object -ExpandProperty FullName
    )
    & scp.exe @sshCommon @comfyuiFiles "${HostAddress}:~/.hermes/plugins/image_gen/comfyui/"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host 'Uploading skills...'
    & scp.exe @sshCommon $novelaiSkill "${HostAddress}:~/.hermes/skills/creative/novelai-prompting/"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & scp.exe @sshCommon $comfyuiSkill "${HostAddress}:~/.hermes/skills/creative/comfyui-workflow/"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $workflowFiles = @(
        Get-ChildItem -LiteralPath $workflowsDir -Filter '*.json' -File -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName
    )
    if ($workflowFiles.Count -gt 0) {
        Write-Host "Uploading $($workflowFiles.Count) ComfyUI workflow file(s)..."
        & scp.exe @sshCommon @workflowFiles "${HostAddress}:~/.hermes/comfyui/workflows/"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

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
