param(
    [switch]$SkipSmokeChecks,
    [switch]$SkipInstaller
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $root "build_release.ps1") -SkipSmokeChecks:$SkipSmokeChecks -SkipInstaller:$SkipInstaller
