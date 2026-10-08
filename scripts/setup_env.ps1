<#
.SYNOPSIS
    Environment setup for waste_demarcation_feasibility_study.

.DESCRIPTION
    Builds the conda env 'wdfs' (Python 3.12), installs requirements.txt into
    it, and verifies the result end to end.

    ---------------------------------------------------------------------
    BUG HISTORY - read before editing, these mistakes were expensive
    ---------------------------------------------------------------------
    1) ARGUMENTS WERE SILENTLY DROPPED.
       The previous version used `param([string[]]$Args)` in a helper.
       `$Args` is a PowerShell AUTOMATIC VARIABLE. Declaring it as a
       parameter does not bind - the body sees the (empty) automatic value.
       So `& $Exe @Args` ran bare `conda`, which printed its help text and
       exited 0. Every step reported [OK] while doing nothing.
       => NEVER name a parameter $Args. This script uses $ArgList.
       => Every external command is echoed FULLY EXPANDED before it runs.
       => After each conda call we check the output for conda's usage banner
          and abort immediately if we see it.

    2) EXIT CODES FROM conda ARE NOT TRUSTWORTHY.
       conda is often a .bat shim (here: Library\bin\conda.bat) and its exit
       code did not reflect failure. So we never trust exit codes alone:
       after create we assert <env>\python.exe exists AND runs; after install
       we assert the key packages actually import. First failed assertion
       aborts loudly.

    3) THE ENV LOCATION WAS ASSUMED.
       Now resolved via `conda info --base` and `conda env list --json`.
       We also prefer Scripts\conda.exe over the Library\bin\conda.bat shim.

    4) conda 26.x TERMS-OF-SERVICE PLUGIN can block installs from channels
       whose ToS has not been accepted, and cannot prompt non-interactively.
       environment.yml therefore uses conda-forge only. If a ToS error does
       surface, we detect it and print the exact fix.

.PARAMETER Diagnose
    Print full diagnostics and exit WITHOUT changing anything.

.PARAMETER Force
    Tear down any existing or half-made 'wdfs' env and rebuild from scratch.

.PARAMETER Venv
    Skip conda entirely; use a plain venv at .venv.

.PARAMETER SkipVerify
    Create and install only; skip verification.

.PARAMETER UpdateEnv
    Re-apply environment.yml to an existing env. Not needed normally: when a
    valid 'wdfs' env already exists the script skips conda entirely and
    resumes at the pip install step, which is safe to re-run.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1 -Force

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1 -Diagnose
#>

[CmdletBinding()]
param(
    [switch]$Diagnose,
    [switch]$Force,
    [switch]$Venv,
    [switch]$SkipVerify,
    [switch]$UpdateEnv
)

$ErrorActionPreference = 'Stop'

$ENV_NAME     = 'wdfs'
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$ENV_YML      = Join-Path $PROJECT_ROOT 'environment.yml'
$REQS         = Join-Path $PROJECT_ROOT 'requirements.txt'
$VERIFY       = Join-Path $PSScriptRoot 'verify_env.py'
$VENV_DIR     = Join-Path $PROJECT_ROOT '.venv'

$script:StepNo    = 0
$script:CondaExe  = $null
$script:CondaBase = $null

# ===========================================================================
#  output helpers
# ===========================================================================

function Write-Step {
    param([string]$Message)
    $script:StepNo++
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor Cyan
    Write-Host ("  STEP {0}: {1}" -f $script:StepNo, $Message) -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor Cyan
}

function Write-Info  { param([string]$m) Write-Host "    $m"      -ForegroundColor Gray }
function Write-Good  { param([string]$m) Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn2 { param([string]$m) Write-Host "    [!!] $m" -ForegroundColor Yellow }
function Write-Bad   { param([string]$m) Write-Host "    [XX] $m" -ForegroundColor Red }

function Fail {
    param(
        [string]$Message,
        [string]$Category = 'GENERAL',
        [string[]]$Hints = @()
    )
    Write-Host ''
    Write-Host ('!' * 72) -ForegroundColor Red
    Write-Host "  SETUP FAILED  [$Category]" -ForegroundColor Red
    Write-Host ('!' * 72) -ForegroundColor Red
    Write-Host "  $Message" -ForegroundColor Red
    if ($Hints -and $Hints.Count -gt 0) {
        Write-Host ''
        Write-Host '  What to do next:' -ForegroundColor Yellow
        foreach ($h in $Hints) { Write-Host "    - $h" -ForegroundColor Yellow }
    }
    Write-Host ''
    Write-Host '  To collect diagnostics, run:' -ForegroundColor Yellow
    Write-Host "      powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Diagnose" -ForegroundColor Yellow
    Write-Host ''
    exit 1
}

# ===========================================================================
#  external command invocation
# ===========================================================================
# NOTE: the parameter is $ArgList. It must NEVER be called $Args (automatic
# variable - that was bug #1). Nothing here builds a command as a single
# string and splats it blindly; the expanded line is always printed first.

function Format-CommandLine {
    param([string]$Exe, [string[]]$ArgList = @())
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($a in $ArgList) {
        $s = [string]$a
        if ($s -match '[\s"]') { $parts.Add('"' + ($s -replace '"', '\"') + '"') }
        else                   { $parts.Add($s) }
    }
    if ($parts.Count -eq 0) { return $Exe }
    return ($Exe + ' ' + ($parts -join ' '))
}

function ConvertTo-OutputText {
    <#  Native commands write progress and notices to stderr. With `2>&1`
        PowerShell wraps each stderr line in an ErrorRecord whose exception
        type is RemoteException - naively stringifying that yields the
        useless text "System.Management.Automation.RemoteException" instead
        of the actual line. (That is bug #5; conda writes its solver progress
        to stderr, so most of the interesting output came through this path.)
        Unwrap properly so stderr is treated as plain TEXT, never as an
        error condition.                                                   #>
    param($Item)
    if ($null -eq $Item) { return '' }
    if ($Item -is [System.Management.Automation.ErrorRecord]) {
        if ($Item.TargetObject -is [string] -and $Item.TargetObject) {
            return [string]$Item.TargetObject
        }
        if ($Item.Exception -and $Item.Exception.Message) {
            return [string]$Item.Exception.Message
        }
        return $Item.ToString()
    }
    return [string]$Item
}

function Invoke-Tool {
    <#  Runs an external command, streaming its output live while also
        capturing it. Returns @{ Code=<int>; Output=<string[]>; Line=<string> }

        .bat/.cmd shims are routed through cmd.exe /c with an explicitly
        quoted command string, because array splatting against a batch shim
        is exactly where arguments get mangled.                            #>
    param(
        [Parameter(Mandatory)][string]$Exe,
        [string[]]$ArgList = @(),
        [switch]$Quiet
    )

    if ($null -eq $ArgList) { $ArgList = @() }
    $line = Format-CommandLine -Exe $Exe -ArgList $ArgList

    # Always show the fully expanded command line. This is the guard that
    # makes bug #1 impossible to hide again.
    Write-Host "    > $line" -ForegroundColor DarkCyan
    if ($ArgList.Count -eq 0) {
        Write-Warn2 'NOTE: this command is being run with NO arguments (intentional only for --version/--help style probes)'
    }

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = 0
    $captured = New-Object System.Collections.Generic.List[string]

    try {
        if ($Exe -match '\.(bat|cmd)$') {
            # Quote the whole thing for cmd: cmd /c ""path\x.bat" arg arg"
            $inner = Format-CommandLine -Exe ('"' + $Exe + '"') -ArgList $ArgList
            & cmd.exe /c $inner 2>&1 | ForEach-Object {
                $t = ConvertTo-OutputText $_
                $captured.Add($t)
                if (-not $Quiet) { Write-Host "      $t" -ForegroundColor DarkGray }
            }
        }
        else {
            & $Exe @ArgList 2>&1 | ForEach-Object {
                $t = ConvertTo-OutputText $_
                $captured.Add($t)
                if (-not $Quiet) { Write-Host "      $t" -ForegroundColor DarkGray }
            }
        }
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    }
    catch {
        $captured.Add("EXCEPTION: $($_.Exception.Message)")
        $code = 9009
    }
    finally {
        $ErrorActionPreference = $prevEap
    }

    return @{ Code = $code; Output = @($captured.ToArray()); Line = $line }
}

function Test-CondaUsageBanner {
    <#  Detects conda printing its top-level help, which is what happens when
        the argument list never arrives. conda exits 0 in that case, so this
        text check is the only signal - it therefore has to run even on
        success, which makes precision critical.

        Guarded three ways so it cannot fire on a real run:
          * the usage line must appear at the START of the output,
          * a second help-only marker must also be present,
          * and NO evidence of actual work may be present.                #>
    param([string[]]$Output)
    if (-not $Output) { return $false }
    $joined = ($Output -join "`n")

    # If conda actually did something, this is definitively not a help dump.
    if ($joined -match '(?i)(Collecting package metadata|Solving environment|Preparing transaction|Verifying transaction|Executing transaction|To activate this environment|channel Terms of Service accepted|# packages in environment)') {
        return $false
    }

    $head = ($Output | Select-Object -First 6) -join "`n"
    $hasUsage = $head -match '(?im)^\s*usage:\s*conda'
    if (-not $hasUsage) { return $false }

    # A second marker that only appears in the top-level help listing.
    $hasHelpMarker = $joined -match '(?im)(^\s*positional arguments:|^\s*conda is a tool for managing|^\s*options:\s*$|^\s*optional arguments:\s*$)'
    return [bool]$hasHelpMarker
}

function Test-CondaToSBlock {
    <#  Detects conda 26.x REFUSING to proceed over channel Terms of Service.

        BUG #4 (false positive) was matching the bare substring
        "Terms of Service", which also appears in the SUCCESS message
        "3 channel Terms of Service accepted" and in benign channel notices.
        That aborted a run that had completed fine.

        Now: match only explicit refusal phrasing, and bail out immediately
        if the text says "accepted". The caller additionally only invokes
        this on a NON-ZERO exit code, so a succeeding step can never be
        failed by this guard.                                             #>
    param([string[]]$Output)
    if (-not $Output) { return $false }
    $joined = ($Output -join "`n")

    # Success / benign wording - never a block.
    if ($joined -match '(?i)Terms of Service accepted') { return $false }

    # Explicit refusal signatures only.
    if ($joined -match '(?i)CondaToSNonInteractiveError')                      { return $true }
    if ($joined -match '(?i)CondaToSMissingError')                             { return $true }
    if ($joined -match '(?i)Terms of Service (?:have|has) not been accepted')  { return $true }
    if ($joined -match '(?i)has not been accepted.{0,80}Terms of Service')     { return $true }
    if ($joined -match '(?i)Terms of Service.{0,80}(?:were|was) rejected')     { return $true }
    if ($joined -match '(?i)must accept the Terms of Service')                 { return $true }
    if ($joined -match '(?i)rejected the Terms of Service')                    { return $true }
    return $false
}

function Invoke-Conda {
    <#  Every conda call goes through here so the usage-banner and ToS
        checks are applied uniformly.                                    #>
    param([string[]]$ArgList, [switch]$Quiet, [switch]$AllowFail)

    if (-not $script:CondaExe) { Fail 'conda was never resolved' 'CONDA_MISSING' }
    if ($null -eq $ArgList -or $ArgList.Count -eq 0) {
        Fail 'Internal error: Invoke-Conda called with no arguments. This is the argument-passing bug - do not ship it.' 'INTERNAL_ARG_BUG'
    }

    $r = Invoke-Tool -Exe $script:CondaExe -ArgList $ArgList -Quiet:$Quiet

    # ---------------------------------------------------------------------
    #  ORDER MATTERS (bug #4). A diagnostic classifier must never be able to
    #  fail a step that succeeded. So:
    #    * the usage-banner check runs always, because the bug it catches
    #      produces exit code 0 - but it is heavily guarded against firing
    #      on real output (see Test-CondaUsageBanner).
    #    * the ToS classifier runs ONLY when the command actually FAILED.
    #  Postconditions (asserted by the caller) are the real source of truth.
    # ---------------------------------------------------------------------

    if (Test-CondaUsageBanner -Output $r.Output) {
        Fail @"
conda printed its top-level USAGE/HELP text instead of running the command.
That means the arguments did not reach conda, so NOTHING was done - even
though conda exited $($r.Code).

Command line we attempted:
    $($r.Line)
"@ 'ARG_PASSING_BROKEN' @(
            'This is the exact bug that made the previous run silently do nothing.',
            "conda executable in use: $script:CondaExe",
            'If this path ends in .bat, try pointing the script at Scripts\conda.exe instead.',
            'Send the -Diagnose output.'
        )
    }

    if ($r.Code -ne 0 -and (Test-CondaToSBlock -Output $r.Output)) {
        Fail @"
conda refused to proceed because a channel's Terms of Service has not been
accepted. conda 26.x enforces this and cannot prompt from a script.

Command line: $($r.Line)
Exit code   : $($r.Code)
"@ 'CONDA_TOS_BLOCKED' @(
            'Accept the ToS once, interactively, in an Anaconda Prompt:',
            '    conda tos list',
            '    conda tos accept --channel https://repo.anaconda.com/pkgs/main',
            'Then re-run this script.',
            'environment.yml already uses conda-forge only to avoid this; if you',
            '  added the `defaults` channel back, remove it.'
        )
    }

    if ($r.Code -ne 0 -and -not $AllowFail) {
        # Caller decides how to classify; just hand back the result.
        return $r
    }
    return $r
}

# ===========================================================================
#  conda / env resolution
# ===========================================================================

function Resolve-CondaExe {
    <#  Returns a path to a conda we can call. Prefers Scripts\conda.exe over
        the Library\bin\conda.bat shim, because the shim is where argument
        passing and exit codes both get unreliable.                      #>

    $candidates = New-Object System.Collections.Generic.List[string]

    if ($env:CONDA_EXE) { $candidates.Add($env:CONDA_EXE) }

    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.CommandType -eq 'Application' -and $cmd.Source) {
        $candidates.Add($cmd.Source)
    }

    # If conda is a function/alias (post `conda init`), ask it for its base.
    if ($cmd -and $cmd.CommandType -ne 'Application') {
        $probe = Invoke-Tool -Exe 'conda' -ArgList @('info','--base') -Quiet
        if ($probe.Code -eq 0) {
            $b = ($probe.Output | Where-Object { $_ -and $_.Trim() -and $_ -notmatch '^\s*#' } | Select-Object -First 1)
            if ($b) { $candidates.Add((Join-Path $b.Trim() 'Scripts\conda.exe')) }
        }
    }

    # Derive the preferred Scripts\conda.exe from any candidate we have.
    $extra = New-Object System.Collections.Generic.List[string]
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        # ...\Library\bin\conda.bat  or  ...\condabin\conda.bat  ->  ...\Scripts\conda.exe
        $root = $null
        if     ($c -imatch '^(?<r>.+?)\\Library\\bin\\conda\.(bat|exe)$') { $root = $Matches['r'] }
        elseif ($c -imatch '^(?<r>.+?)\\condabin\\conda\.(bat|exe)$')     { $root = $Matches['r'] }
        elseif ($c -imatch '^(?<r>.+?)\\Scripts\\conda\.exe$')            { $root = $Matches['r'] }
        if ($root) { $extra.Add((Join-Path $root 'Scripts\conda.exe')) }
    }
    foreach ($e in $extra) { $candidates.Insert(0, $e) }

    # Known install roots, miniconda3 first (that is what this machine has).
    $roots = @(
        (Join-Path $env:USERPROFILE 'miniconda3'),
        (Join-Path $env:USERPROFILE 'anaconda3'),
        (Join-Path $env:USERPROFILE 'Miniconda3'),
        (Join-Path $env:USERPROFILE 'Anaconda3'),
        (Join-Path $env:LOCALAPPDATA 'miniconda3'),
        'C:\ProgramData\miniconda3',
        'C:\ProgramData\Miniconda3',
        'C:\ProgramData\Anaconda3',
        'C:\miniconda3',
        'C:\anaconda3'
    )
    foreach ($r in $roots) {
        if ($r) {
            $candidates.Add((Join-Path $r 'Scripts\conda.exe'))
            $candidates.Add((Join-Path $r 'condabin\conda.bat'))
        }
    }

    # First existing candidate wins; .exe entries were pushed to the front.
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            return (Resolve-Path -LiteralPath $c).Path
        }
    }
    return $null
}

function Get-CondaBase {
    $r = Invoke-Conda -ArgList @('info','--base') -Quiet -AllowFail
    if ($r.Code -ne 0) { return $null }
    $line = $r.Output | Where-Object { $_ -and $_.Trim() -and $_ -notmatch '^\s*#' } | Select-Object -First 1
    if ($line) { return $line.Trim() }
    return $null
}

function Get-EnvPython {
    param([string]$EnvPath)
    if (-not $EnvPath) { return '' }
    $win = Join-Path $EnvPath 'python.exe'
    if (Test-Path -LiteralPath $win) { return $win }
    $nix = Join-Path $EnvPath 'bin\python'
    if (Test-Path -LiteralPath $nix) { return $nix }
    return $win    # expected path, so messages stay useful
}

function Get-CondaEnvPath {
    param([Parameter(Mandatory)][string]$Name)

    $r = Invoke-Conda -ArgList @('env','list','--json') -Quiet -AllowFail
    if ($r.Code -eq 0) {
        $joined = ($r.Output -join "`n").Trim()
        if ($joined -and $joined.StartsWith('{')) {
            try {
                $data = $joined | ConvertFrom-Json
                foreach ($p in @($data.envs)) {
                    if ($p -and (Split-Path -Leaf $p) -eq $Name) { return $p }
                }
            } catch {
                Write-Warn2 "could not parse 'conda env list --json': $($_.Exception.Message)"
            }
        }
    }

    $r2 = Invoke-Conda -ArgList @('env','list') -Quiet -AllowFail
    if ($r2.Code -eq 0) {
        foreach ($line in $r2.Output) {
            if ($line -match '^\s*#') { continue }
            if ($line -match ('^\s*' + [regex]::Escape($Name) + '\s+\*?\s*(?<path>[A-Za-z]:\\\S.*|/\S.*)$')) {
                return $Matches['path'].Trim()
            }
        }
    }
    return $null
}

function Get-ExpectedEnvPath {
    param([string]$Name)
    if ($script:CondaBase) { return (Join-Path $script:CondaBase "envs\$Name") }
    return $null
}

function Test-CondaEnvValid {
    param([string]$EnvPath)
    if (-not $EnvPath) { return $false }
    if (-not (Test-Path -LiteralPath $EnvPath)) { return $false }
    if (-not (Test-Path -LiteralPath (Join-Path $EnvPath 'conda-meta'))) { return $false }
    return (Test-Path -LiteralPath (Get-EnvPython $EnvPath))
}

function Resolve-EnvPathAnywhere {
    <#  conda env list, then the expected <base>\envs\<name>. Returns the
        path if ANYTHING is there (valid or not) so callers can distinguish
        "absent" from "half-made".                                        #>
    param([string]$Name)
    $p = Get-CondaEnvPath -Name $Name
    if ($p) { return $p }
    $g = Get-ExpectedEnvPath -Name $Name
    if ($g -and (Test-Path -LiteralPath $g)) { return $g }
    return $null
}

function Assert-EnvUsable {
    <#  POSTCONDITION ASSERTION. Exit codes are not trusted; this is.
        Returns the interpreter's version string.                        #>
    param([string]$EnvPath, [string]$Stage, [string]$Category)

    if (-not $EnvPath) {
        Fail "After $Stage there is still no environment named '$ENV_NAME' anywhere conda can see, and nothing at the expected path." $Category @(
            'The environment was never created, despite any [OK] above.',
            'Re-run with -Force to tear down and rebuild.',
            'Run -Diagnose and send the output.'
        )
    }
    if (-not (Test-Path -LiteralPath $EnvPath)) {
        Fail "After $Stage the env path does not exist: $EnvPath" $Category @(
            'conda registered this path but nothing is there - an aborted create.',
            'Re-run with -Force.'
        )
    }
    if (-not (Test-Path -LiteralPath (Join-Path $EnvPath 'conda-meta'))) {
        Fail "After $Stage, '$EnvPath' exists but has no conda-meta, so conda does not regard it as an environment. This is the 'Not a conda environment' error." $Category @(
            'Half-created env. Tear it down and rebuild:',
            "    powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Force",
            'Check the solver output from the create step for the real cause.'
        )
    }
    $py = Get-EnvPython $EnvPath
    if (-not (Test-Path -LiteralPath $py)) {
        Fail "After $Stage, python.exe is missing from the env: $py" $Category @(
            'The env exists but has no interpreter. Rebuild with -Force.'
        )
    }
    $probe = Invoke-Tool -Exe $py -ArgList @('-c','import sys;print(sys.version.split()[0])') -Quiet
    if ($probe.Code -ne 0) {
        Fail "After $Stage the env's python.exe exists but will not run (exit $($probe.Code)): $py" $Category @(
            "Output: $($probe.Output -join ' | ')",
            'Likely a corrupt env. Rebuild with -Force.'
        )
    }
    $ver = ($probe.Output | Where-Object { $_ -match '^\d+\.\d+' } | Select-Object -First 1)
    Write-Good "asserted: $py runs, version $ver"
    return $ver
}

function Remove-WdfsEnv {
    <#  Tear down an existing OR half-made env. Handles the case where conda
        will not remove it because it never considered it an env.        #>
    param([string]$EnvPath)

    Write-Info 'attempting conda env remove...'
    $rm = Invoke-Conda -ArgList @('env','remove','-n',$ENV_NAME,'-y') -AllowFail
    if ($rm.Code -ne 0) {
        Write-Warn2 "conda env remove exited $($rm.Code) - falling back to deleting the directory"
    }

    foreach ($p in @($EnvPath, (Get-ExpectedEnvPath -Name $ENV_NAME))) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            Write-Info "deleting directory: $p"
            try {
                Remove-Item -LiteralPath $p -Recurse -Force
                Write-Good "removed $p"
            } catch {
                Fail "Could not delete the env directory: $p" 'ENV_REMOVE_FAILED' @(
                    "Error: $($_.Exception.Message)",
                    'Close any shell, editor or Jupyter kernel using that env, then retry.',
                    "Or delete it manually:  Remove-Item -LiteralPath '$p' -Recurse -Force"
                )
            }
        }
    }
}

# ===========================================================================
#  -Diagnose
# ===========================================================================

function Invoke-Diagnose {
    Write-Host ''
    Write-Host '############################################################' -ForegroundColor Magenta
    Write-Host '#  DIAGNOSTICS - read only, nothing will be changed        #' -ForegroundColor Magenta
    Write-Host '############################################################' -ForegroundColor Magenta

    Write-Step 'Host / PowerShell'
    Write-Info "PSVersion        : $($PSVersionTable.PSVersion)"
    Write-Info "PSEdition        : $($PSVersionTable.PSEdition)"
    Write-Info "OS               : $([System.Environment]::OSVersion.VersionString)"
    Write-Info "64-bit process   : $([System.Environment]::Is64BitProcess)"
    Write-Info "ExecutionPolicy  : $(Get-ExecutionPolicy)"
    Write-Info "ScriptPath       : $PSCommandPath"

    Write-Step 'Argument-passing self-test (guards against bug #1)'
    $t = Invoke-Tool -Exe 'cmd.exe' -ArgList @('/c','echo','ARG1','ARG2','ARG3') -Quiet
    Write-Info "cmd echo output  : $($t.Output -join ' ')"
    if (($t.Output -join ' ') -match 'ARG1\s+ARG2\s+ARG3') {
        Write-Good 'arguments ARE reaching external commands correctly'
    } else {
        Write-Bad 'ARGUMENT PASSING IS BROKEN - external commands are not receiving their arguments'
    }

    Write-Step 'Project files'
    foreach ($f in @($ENV_YML, $REQS, $VERIFY)) {
        if (Test-Path -LiteralPath $f) { Write-Good "present: $f" } else { Write-Bad "MISSING: $f" }
    }
    $imgDir = Join-Path $PROJECT_ROOT 'data\processed\1024'
    if (Test-Path -LiteralPath $imgDir) {
        $n = @(Get-ChildItem -LiteralPath $imgDir -Filter *.jpg -ErrorAction SilentlyContinue).Count
        Write-Good "image dir has $n jpg file(s): $imgDir"
    } else {
        Write-Warn2 "image dir missing: $imgDir"
    }

    Write-Step 'conda discovery'
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Good 'conda found via Get-Command'
        Write-Info "CommandType      : $($cmd.CommandType)"
        Write-Info "Source           : '$($cmd.Source)'"
        if ($cmd.CommandType -ne 'Application') {
            Write-Warn2 "conda is a $($cmd.CommandType); .Source may be empty"
        }
        if ($cmd.Source -imatch '\.bat$') {
            Write-Warn2 'conda on PATH is a .bat shim - this script prefers Scripts\conda.exe'
        }
    } else {
        Write-Warn2 'conda is NOT on PATH'
    }
    Write-Info "env:CONDA_EXE         : '$env:CONDA_EXE'"
    Write-Info "env:CONDA_PREFIX      : '$env:CONDA_PREFIX'"
    Write-Info "env:CONDA_DEFAULT_ENV : '$env:CONDA_DEFAULT_ENV'"

    $script:CondaExe = Resolve-CondaExe
    if ($script:CondaExe) {
        Write-Good "resolved conda exe: $script:CondaExe"
        $isBat = $script:CondaExe -imatch '\.bat$'
        Write-Info "is a .bat shim   : $isBat"
        $v = Invoke-Conda -ArgList @('--version') -Quiet -AllowFail
        Write-Info "conda --version  : $($v.Output -join ' ')  (exit $($v.Code))"
        $script:CondaBase = Get-CondaBase
        Write-Info "conda info --base: '$script:CondaBase'"
    } else {
        Write-Bad 'could not resolve any conda executable'
    }

    if ($script:CondaExe) {
        Write-Step 'Terms-of-Service status (conda 26.x)'
        $tos = Invoke-Conda -ArgList @('tos','list') -Quiet -AllowFail
        Write-Info "(exit $($tos.Code))"
        foreach ($l in $tos.Output) { Write-Host "      $l" -ForegroundColor DarkGray }
        if ($tos.Code -ne 0) { Write-Info 'the `conda tos` subcommand may not exist on this version - fine' }

        Write-Step 'Configured channels'
        $ch = Invoke-Conda -ArgList @('config','--show','channels') -Quiet -AllowFail
        foreach ($l in $ch.Output) { Write-Host "      $l" -ForegroundColor DarkGray }
        $ed = Invoke-Conda -ArgList @('config','--show','envs_dirs') -Quiet -AllowFail
        foreach ($l in $ed.Output) { Write-Host "      $l" -ForegroundColor DarkGray }

        Write-Step "Does env '$ENV_NAME' exist?"
        $el = Invoke-Conda -ArgList @('env','list') -Quiet -AllowFail
        foreach ($l in $el.Output) { Write-Host "      $l" -ForegroundColor DarkGray }

        $envPath = Resolve-EnvPathAnywhere -Name $ENV_NAME
        if ($envPath) {
            Write-Info "candidate env path : $envPath"
            Write-Info "exists             : $(Test-Path -LiteralPath $envPath)"
            Write-Info "conda-meta present : $(Test-Path -LiteralPath (Join-Path $envPath 'conda-meta'))"
            $py = Get-EnvPython $envPath
            Write-Info "python.exe         : $py"
            Write-Info "python.exe present : $(Test-Path -LiteralPath $py)"
            if (Test-Path -LiteralPath $py) {
                $p = Invoke-Tool -Exe $py -ArgList @('-c','import sys;print(sys.version)') -Quiet
                Write-Info "python version     : $($p.Output -join ' ')"
                $pl = Invoke-Tool -Exe $py -ArgList @('-m','pip','list') -Quiet
                $want = 'numpy|opencv|matplotlib|pandas|^torch|torchvision|pyiqa|timm|transformers|pillow'
                $hits = @($pl.Output | Where-Object { $_ -imatch $want })
                if ($hits.Count -gt 0) {
                    Write-Info 'project packages installed:'
                    foreach ($l in $hits) { Write-Host "        $l" -ForegroundColor DarkGray }
                } else {
                    Write-Warn2 'NONE of the project packages are installed in this env'
                }
            }
            if (Test-CondaEnvValid $envPath) { Write-Good "env '$ENV_NAME' is VALID" }
            else { Write-Bad "env '$ENV_NAME' is NOT valid (half-made) - use -Force to tear down and rebuild" }
        } else {
            Write-Bad "no env named '$ENV_NAME' and nothing at $(Get-ExpectedEnvPath -Name $ENV_NAME)"
        }
    }

    Write-Step 'Pythons on PATH'
    foreach ($n in @('python','python3','py')) {
        $p = Get-Command $n -ErrorAction SilentlyContinue
        if (-not $p) { Write-Info "$n : not found"; continue }
        $src = if ($p.Source) { $p.Source } else { "($($p.CommandType))" }
        Write-Info "$n -> $src"
        if ($p.CommandType -eq 'Application' -and $p.Source) {
            $pv = Invoke-Tool -Exe $p.Source -ArgList @('-c','import sys;print(sys.version.split()[0])') -Quiet
            Write-Info "    version: $($pv.Output -join ' ')"
        }
    }

    Write-Step 'Paths this script would use'
    Write-Info "ENV_NAME         : $ENV_NAME"
    Write-Info "conda exe        : $(if ($script:CondaExe) { $script:CondaExe } else { '<unresolved>' })"
    Write-Info "conda base       : $(if ($script:CondaBase) { $script:CondaBase } else { '<unknown>' })"
    $ep = if ($script:CondaExe) { Resolve-EnvPathAnywhere -Name $ENV_NAME } else { $null }
    Write-Info "env path         : $(if ($ep) { $ep } else { '<none>' })"
    Write-Info "env python       : $(if ($ep) { Get-EnvPython $ep } else { '<n/a>' })"
    Write-Info "environment.yml  : $ENV_YML"
    Write-Info "requirements.txt : $REQS"

    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor Green
    Write-Host '  DIAGNOSTICS COMPLETE - nothing was changed.' -ForegroundColor Green
    Write-Host ('=' * 72) -ForegroundColor Green
    exit 0
}

# ===========================================================================
#  main
# ===========================================================================

if ($Diagnose) { Invoke-Diagnose }

Write-Host ''
Write-Host '############################################################' -ForegroundColor Magenta
Write-Host '#  waste_demarcation_feasibility_study - environment setup #' -ForegroundColor Magenta
Write-Host '############################################################' -ForegroundColor Magenta
Write-Info "project root : $PROJECT_ROOT"
Write-Info 'every external command is echoed in full before it runs'

# --- STEP 1 -----------------------------------------------------------------
Write-Step 'Checking project files'
if (-not (Test-Path -LiteralPath $REQS))   { Fail "requirements.txt not found at $REQS" 'PROJECT_FILES' }
Write-Good 'requirements.txt found'
if (-not (Test-Path -LiteralPath $VERIFY)) { Fail "scripts\verify_env.py not found at $VERIFY" 'PROJECT_FILES' }
Write-Good 'scripts\verify_env.py found'
if (Test-Path -LiteralPath $ENV_YML) { Write-Good 'environment.yml found' }
else { Write-Warn2 'environment.yml missing - conda path unavailable' }

# --- STEP 2 -----------------------------------------------------------------
Write-Step 'Resolving the toolchain + argument-passing self-test'

# Prove arguments survive the call boundary BEFORE relying on it.
$selftest = Invoke-Tool -Exe 'cmd.exe' -ArgList @('/c','echo','ARGCHECK_OK') -Quiet
if (($selftest.Output -join ' ') -notmatch 'ARGCHECK_OK') {
    Fail 'Argument-passing self-test failed: external commands are not receiving their arguments.' 'ARG_PASSING_BROKEN' @(
        "cmd.exe echo returned: $($selftest.Output -join ' | ')",
        'Do not trust any further step. Send the -Diagnose output.'
    )
}
Write-Good 'argument-passing self-test passed (args reach external commands)'

$useConda = $false
if ($Venv) {
    Write-Info '-Venv specified: skipping conda.'
} elseif (-not (Test-Path -LiteralPath $ENV_YML)) {
    Write-Warn2 'no environment.yml - conda path unavailable'
} else {
    $script:CondaExe = Resolve-CondaExe
    if ($script:CondaExe) {
        Write-Good "conda executable: $script:CondaExe"
        if ($script:CondaExe -imatch '\.bat$') {
            Write-Warn2 'this is a .bat shim; calls will be routed through cmd.exe with explicit quoting'
        }
        $v = Invoke-Conda -ArgList @('--version') -Quiet -AllowFail
        if ($v.Code -ne 0) {
            Write-Warn2 "conda --version failed (exit $($v.Code)) - falling back to venv"
        } else {
            Write-Good "conda version: $($v.Output -join ' ')"
            $script:CondaBase = Get-CondaBase
            if ($script:CondaBase) { Write-Good "conda base: $script:CondaBase" }
            else { Write-Warn2 'could not determine conda base' }
            $useConda = $true
        }
    } else {
        Write-Warn2 'no conda executable could be resolved - falling back to venv'
    }
}

if (-not $useConda) {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd -or -not $pyCmd.Source) {
        Fail 'Neither conda nor python could be resolved.' 'NO_TOOLCHAIN' @(
            'Install Miniconda (recommended) or Python 3.12, then re-run.'
        )
    }
    $pv = Invoke-Tool -Exe $pyCmd.Source -ArgList @('-c','import sys;print("%d.%d"%sys.version_info[:2])') -Quiet
    $pyVer = ($pv.Output | Where-Object { $_ -match '^\d+\.\d+$' } | Select-Object -First 1)
    Write-Info "python on PATH: $($pyCmd.Source) (version $pyVer)"
    if ($pyVer -eq '3.13' -or $pyVer -eq '3.14') {
        Write-Warn2 "Python $pyVer is newer than this project's 3.12 target; wheels exist but you get"
        Write-Warn2 'the newest major numpy/pandas/opencv, which is less tested with pyiqa.'
    }
}

# --- STEP 3 -----------------------------------------------------------------
$EnvPython = $null
$ActivateHint = ''

if ($useConda) {
    Write-Step "Building conda env '$ENV_NAME' (Python 3.12)"

    $envPath = Resolve-EnvPathAnywhere -Name $ENV_NAME
    if ($envPath) {
        $valid = Test-CondaEnvValid $envPath
        Write-Info "found something at: $envPath  (valid env: $valid)"
    } else {
        Write-Info "no existing '$ENV_NAME' env found"
    }

    $needCreate = $true

    if ($envPath -and $Force) {
        Write-Warn2 "-Force: tearing down $envPath"
        Remove-WdfsEnv -EnvPath $envPath
        $needCreate = $true
    }
    elseif ($envPath -and (Test-CondaEnvValid $envPath)) {
        # RESUME PATH. The env already exists and is valid, so there is
        # nothing for conda to do - skip straight to the pip install step.
        #
        # We deliberately do NOT run `conda env update --prune` here:
        #   * it is pointless (environment.yml only specifies python/pip/
        #     setuptools/wheel, which are already present), and
        #   * `--prune` removes packages not named in the yml, which risks
        #     tearing out the pip-installed torch/pyiqa stack.
        # Use -UpdateEnv if you genuinely want the yml re-applied.
        Write-Good 'existing valid env detected - no conda work needed'
        Write-Info  'skipping create/update and resuming at the pip install step'
        if ($UpdateEnv) {
            Write-Info '-UpdateEnv specified: re-applying environment.yml (without --prune)'
            $up = Invoke-Conda -ArgList @('env','update','--name',$ENV_NAME,'--file',$ENV_YML) -AllowFail
            if ($up.Code -ne 0) {
                Fail "conda env update failed (exit $($up.Code))." 'ENV_UPDATE_FAILED' @(
                    'See the solver output above.',
                    'The env is still usable; re-run without -UpdateEnv to just do the pip install.'
                )
            }
        }
        $needCreate = $false
    }
    elseif ($envPath) {
        Write-Bad "'$envPath' exists but is NOT a valid env (half-made) - tearing it down"
        Remove-WdfsEnv -EnvPath $envPath
        $needCreate = $true
    }

    if ($needCreate) {
        Write-Info 'Creating the env. Several GB; allow 10-20 minutes.'
        $cr = Invoke-Conda -ArgList @('env','create','--file',$ENV_YML,'--name',$ENV_NAME,'--yes') -AllowFail
        if ($cr.Code -ne 0) {
            # Older conda rejects --yes on `env create`; retry without it.
            $joined = ($cr.Output -join "`n")
            if ($joined -imatch 'unrecognized arguments.*--yes|no such option.*--yes') {
                Write-Warn2 'this conda does not accept --yes on `env create`; retrying without it'
                $cr = Invoke-Conda -ArgList @('env','create','--file',$ENV_YML,'--name',$ENV_NAME) -AllowFail
            }
        }
        if ($cr.Code -ne 0) {
            Fail "conda env create failed (exit $($cr.Code)). The environment was NOT created." 'ENV_CREATE_FAILED' @(
                'Read the solver output above: ResolvePackageNotFound or a version',
                '  conflict in environment.yml is the usual cause.',
                'Try the venv route instead:  -Venv',
                'Or run -Diagnose and send the output.'
            )
        }
        Write-Info 'conda env create returned success - but exit codes are not trusted here,'
        Write-Info 'so the postcondition is asserted next.'
    }

    # ---- POSTCONDITION ASSERTION (bug #2 guard) ---------------------------
    Write-Info 'ASSERTING the environment really exists and its interpreter runs...'
    $envPath = Resolve-EnvPathAnywhere -Name $ENV_NAME
    Assert-EnvUsable -EnvPath $envPath -Stage 'environment creation' -Category 'ENV_NOT_CREATED' | Out-Null

    $EnvPython = Get-EnvPython $envPath
    $ActivateHint = "conda activate $ENV_NAME"
    Write-Good "env ready: $envPath"
    Write-Info  'interpreter will be called by absolute path (no conda activate, no conda run):'
    Write-Info  "  $EnvPython"
}
else {
    Write-Step 'Creating virtualenv at .venv'

    if ((Test-Path -LiteralPath $VENV_DIR) -and $Force) {
        Write-Warn2 '.venv exists - removing (-Force)'
        Remove-Item -LiteralPath $VENV_DIR -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath $VENV_DIR)) {
        $mk = Invoke-Tool -Exe 'python' -ArgList @('-m','venv',$VENV_DIR)
        if ($mk.Code -ne 0) {
            Fail "venv creation failed (exit $($mk.Code))" 'VENV_CREATE_FAILED' @(
                'Check that python on PATH is a full install, not the Microsoft Store stub.'
            )
        }
        Write-Good '.venv created'
    } else {
        Write-Good '.venv exists - reusing'
    }

    $EnvPython = Join-Path $VENV_DIR 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $EnvPython)) {
        Fail "venv python missing at $EnvPython" 'VENV_NOT_CREATED' @('Delete .venv and re-run with -Force.')
    }
    $probe = Invoke-Tool -Exe $EnvPython -ArgList @('-c','import sys;print(sys.version.split()[0])') -Quiet
    if ($probe.Code -ne 0) {
        Fail "venv python will not run: $EnvPython" 'VENV_NOT_CREATED' @("Output: $($probe.Output -join ' | ')")
    }
    Write-Good "venv python runnable: $EnvPython ($($probe.Output -join ' '))"
    $ActivateHint = '.\.venv\Scripts\Activate.ps1'
}

if (-not $EnvPython -or -not (Test-Path -LiteralPath $EnvPython)) {
    Fail 'No usable interpreter after environment creation.' 'ENV_NOT_CREATED' @('Run -Diagnose and send the output.')
}

# --- STEP 4 -----------------------------------------------------------------
Write-Step 'Upgrading pip, setuptools, wheel'
$r = Invoke-Tool -Exe $EnvPython -ArgList @('-m','pip','install','--upgrade','pip','setuptools','wheel')
if ($r.Code -ne 0) {
    Fail "pip upgrade failed (exit $($r.Code))" 'PIP_UPGRADE_FAILED' @('Check network/proxy access.')
}
$pv = Invoke-Tool -Exe $EnvPython -ArgList @('-m','pip','--version') -Quiet
Write-Good "pip in env: $($pv.Output -join ' ')"

# --- STEP 5 -----------------------------------------------------------------
Write-Step 'Installing project requirements'
Write-Info 'Large download (~3-5 GB with torch + pyiqa deps). This is the slow part.'
$r = Invoke-Tool -Exe $EnvPython -ArgList @('-m','pip','install','-r',$REQS)
if ($r.Code -ne 0) {
    Fail "pip install -r requirements.txt failed (exit $($r.Code))." 'PIP_INSTALL_FAILED' @(
        'Scroll up to the first pip ERROR line - it names the offending package.',
        'Re-run to resume; pip reuses what it already downloaded.'
    )
}
Write-Info 'pip reported success - asserting the postcondition rather than trusting it.'

# ---- POSTCONDITION ASSERTION: packages must import --------------------------
Assert-EnvUsable -EnvPath (Split-Path -Parent $EnvPython) -Stage 'package installation' -Category 'ENV_BROKEN_AFTER_INSTALL' | Out-Null

$probeCode = 'import importlib,sys' + "`n" +
             'missing=[]' + "`n" +
             'for n in ("numpy","cv2","matplotlib","pandas","torch","torchvision","pyiqa"):' + "`n" +
             '    try: importlib.import_module(n)' + "`n" +
             '    except Exception as e: missing.append("%s(%s)"%(n,type(e).__name__))' + "`n" +
             'print("MISSING:"+";".join(missing) if missing else "ALL_IMPORTS_OK")' + "`n" +
             'sys.exit(3 if missing else 0)'

$imp = Invoke-Tool -Exe $EnvPython -ArgList @('-c', $probeCode) -Quiet
if ($imp.Code -ne 0 -or (($imp.Output -join ' ') -notmatch 'ALL_IMPORTS_OK')) {
    Fail "The env exists and pip reported success, but some packages will not import: $($imp.Output -join ' ')" 'PACKAGES_MISSING' @(
        'This is a half-finished install, not a broken environment.',
        'Re-run this script to let pip finish.',
        'If it persists, rebuild clean:  -Force'
    )
}
Write-Good "asserted: all key packages import ($($imp.Output -join ' '))"

# --- STEP 6 -----------------------------------------------------------------
if ($SkipVerify) {
    Write-Step 'Verification skipped (-SkipVerify)'
} else {
    Write-Step 'Verifying the environment (imports, torch device, NIQE end to end)'
    Write-Info 'The first NIQE call downloads metric weights - allow a minute.'
    Write-Host "    > $(Format-CommandLine -Exe $EnvPython -ArgList @($VERIFY))" -ForegroundColor DarkCyan

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $EnvPython $VERIFY
    $verifyCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEap

    if ($verifyCode -ne 0) {
        Fail "verify_env.py reported problems (exit $verifyCode). The environment itself is sound - it exists, its interpreter runs, and all key packages import (all asserted above) - so this is a RUNTIME/METRIC failure, most likely the NIQE step." 'VERIFY_FAILED' @(
            'Read the SUMMARY section printed by verify_env.py above.',
            'If NIQE could not download weights, check network access and retry.',
            "If no test image was found, run:  `"$EnvPython`" scripts\preprocess.py",
            "Re-run just the check:  `"$EnvPython`" scripts\verify_env.py"
        )
    }
    Write-Good 'verification passed'
}

# --- done -------------------------------------------------------------------
Write-Host ''
Write-Host ('=' * 72) -ForegroundColor Green
Write-Host '  SETUP COMPLETE' -ForegroundColor Green
Write-Host ('=' * 72) -ForegroundColor Green
Write-Host ''
Write-Host '  Environment interpreter:' -ForegroundColor White
Write-Host "      $EnvPython" -ForegroundColor Yellow
Write-Host ''
Write-Host '  Activate it in new terminals with:' -ForegroundColor White
Write-Host "      $ActivateHint" -ForegroundColor Yellow
Write-Host ''
Write-Host '  Then, for example:' -ForegroundColor White
Write-Host '      python scripts\verify_env.py      # re-check any time' -ForegroundColor Yellow
Write-Host '      python scripts\preprocess.py      # rebuild data\processed' -ForegroundColor Yellow
Write-Host ''
exit 0
