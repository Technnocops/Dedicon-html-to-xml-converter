param(
    [switch]$SkipSmokeChecks,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$portableDir = Join-Path $root "release\portable"
$buildDir = Join-Path $root "release\build-temp"
$installerDir = Join-Path $root "release\installer"
$installerScript = Join-Path $root "installer\Technocops_DDC_Converter_HTML_to_XML_Pro.iss"
$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    "C:\Program Files\Inno Setup 5\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

New-Item -ItemType Directory -Force -Path $portableDir | Out-Null
New-Item -ItemType Directory -Force -Path $installerDir | Out-Null

& $python "tools\generate_brand_assets.py"
& $python "tools\generate_security_manifest.py"

if (-not $SkipSmokeChecks) {
    & $python "tools\run_release_checks.py" "--phase" "prebuild"
}

& $python -m PyInstaller --noconfirm --clean --distpath $portableDir --workpath $buildDir "technocops_ddc.spec"

$bundleDir = Join-Path $portableDir "Technocops_DDC_Converter_HTML_to_XML_Pro"
if (-not $SkipSmokeChecks) {
    & $python "tools\run_release_checks.py" "--phase" "postbuild" "--dist-root" $bundleDir
}

if (-not $SkipInstaller) {
    if ($iscc) {
        & $iscc $installerScript
    }
    else {
        Write-Warning "Inno Setup compiler (ISCC.exe) was not found. Installer script is ready but setup EXE was not built."
    }
}

if (Test-Path $buildDir) {
    Remove-Item -LiteralPath $buildDir -Recurse -Force
}

Write-Host ""
Write-Host "Release build completed."
Write-Host "Portable bundle: $bundleDir"
if ($iscc) {
    Write-Host "Installer output: $installerDir"
}
