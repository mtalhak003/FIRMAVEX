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
    # Hide Python/developer tools from PATH for the installed GUI launch.
    # This is isolated CI evidence, not a physical clean-consumer-machine test.
    $savedPath = $env:PATH
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$destination"
        $smoke = Start-Process $app -ArgumentList '--smoke-test' -Wait -PassThru
    } finally { $env:PATH = $savedPath }
    if ($smoke.ExitCode -ne 0) { throw 'Installed startup failed' }
    if ($FirmwareQualification -and $iteration -eq 1) {
        $engine = Join-Path $destination 'FIRMAVEX.exe'
        $demo = Join-Path $env:RUNNER_TEMP 'windows-installed-builtin'
        & $engine --firmavex-cli demo-builtin --output-dir $demo
        if ($LASTEXITCODE -ne 0) { throw 'Installed real firmware execution failed' }
        python -m tools.desktop_native_evidence $demo
        if ($LASTEXITCODE -ne 0) { throw 'Installed real execution evidence failed' }
    }
    if ($FirmwareQualification) {
        $receipt = Join-Path $env:RUNNER_TEMP 'windows-installed-builtin\search\result.json'
        $savedFiles = @($receipt, (Join-Path (Split-Path $receipt) 'run.sqlite3'))
        if ($iteration -eq 1) { $receiptDigests = @($savedFiles | Get-FileHash -Algorithm SHA256) }
        & (Join-Path $destination 'FIRMAVEX.exe') --firmavex-cli inspect (Split-Path $receipt)
        if ($LASTEXITCODE -ne 0) { throw 'Installed restart/reopen failed' }
        if (Compare-Object -ReferenceObject $receiptDigests -DifferenceObject @($savedFiles | Get-FileHash -Algorithm SHA256) -Property Path,Hash) { throw 'Reinstall changed saved outcome or database' }
    }
    if (!(Test-Path $sentinel)) { throw 'Upgrade removed user data' }
}
$p = Start-Process (Join-Path $destination 'unins000.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Uninstall failed' }
if (!(Test-Path $sentinel)) { throw 'Uninstall removed user data' }
Remove-Item $sentinelRoot -Recurse

if ($FirmwareQualification) {
    if (Compare-Object -ReferenceObject $receiptDigests -DifferenceObject @($savedFiles | Get-FileHash -Algorithm SHA256) -Property Path,Hash) { throw 'Uninstall changed saved outcome or database' }
}
@{
    schema_version = 1; kind = 'firmavex_installer_lifecycle'; platform = 'windows'
    measurement = 'fresh_github_runner_not_physical_consumer_machine'
    installed_gui_without_developer_path = $true; reinstall_preserved_user_data = $true
    uninstall_preserved_user_data = $true; distinct_version_rollback = 'not_qualified'
    firmware_qualified = [bool]$FirmwareQualification
} | ConvertTo-Json | Set-Content (Join-Path $env:RUNNER_TEMP 'installer-lifecycle.json')
