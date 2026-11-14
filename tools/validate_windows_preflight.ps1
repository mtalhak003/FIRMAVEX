#requires -Version 7.0
<#
Native PowerShell entry point for the controlled Batch 35 preflight harness.
Only the existing operator-trusted Git and virtual-environment Python are run.
This wrapper neither creates output directories nor executes supplied artifacts.
The Python harness owns bounded UTF-8 evidence writes and final classifications.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExpectedHead,
    [string]$Output,
    [string]$Python,
    [string]$Manifest,
    [string]$StagingRoot,
    [switch]$ConfirmControlledInputs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Preflight classifications and harness failures must be handled by exit code,
# not PowerShell's version-dependent native-command ErrorAction behavior.
$PSNativeCommandUseErrorActionPreference = $false

function Assert-PathSpelling([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Length -gt 4096 -or
        $Value -match '[\x00-\x1f\x7f]') { throw 'B35_UNSAFE_PATH' }
    $Spelling = $Value.Replace('\', '/')
    if ($Spelling.StartsWith('//') -or $Spelling -cnotmatch '^[A-Za-z]:/' -or
        $Spelling.Substring(2).Contains(':')) { throw 'B35_UNSAFE_PATH' }
    $Parts = @($Spelling.Split('/') | Where-Object { $_.Length -gt 0 })
    foreach ($Part in $Parts) {
        if ($Part.EndsWith('.') -or $Part.EndsWith(' ') -or $Part.Contains('~')) {
            throw 'B35_UNSAFE_PATH'
        }
        $Stem = $Part.Split('.')[0].TrimEnd(' ')
        if ($Stem -match '^(con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])$') {
            throw 'B35_UNSAFE_PATH'
        }
    }
    for ($Index = 0; $Index -lt $Parts.Count - 1; $Index++) {
        if ($Parts[$Index] -ieq 'evidence' -and $Parts[$Index + 1] -ieq 'windows-sandbox') {
            throw 'B35_PROTECTED_PATH'
        }
    }
}

function Get-LocalPath([string]$Value) {
    # Validate before normalization or any provider/filesystem access.
    Assert-PathSpelling $Value
    $Full = [IO.Path]::GetFullPath($Value)
    Assert-PathSpelling $Full
    $Drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($Full))
    if ($Drive.DriveType -notin @([IO.DriveType]::Fixed, [IO.DriveType]::Removable,
                                  [IO.DriveType]::Ram, [IO.DriveType]::CDRom)) {
        throw 'B35_NONLOCAL_DRIVE'
    }
    return $Full
}

function Get-CheckedEntry([string]$Full, [switch]$Directory, [switch]$MissingFinal) {
    # Walk root to leaf so a static parent junction is refused before its child.
    # This is not protection against a hostile concurrent parent replacement.
    $Root = [IO.Path]::GetPathRoot($Full)
    $Parts = @($Full.Substring($Root.Length).Split(
        [IO.Path]::DirectorySeparatorChar, [StringSplitOptions]::RemoveEmptyEntries))
    $Current = $Root
    $Entry = $null
    for ($Index = -1; $Index -lt $Parts.Count; $Index++) {
        if ($Index -ge 0) { $Current = [IO.Path]::Combine($Current, $Parts[$Index]) }
        try {
            $Entry = Get-Item -LiteralPath $Current -Force -ErrorAction Stop
        } catch [System.Management.Automation.ItemNotFoundException] {
            if ($MissingFinal -and $Index -eq $Parts.Count - 1) { return $null }
            throw 'B35_REQUIRED_PATH_MISSING'
        } catch { throw 'B35_PATH_INSPECTION_BLOCKED' }
        if (($Entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'B35_REPARSE_PATH'
        }
        if ($Index -lt $Parts.Count - 1 -and -not $Entry.PSIsContainer) {
            throw 'B35_INVALID_PARENT'
        }
    }
    if ($MissingFinal) { return $Entry }
    if ([bool]$Entry.PSIsContainer -ne [bool]$Directory) { throw 'B35_WRONG_PATH_TYPE' }
    return $Entry
}

function Test-Within([string]$Child, [string]$Parent) {
    $Parent = $Parent.TrimEnd([IO.Path]::DirectorySeparatorChar)
    return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
        $Child.StartsWith($Parent + [IO.Path]::DirectorySeparatorChar,
                          [StringComparison]::OrdinalIgnoreCase)
}

function Invoke-ReadOnlyGit([string]$Executable, [string]$Repository, [string[]]$CommandArguments) {
    # Keep only private in-memory copies of Git overrides; never print their values.
    $Saved = @{}
    $Names = @([Environment]::GetEnvironmentVariables('Process').Keys |
        Where-Object { $_ -match '^GIT_' })
    foreach ($Name in $Names) {
        $Saved[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
    $Overrides = @{
        GIT_CONFIG_NOSYSTEM = '1'; GIT_CONFIG_GLOBAL = 'NUL'; GIT_CONFIG_SYSTEM = 'NUL'
        GIT_ATTR_NOSYSTEM = '1'; GIT_TERMINAL_PROMPT = '0'; GIT_NO_LAZY_FETCH = '1'
        GIT_NO_REPLACE_OBJECTS = '1'
    }
    $Primary = $null
    try {
        foreach ($Name in $Names) { [Environment]::SetEnvironmentVariable($Name, $null, 'Process') }
        foreach ($Name in $Overrides.Keys) {
            [Environment]::SetEnvironmentVariable($Name, $Overrides[$Name], 'Process')
        }
        $Lines = @(& $Executable --no-optional-locks --no-pager -c core.fsmonitor=false `
            -c protocol.allow=never -c core.attributesFile=NUL -c ('core.hooksPath=' + $Executable) `
            -C $Repository @CommandArguments 2>$null)
        $Code = $LASTEXITCODE
        return [pscustomobject]@{ Lines = $Lines; ExitCode = $Code }
    } catch {
        $Primary = $_.Exception
        throw
    } finally {
        $RestoreFailed = $false
        foreach ($Name in $Overrides.Keys) {
            try { [Environment]::SetEnvironmentVariable($Name, $null, 'Process') }
            catch [System.Management.Automation.PipelineStoppedException] { throw }
            catch { $RestoreFailed = $true }
        }
        foreach ($Name in $Saved.Keys) {
            try { [Environment]::SetEnvironmentVariable($Name, $Saved[$Name], 'Process') }
            catch [System.Management.Automation.PipelineStoppedException] { throw }
            catch { $RestoreFailed = $true }
        }
        if ($RestoreFailed) {
            if ($null -eq $Primary) { throw 'B35_GIT_ENV_RESTORE_FAILED' }
            [Console]::Error.WriteLine('FIRMAVEX Batch 35 wrapper blocked: B35_GIT_ENV_RESTORE_FAILED')
        }
    }
}

try {
    if (-not $IsWindows -or $PSVersionTable.PSVersion.Major -lt 7) {
        throw 'B35_NATIVE_WINDOWS_POWERSHELL_REQUIRED'
    }
    if ($ExpectedHead -cnotmatch '^[0-9a-f]{40}$') { throw 'B35_INVALID_EXPECTED_HEAD' }
    if (-not $ConfirmControlledInputs.IsPresent) { throw 'B35_CONTROLLED_INPUT_ACK_REQUIRED' }
    $Repo = Get-LocalPath ([IO.Directory]::GetParent($PSScriptRoot).FullName)
    $null = Get-CheckedEntry $Repo -Directory
    $InvocationDirectory = Get-LocalPath ([string](Get-Location).Path)

    if ([string]::IsNullOrWhiteSpace($Python)) {
        $Python = [IO.Path]::Combine($Repo, '.venv', 'Scripts', 'python.exe')
    }
    $Python = Get-LocalPath $Python
    if ([IO.Path]::GetFileName($Python) -ine 'python.exe') { throw 'B35_EXISTING_VENV_REQUIRED' }
    $Scripts = [IO.Directory]::GetParent($Python).FullName
    if ([IO.Path]::GetFileName($Scripts) -ine 'Scripts') { throw 'B35_EXISTING_VENV_REQUIRED' }
    $Venv = [IO.Directory]::GetParent($Scripts).FullName
    $Config = Get-LocalPath ([IO.Path]::Combine($Venv, 'pyvenv.cfg'))
    $null = Get-CheckedEntry $Python
    $null = Get-CheckedEntry $Config
    # A venv marker is a layout check, not authentication of Python itself.

    if ([string]::IsNullOrWhiteSpace($Output)) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'B35_OUTPUT_REQUIRED' }
        $Output = [IO.Path]::Combine($env:LOCALAPPDATA,
            'FIRMAVEX-Preflight-Batch35-' + [guid]::NewGuid().ToString('N'))
    }
    $Output = Get-LocalPath $Output
    if ($null -ne (Get-CheckedEntry $Output -MissingFinal)) { throw 'B35_OUTPUT_ALREADY_EXISTS' }
    if ((Test-Within $Output $Repo) -or (Test-Within $Repo $Output)) { throw 'B35_OUTPUT_OVERLAP' }
    if ((Test-Within $Output $Venv) -or (Test-Within $Venv $Output)) { throw 'B35_OUTPUT_VENV_OVERLAP' }

    $HasManifest = -not [string]::IsNullOrWhiteSpace($Manifest)
    $HasStaging = -not [string]::IsNullOrWhiteSpace($StagingRoot)
    if ($HasManifest -ne $HasStaging) { throw 'B35_MANIFEST_STAGING_PAIR_REQUIRED' }
    if ($HasManifest) {
        $Manifest = Get-LocalPath $Manifest
        $StagingRoot = Get-LocalPath $StagingRoot
        $null = Get-CheckedEntry $StagingRoot -Directory
        $null = Get-CheckedEntry $Manifest
        if (-not (Test-Within $Manifest $StagingRoot) -or
            (Test-Within $StagingRoot $Repo) -or (Test-Within $Repo $StagingRoot) -or
            (Test-Within $Output $StagingRoot) -or (Test-Within $StagingRoot $Output)) {
            throw 'B35_INPUT_OUTPUT_OVERLAP'
        }
    }

    $GitCommand = Get-Command git.exe -CommandType Application -ErrorAction Stop
    $Git = Get-LocalPath $GitCommand.Source
    $null = Get-CheckedEntry $Git
    if ((Test-Within $Git $InvocationDirectory) -or (Test-Within $Git $Repo) -or
        (Test-Within $Git $Output) -or ($HasStaging -and (Test-Within $Git $StagingRoot))) {
        throw 'B35_GIT_LOCATION_BLOCKED'
    }
    # Bind Git's discovered worktree before any configuration/index/status scan.
    $RootResult = Invoke-ReadOnlyGit $Git $Repo @('rev-parse', '--show-toplevel')
    if ($RootResult.ExitCode -ne 0 -or $RootResult.Lines.Count -ne 1) {
        throw 'B35_GIT_WORKTREE_REDIRECTED'
    }
    $ActualRoot = Get-LocalPath ($RootResult.Lines[0].Trim())
    if (-not $ActualRoot.Equals($Repo, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'B35_GIT_WORKTREE_REDIRECTED'
    }
    # Reject local include/filter mechanisms before status can invoke an
    # attribute-driven helper. Only names are inspected; values are not emitted.
    $ConfigResult = Invoke-ReadOnlyGit $Git $Repo @('config', '--no-includes', '--name-only', '--list')
    if ($ConfigResult.ExitCode -ne 0) { throw 'B35_GIT_CONFIG_BLOCKED' }
    foreach ($Name in $ConfigResult.Lines) {
        if ($Name -match '^(filter\.|include\.|includeif\.)') { throw 'B35_GIT_CONFIG_BLOCKED' }
    }
    # A clean status alone can hide files marked assume-unchanged/skip-worktree.
    # Scope all index inspection away from private evidence before Python loads.
    $IndexResult = Invoke-ReadOnlyGit $Git $Repo @('ls-files', '-v', '--', '.', ':(exclude)evidence/**')
    if ($IndexResult.ExitCode -ne 0) { throw 'B35_GIT_INDEX_BLOCKED' }
    foreach ($Line in $IndexResult.Lines) {
        if ($Line -cnotmatch '^H ') { throw 'B35_GIT_INDEX_BLOCKED' }
    }
    $HeadResult = Invoke-ReadOnlyGit $Git $Repo @('rev-parse', 'HEAD')
    if ($HeadResult.ExitCode -ne 0 -or $HeadResult.Lines.Count -ne 1 -or
        $HeadResult.Lines[0].Trim() -cne $ExpectedHead) { throw 'B35_REVISION_MISMATCH' }
    $StatusResult = Invoke-ReadOnlyGit $Git $Repo @('status', '--short', '--untracked-files=all',
        '--', '.', ':(exclude)evidence/**')
    if ($StatusResult.ExitCode -ne 0 -or $StatusResult.Lines.Count -ne 0) { throw 'B35_CHECKOUT_CHANGED' }

    $Arguments = @('-E', '-s', '-B', '-m', 'tools.windows_preflight_validation',
        '--expected-head', $ExpectedHead, '--git-executable', $Git,
        '--output', $Output, '--controlled-inputs',
        '--powershell-version', ('{0}.{1}.{2}' -f $PSVersionTable.PSVersion.Major,
            $PSVersionTable.PSVersion.Minor, $PSVersionTable.PSVersion.Patch))
    if ($HasManifest) { $Arguments += @('--manifest', $Manifest, '--staging-root', $StagingRoot) }
    Push-Location -LiteralPath $Repo
    try {
        & $Python @Arguments
        $HarnessExit = $LASTEXITCODE
    } finally { Pop-Location }
    exit $HarnessExit
} catch [System.Management.Automation.PipelineStoppedException] {
    throw
} catch {
    $Code = 'B35_WRAPPER_BLOCKED'
    if ($_.Exception.Message -cmatch '^B35_[A-Z0-9_]{1,64}$') { $Code = $_.Exception.Message }
    [Console]::Error.WriteLine('FIRMAVEX Batch 35 wrapper blocked: ' + $Code)
    exit 2
}
