<#
.SYNOPSIS
  omnigate — cross-platform migration to Omarchy (Windows wrapper).

.DESCRIPTION
  Runs the omnigate Python tool on Windows. Finds a usable Python 3
  (py -3 launcher first, then python), checks git, then runs
  `python bootstrap.py <args>` from the repo root so relative imports
  resolve no matter where this script is invoked from.

  PowerShell ships with every supported Windows version — no extra
  install required. Git for Windows (https://git-scm.com/download/win)
  and Python (https://www.python.org/downloads/windows/) must be
  installed; bootstrap.py prints clear install instructions if either
  is missing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File omnigate.ps1 --help
  powershell -ExecutionPolicy Bypass -File omnigate.ps1 export --os windows --out my-setup.zip
  powershell -ExecutionPolicy Bypass -File omnigate.ps1 doctor
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    # Prefer the Windows py launcher, then python3, then python.
    $candidates = @('py', 'python3', 'python')
    foreach ($cand in $candidates) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cand
        }
    }
    return $null
}

function Find-Git {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # Git for Windows standard locations, in case PATH is missing it.
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'Git\cmd\git.exe'),
        (Join-Path ${env:LOCALAPPDATA} 'Programs\Git\cmd\git.exe')
    )
    foreach ($cand in $candidates) {
        if (Test-Path -LiteralPath $cand) { return $cand }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host 'omnigate: no Python 3 found on this Windows machine.' -ForegroundColor Red
    Write-Host ''
    Write-Host '  Install Python from https://www.python.org/downloads/windows/' -ForegroundColor Yellow
    Write-Host "  and tick 'Add python.exe to PATH' (or use the Microsoft Store 'python3' app)."
    exit 3
}

$git = Find-Git
if (-not $git) {
    Write-Host 'omnigate: git not found — git is the migration backbone.' -ForegroundColor Red
    Write-Host ''
    Write-Host '  Install Git for Windows from https://git-scm.com/download/win' -ForegroundColor Yellow
    Write-Host '  (default options put git on PATH).'
    exit 3
}

# Delegate to bootstrap.py, which validates the Python version and runs the
# requested command with the repo root as the working directory.
Push-Location $RepoRoot
try {
    & $py "$RepoRoot\bootstrap.py" @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
