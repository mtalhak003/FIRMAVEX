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
    $app = Join-Path $destination 'FIRMAVEX.exe'
    & $app --smoke-test
    if ($LASTEXITCODE -ne 0) { throw 'Installed startup failed' }
    if (!(Test-Path $sentinel)) { throw 'Upgrade removed user data' }
}
$p = Start-Process (Join-Path $destination 'unins000.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Uninstall failed' }
if (!(Test-Path $sentinel)) { throw 'Uninstall removed user data' }
Remove-Item $sentinelRoot -Recurse
