param(
    [string]$Version,
    [switch]$SkipSmokeChecks,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Set-Utf8NoBomFile {
    param(
        [string]$Path,
        [string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Update-AppVersionFiles {
    param(
        [string]$RootPath,
        [string]$NewVersion
    )

    $normalizedVersion = $NewVersion.Trim()
    if ($normalizedVersion -match '^Release-(\d+(?:\.\d+){1,3})$') {
        $normalizedVersion = $Matches[1]
    }

    if ($normalizedVersion -notmatch '^\d+(?:\.\d+){1,3}$') {
        throw "Version must look like Release-1.0.0, 2.5.0, or 2.5.0.1"
    }

    $parts = $normalizedVersion.Split('.')
    $label = "Release-$normalizedVersion"
    $versionInfoParts = @($parts | ForEach-Object { [int]$_ })
    while ($versionInfoParts.Count -lt 4) {
        $versionInfoParts += 0
    }
    $versionInfo = ($versionInfoParts[0..3] -join '.')
    $versionTuple = ($versionInfoParts[0..3] -join ', ')

    $initPath = Join-Path $RootPath "src\technocops_ddc\__init__.py"
    $initText = Get-Content -LiteralPath $initPath -Raw
    $initText = [regex]::Replace($initText, 'APP_VERSION = "[^"]+"', "APP_VERSION = `"$normalizedVersion`"", 1)
    $initText = [regex]::Replace($initText, 'APP_VERSION_LABEL = "[^"]+"', "APP_VERSION_LABEL = `"$label`"", 1)
    Set-Utf8NoBomFile -Path $initPath -Content $initText

    $issPath = Join-Path $RootPath "installer\Technocops_DDC_Converter_HTML_to_XML_Pro.iss"
    $issText = Get-Content -LiteralPath $issPath -Raw
    $issText = [regex]::Replace($issText, '#define MyAppVersion "[^"]+"', "#define MyAppVersion `"$normalizedVersion`"", 1)
    $issText = [regex]::Replace($issText, 'OutputBaseFilename=Technocops_DDC_Converter_HTML_to_XML_Pro_Setup_(?:v|Release-)[0-9.]+', "OutputBaseFilename=Technocops_DDC_Converter_HTML_to_XML_Pro_Setup_Release-$normalizedVersion", 1)
    $issText = [regex]::Replace($issText, 'VersionInfoVersion=[0-9.]+', "VersionInfoVersion=$versionInfo", 1)
    Set-Utf8NoBomFile -Path $issPath -Content $issText

    $windowsInfoPath = Join-Path $RootPath "packaging\windows_version_info.txt"
    $windowsInfoText = Get-Content -LiteralPath $windowsInfoPath -Raw
    $windowsInfoText = [regex]::Replace($windowsInfoText, 'filevers=\([^)]+\)', "filevers=($versionTuple)", 1)
    $windowsInfoText = [regex]::Replace($windowsInfoText, 'prodvers=\([^)]+\)', "prodvers=($versionTuple)", 1)
    $windowsInfoText = [regex]::Replace($windowsInfoText, 'StringStruct\("FileVersion", "[^"]+"\)', "StringStruct(`"FileVersion`", `"$label`")", 1)
    $windowsInfoText = [regex]::Replace($windowsInfoText, 'StringStruct\("ProductVersion", "[^"]+"\)', "StringStruct(`"ProductVersion`", `"$label`")", 1)
    Set-Utf8NoBomFile -Path $windowsInfoPath -Content $windowsInfoText
}

if ($Version) {
    Update-AppVersionFiles -RootPath $root -NewVersion $Version
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$versionFile = Join-Path $root "src\technocops_ddc\__init__.py"
$versionMatch = Select-String -Path $versionFile -Pattern 'APP_VERSION = "([^"]+)"' | Select-Object -First 1
if (-not $versionMatch) {
    throw "Unable to detect application version from $versionFile"
}

$appVersion = $versionMatch.Matches[0].Groups[1].Value
$versionSuffix = $appVersion.Replace('.', '_')
$portableDir = Join-Path $root "release\portable_v$versionSuffix"
$buildDir = Join-Path $root "release\build-temp-v$versionSuffix"
$installerDir = Join-Path $root "release\installer"
$portableZip = Join-Path $installerDir ("Technocops_DDC_Converter_HTML_to_XML_Pro_Portable_v{0}.zip" -f $appVersion)
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
if ($LASTEXITCODE -ne 0) {
    throw "Brand asset generation failed with exit code $LASTEXITCODE"
}
& $python "tools\generate_security_manifest.py"
if ($LASTEXITCODE -ne 0) {
    throw "Security manifest generation failed with exit code $LASTEXITCODE"
}

if (-not $SkipSmokeChecks) {
    & $python "tools\run_release_checks.py" "--phase" "prebuild"
    if ($LASTEXITCODE -ne 0) {
        throw "Prebuild release checks failed with exit code $LASTEXITCODE"
    }
}

& $python -m PyInstaller --noconfirm --clean --distpath $portableDir --workpath $buildDir "technocops_ddc.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$bundleDir = Join-Path $portableDir "Technocops_DDC_Converter_HTML_to_XML_Pro"
if (-not $SkipSmokeChecks) {
    & $python "tools\run_release_checks.py" "--phase" "postbuild" "--dist-root" $bundleDir
    if ($LASTEXITCODE -ne 0) {
        throw "Postbuild release checks failed with exit code $LASTEXITCODE"
    }
}

if (Test-Path $portableZip) {
    Remove-Item -LiteralPath $portableZip -Force
}
Compress-Archive -Path (Join-Path $portableDir "Technocops_DDC_Converter_HTML_to_XML_Pro") -DestinationPath $portableZip

if (-not $SkipInstaller) {
    if ($iscc) {
        & $iscc "/DMyPortableRoot=..\release\portable_v$versionSuffix" $installerScript
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup compilation failed with exit code $LASTEXITCODE"
        }
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
Write-Host "Portable ZIP: $portableZip"
if ($iscc) {
    Write-Host "Installer output: $installerDir"
}
