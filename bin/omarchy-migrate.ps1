#Requires -Version 5.1
<#
.SYNOPSIS
    omarchy-migrate — migrate files from your old Windows to Omarchy.

.DESCRIPTION
    PowerShell router for Windows source side. Delegates to the Python engine.
    Follows Omarchy conventions where applicable.

    State:  $env:LOCALAPPDATA\omarchy\migrate\
    Config: $env:APPDATA\omarchy\migrate\
    Data:   $env:LOCALAPPDATA\omarchy\migrate\

.EXAMPLE
    .\omarchy-migrate.ps1 detect
    .\omarchy-migrate.ps1 export --out D:\migration.zip
    .\omarchy-migrate.ps1 import D:\migration.zip -Yes
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'
$OmarchyMigrateVersion = '0.2.0'

# Resolve the repo root (where this script lives)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $ScriptDir

# XDG-style paths on Windows
$StateDir = Join-Path $env:LOCALAPPDATA 'omarchy\migrate'
$ConfigDir = Join-Path $env:APPDATA 'omarchy\migrate'
$DataDir = Join-Path $env:LOCALAPPDATA 'omarchy\migrate'

foreach $d in @($StateDir, $ConfigDir, $DataDir) {
    if (!(Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

function Run-Python {
    param([string[]]$PyArgs)
    Set-Location $Repo
    & python3 @($PyArgs)
    if ($LASTEXITCODE -ne 0) { throw "python3 exited $LASTEXITCODE" }
}

function Get-OSName { 'windows' }

function Cmd-Detect {
    Write-Host "Detecting apps on Windows..."
    $osName = Get-OSName
    Run-Python -PyArgs @('-c', @"
import sys; sys.path.insert(0, '$Repo')
from lib.core import detect
r = detect('$osName')
print(f'OS: {r.os_name}')
print(f'Apps found: {len(r.apps)}')
print(f'Storage devices: {len(r.storage)}')
for app in sorted(r.apps)[:20]:
    print(f'  {app}')
"@)
}

function Cmd-Export {
    param($Out)
    if (!$Out) { $Out = Join-Path $env:USERPROFILE 'omarchy-migrate-package.zip' }
    Write-Host "Exporting to $Out..."
    $osName = Get-OSName
    Run-Python -PyArgs @('lib/core.py', 'export', '--os', $osName, '--out', $Out)
}

function Cmd-Import {
    param($Pkg, [switch]$DryRun, [switch]$Yes)
    if (!$Pkg) { Write-Error "Usage: omarchy-migrate import <package.zip>"; return 1 }
    $importArgs = @('lib/core.py', 'import', '--pkg', $Pkg)
    if ($DryRun) { $importArgs += '--dry-run' }
    if ($Yes) { $importArgs += '--yes' }
    Run-Python -PyArgs $importArgs
}

function Cmd-Share {
    param($Port = 5317)
    Run-Python -PyArgs @('lib/core.py', 'share', '--port', $Port)
}

function Cmd-Receive {
    param($Url)
    if (!$Url) { Write-Error "Usage: omarchy-migrate receive <manifest-url>"; return 1 }
    Run-Python -PyArgs @('lib/core.py', 'receive', '--url', $Url)
}

function Cmd-Doctor {
    $pyCmd = Get-Command python3 -ErrorAction SilentlyContinue
    Write-Host "omarchy-migrate v$OmarchyMigrateVersion"
    Write-Host ''
    Write-Host 'Environment:'
    if ($pyCmd) { Write-Host "  python3: $($pyCmd.Source)" } else { Write-Host '  python3: NOT FOUND' }
    Write-Host '  os:      windows'
    Write-Host '  scripts: powershell'
    Write-Host ''
    Write-Host 'Directories:'
    Write-Host "  state:   $StateDir"
    Write-Host "  config:  $ConfigDir"
    Write-Host "  data:    $DataDir"
    if (!$pyCmd) {
        Write-Host ''
        Write-Host 'Install python3 from https://www.python.org/downloads/windows/'
        return 1
    }
    Write-Host ''
    Write-Host 'Environment OK.'
}

# Router
switch ($Command) {
    'detect'    { Cmd-Detect @Args }
    'export'    { Cmd-Export @Args }
    'import'    { Cmd-Import @Args }
    'share'     { Cmd-Share @Args }
    'receive'   { Cmd-Receive @Args }
    'doctor'    { Cmd-Doctor @Args }
    { $_ -in @('--help', '-h', $null) } {
        Write-Host "omarchy-migrate v$OmarchyMigrateVersion"
        Write-Host ''
        Write-Host 'Usage: .\omarchy-migrate.ps1 <command> [args]'
        Write-Host ''
        Write-Host 'Commands:'
        Write-Host '  detect              Scan for installed apps and storage'
        Write-Host '  export [OUT]        Build migration package'
        Write-Host '  import PKG [-Yes] [-DryRun]  Import a migration package'
        Write-Host '  share [PORT]        Share your setup via QR'
        Write-Host '  receive URL         Pull a friend''s setup'
        Write-Host '  doctor              Verify environment'
    }
    default {
        Write-Error "Unknown command: $Command`nRun '.\omarchy-migrate.ps1 --help' for usage."
        exit 1
    }
}
