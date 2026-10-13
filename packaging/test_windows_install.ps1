param([switch]$FirmwareQualification)
$ErrorActionPreference = 'Stop'
$destination = Join-Path $env:RUNNER_TEMP 'FIRMAVEX installed with spaces'
$sentinelRoot = Join-Path $env:LOCALAPPDATA 'FIRMAVEX\batch3-installer-test'
New-Item -ItemType Directory -Force $sentinelRoot | Out-Null
$sentinel = Join-Path $sentinelRoot 'preserve.txt'
Set-Content $sentinel 'installer must preserve projects'
$installer = Resolve-Path 'dist/FIRMAVEX-Windows-unsigned.exe'
foreach ($iteration in 1..2) {
    $p = Start-Process $installer -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$destination`"" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installation/upgrade failed: $($p.ExitCode)" }
    $app = Join-Path $destination 'FIRMAVEX-Desktop.exe'
    $smoke = Start-Process $app -ArgumentList '--smoke-test' -Wait -PassThru
    if ($smoke.ExitCode -ne 0) { throw 'Installed startup failed' }
    if ($FirmwareQualification -and $iteration -eq 1) {
        $engine = Join-Path $destination 'FIRMAVEX.exe'
        $demo = Join-Path $env:RUNNER_TEMP 'windows-installed-builtin'
        & $engine --firmavex-cli demo-builtin --output-dir $demo
        if ($LASTEXITCODE -ne 0) { throw 'Installed real firmware execution failed' }
        python -m tools.desktop_native_evidence $demo
        if ($LASTEXITCODE -ne 0) { throw 'Installed real execution evidence failed' }
    }
    if (!(Test-Path $sentinel)) { throw 'Upgrade removed user data' }
}
$p = Start-Process (Join-Path $destination 'unins000.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Uninstall failed' }
if (!(Test-Path $sentinel)) { throw 'Uninstall removed user data' }
Remove-Item $sentinelRoot -Recurse
