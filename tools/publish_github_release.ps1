param(
    [string]$RemoteName = "origin",
    [string]$TargetBranch = "",
    [string]$WorkingCloneDir = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Invoke-Git {
    param(
        [string[]]$Arguments,
        [string]$WorkingDirectory = "",
        [switch]$AllowFailure
    )

    $location = if ($WorkingDirectory) { $WorkingDirectory } else { (Get-Location).Path }
    $quotedArguments = @("git", "-C")
    foreach ($argument in @($location) + $Arguments) {
        if ($argument -match '[\s"&|<>^()]') {
            $quotedArguments += '"' + $argument.Replace('"', '\"') + '"'
        }
        else {
            $quotedArguments += $argument
        }
    }

    $commandText = ($quotedArguments -join " ") + " 2>&1"
    $output = & cmd.exe /d /c $commandText
    if (-not $AllowFailure -and $LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine).Trim()
    }

    return ($output -join [Environment]::NewLine).Trim()
}

function Parse-GitHubRepository {
    param([string]$RemoteUrl)

    if ($RemoteUrl -match 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(?:\.git)?$') {
        return @{
            Owner = $matches.owner
            Repo = $matches.repo
        }
    }

    throw "Unable to parse a GitHub owner/repository from remote URL: $RemoteUrl"
}

function Get-AppVersionInfo {
    param([string]$VersionFile)

    $versionMatch = Select-String -Path $VersionFile -Pattern 'APP_VERSION = "([^"]+)"' | Select-Object -First 1
    $labelMatch = Select-String -Path $VersionFile -Pattern 'APP_VERSION_LABEL = "([^"]+)"' | Select-Object -First 1
    if (-not $versionMatch) {
        throw "Unable to detect APP_VERSION from $VersionFile"
    }

    return @{
        Version = $versionMatch.Matches[0].Groups[1].Value.Trim()
        Label = if ($labelMatch) { $labelMatch.Matches[0].Groups[1].Value.Trim() } else { "" }
    }
}

function Resolve-GitHubToken {
    if ($env:TECHNOCOPS_DDC_GITHUB_TOKEN) {
        return $env:TECHNOCOPS_DDC_GITHUB_TOKEN.Trim()
    }
    if ($env:GITHUB_TOKEN) {
        return $env:GITHUB_TOKEN.Trim()
    }

    $credentialOutput = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
    if ($LASTEXITCODE -eq 0 -and $credentialOutput) {
        $passwordLine = $credentialOutput | Where-Object { $_ -like "password=*" } | Select-Object -First 1
        if ($passwordLine) {
            return $passwordLine.Substring("password=".Length).Trim()
        }
    }

    $ghToken = & gh auth token 2>$null
    if ($LASTEXITCODE -eq 0 -and $ghToken) {
        return $ghToken.Trim()
    }

    throw "No reusable GitHub credential was found. Sign in once with Git Credential Manager or set TECHNOCOPS_DDC_GITHUB_TOKEN."
}

function Resolve-AssetPath {
    param(
        [string]$ProjectRoot,
        [string]$Version,
        [string]$VersionLabel,
        [ValidateSet("setup", "portable")][string]$Kind
    )

    $installerDir = Join-Path $ProjectRoot "release\installer"
    $candidates = switch ($Kind) {
        "setup" {
            @(
                (Join-Path $installerDir "Technocops_DDC_Converter_HTML_to_XML_Pro_Setup_$VersionLabel.exe"),
                (Join-Path $installerDir "Technocops_DDC_Converter_HTML_to_XML_Pro_Setup_v$Version.exe")
            )
        }
        "portable" {
            @(
                (Join-Path $installerDir "Technocops_DDC_Converter_HTML_to_XML_Pro_Portable_v$Version.zip"),
                (Join-Path $installerDir "Technocops_DDC_Converter_HTML_to_XML_Pro_Portable_$VersionLabel.zip")
            )
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Unable to find the $Kind asset. Checked:`n$($candidates -join [Environment]::NewLine)"
}

function Ensure-GitIdentity {
    param([string]$RepositoryPath)

    $userName = Invoke-Git -WorkingDirectory $RepositoryPath -Arguments @("config", "--get", "user.name") -AllowFailure
    $userEmail = Invoke-Git -WorkingDirectory $RepositoryPath -Arguments @("config", "--get", "user.email") -AllowFailure

    if (-not $userName) {
        Invoke-Git -WorkingDirectory $RepositoryPath -Arguments @("config", "user.name", "Technnocops Release Bot") | Out-Null
    }
    if (-not $userEmail) {
        Invoke-Git -WorkingDirectory $RepositoryPath -Arguments @("config", "user.email", "release-bot@technocops.local") | Out-Null
    }
}

function Sync-ReleaseSnapshot {
    param(
        [string]$SourceRoot,
        [string]$CloneRoot
    )

    $allowedItems = @(
        ".gitignore",
        "assets",
        "docs",
        "installer",
        "packaging",
        "src",
        "tools",
        "LICENSE",
        "README.md",
        "requirements.txt",
        "run_app.py",
        "technocops_ddc.spec",
        "build_release.ps1",
        "build_exe.bat",
        "build_exe.ps1",
        "publish_github_release.bat",
        "generate_activation_key.bat",
        "generate_activation_key.py"
    )

    Get-ChildItem -Path $CloneRoot -Force |
        Where-Object { $_.Name -ne ".git" } |
        Remove-Item -Recurse -Force

    foreach ($item in $allowedItems) {
        $sourcePath = Join-Path $SourceRoot $item
        if (-not (Test-Path $sourcePath)) {
            continue
        }

        $destinationPath = Join-Path $CloneRoot $item
        Copy-Item -Path $sourcePath -Destination $destinationPath -Recurse -Force
    }

    Get-ChildItem -Path $CloneRoot -Directory -Recurse -Force |
        Where-Object { $_.Name -eq "__pycache__" } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Get-ChildItem -Path $CloneRoot -File -Recurse -Force -Include *.pyc,*.pyo |
        Remove-Item -Force -ErrorAction SilentlyContinue

    $generatedDocsPath = Join-Path $CloneRoot "docs\presentation_pack"
    if (Test-Path $generatedDocsPath) {
        Remove-Item -Path $generatedDocsPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$versionInfo = Get-AppVersionInfo -VersionFile (Join-Path $projectRoot "src\technocops_ddc\__init__.py")
$appVersion = $versionInfo.Version
$versionLabel = $versionInfo.Label
$tagName = if ($versionLabel) { $versionLabel } else { "v$appVersion" }
$setupPath = Resolve-AssetPath -ProjectRoot $projectRoot -Version $appVersion -VersionLabel $versionLabel -Kind setup
$portablePath = Resolve-AssetPath -ProjectRoot $projectRoot -Version $appVersion -VersionLabel $versionLabel -Kind portable
$token = Resolve-GitHubToken

$remoteUrl = Invoke-Git -WorkingDirectory $projectRoot -Arguments @("remote", "get-url", $RemoteName)
$repository = Parse-GitHubRepository -RemoteUrl $remoteUrl
$repoSlug = "$($repository.Owner)/$($repository.Repo)"

$headers = @{
    Accept = "application/vnd.github+json"
    Authorization = "Bearer $token"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$repoInfo = Invoke-RestMethod -Method GET -Headers $headers -Uri "https://api.github.com/repos/$repoSlug"
if (-not $TargetBranch) {
    $TargetBranch = $repoInfo.default_branch
}

$cloneRoot = if ($WorkingCloneDir) {
    [IO.Path]::GetFullPath($WorkingCloneDir)
} else {
    Join-Path (Split-Path -Parent $projectRoot) "Software_release_publish"
}

if (Test-Path $cloneRoot) {
    Remove-Item -Path $cloneRoot -Recurse -Force
}

Write-Host "Cloning clean publish workspace..."
Invoke-Git -WorkingDirectory $projectRoot -Arguments @("clone", "--branch", $TargetBranch, $remoteUrl, $cloneRoot) | Out-Null

Ensure-GitIdentity -RepositoryPath $cloneRoot
Sync-ReleaseSnapshot -SourceRoot $projectRoot -CloneRoot $cloneRoot

Invoke-Git -WorkingDirectory $cloneRoot -Arguments @("add", "-A") | Out-Null
$hasChanges = $true
try {
    Invoke-Git -WorkingDirectory $cloneRoot -Arguments @("diff", "--cached", "--quiet")
    $hasChanges = $false
}
catch {
    $hasChanges = $true
}

if ($hasChanges) {
    Write-Host "Creating clean release commit..."
    Invoke-Git -WorkingDirectory $cloneRoot -Arguments @("commit", "-m", "Release $tagName") | Out-Null
}
else {
    Write-Host "No source changes detected in clean publish workspace. Reusing current remote branch state."
}

Invoke-Git -WorkingDirectory $cloneRoot -Arguments @("tag", "-d", $tagName) -AllowFailure | Out-Null
Invoke-Git -WorkingDirectory $cloneRoot -Arguments @("tag", "-a", $tagName, "-m", "Release $tagName") | Out-Null

Write-Host "Pushing source snapshot to $RemoteName/$TargetBranch..."
Invoke-Git -WorkingDirectory $cloneRoot -Arguments @("push", $RemoteName, "HEAD:$TargetBranch") | Out-Null

Write-Host "Updating tag $tagName..."
Invoke-Git -WorkingDirectory $cloneRoot -Arguments @("push", $RemoteName, "refs/tags/$tagName", "--force") | Out-Null

$releaseBody = @{
    tag_name = $tagName
    target_commitish = $TargetBranch
    name = $tagName
    draft = $false
    prerelease = $false
    generate_release_notes = $true
} | ConvertTo-Json

$release = $null
try {
    $release = Invoke-RestMethod -Method GET -Headers $headers -Uri "https://api.github.com/repos/$repoSlug/releases/tags/$tagName"
    $release = Invoke-RestMethod -Method PATCH -Headers $headers -Uri "https://api.github.com/repos/$repoSlug/releases/$($release.id)" -Body $releaseBody
    Write-Host "Existing release found. Metadata refreshed and assets will be replaced."
}
catch {
    $response = $_.Exception.Response
    if (-not $response -or $response.StatusCode.value__ -ne 404) {
        throw
    }
}

if (-not $release) {
    Write-Host "Creating GitHub release $tagName..."
    $release = Invoke-RestMethod -Method POST -Headers $headers -Uri "https://api.github.com/repos/$repoSlug/releases" -Body $releaseBody
}

$assetNames = @(
    [IO.Path]::GetFileName($setupPath),
    [IO.Path]::GetFileName($portablePath)
)

foreach ($asset in $release.assets) {
    if ($assetNames -contains $asset.name) {
        Write-Host "Deleting existing asset $($asset.name)..."
        Invoke-RestMethod -Method DELETE -Headers $headers -Uri "https://api.github.com/repos/$repoSlug/releases/assets/$($asset.id)"
    }
}

$uploadBase = $release.upload_url -replace '\{\?name,label\}', ''
foreach ($assetPath in @($setupPath, $portablePath)) {
    $assetName = [IO.Path]::GetFileName($assetPath)
    $uploadUri = '{0}?name={1}' -f $uploadBase, [Uri]::EscapeDataString($assetName)
    Write-Host "Uploading $assetName..."
    Invoke-RestMethod -Method POST -Headers $headers -ContentType "application/octet-stream" -Uri $uploadUri -InFile $assetPath | Out-Null
}

$releasePage = "https://github.com/$repoSlug/releases/tag/$tagName"
Write-Host ""
Write-Host "Release complete."
Write-Host "Repository : $repoSlug"
Write-Host "Branch     : $TargetBranch"
Write-Host "Tag        : $tagName"
Write-Host "Release    : $releasePage"
