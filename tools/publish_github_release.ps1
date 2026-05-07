param(
    [string]$Token = "",
    [string]$RemoteName = "origin",
    [string]$TargetBranch = ""
)

$ErrorActionPreference = "Stop"

function Get-PlainTextFromSecureString {
    param([System.Security.SecureString]$SecureValue)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Invoke-Git {
    param(
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $output = & git @Arguments 2>&1
    if (-not $AllowFailure -and $LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    return ($output -join [Environment]::NewLine).Trim()
}

function Invoke-AuthenticatedGit {
    param(
        [string]$BasicAuthHeader,
        [string[]]$Arguments
    )

    $output = & git -c "http.extraheader=AUTHORIZATION: basic $BasicAuthHeader" @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
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

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not $Token) {
    $secureToken = Read-Host "Enter GitHub personal access token" -AsSecureString
    $Token = Get-PlainTextFromSecureString -SecureValue $secureToken
}

if (-not $Token) {
    throw "A GitHub token is required."
}

$versionFile = Join-Path $projectRoot "src\technocops_ddc\__init__.py"
$versionMatch = Select-String -Path $versionFile -Pattern 'APP_VERSION = "([^"]+)"' | Select-Object -First 1
if (-not $versionMatch) {
    throw "Unable to detect application version from $versionFile"
}

$appVersion = $versionMatch.Matches[0].Groups[1].Value
$tagName = "v$appVersion"
$setupPath = Join-Path $projectRoot "release\installer\Technocops_DDC_Converter_HTML_to_XML_Pro_Setup_v$appVersion.exe"
$portablePath = Join-Path $projectRoot "release\installer\Technocops_DDC_Converter_HTML_to_XML_Pro_Portable_v$appVersion.zip"

if (-not (Test-Path $setupPath)) {
    throw "Setup EXE was not found: $setupPath"
}
if (-not (Test-Path $portablePath)) {
    throw "Portable ZIP was not found: $portablePath"
}

$statusOutput = Invoke-Git -Arguments @("status", "--short")
if ($statusOutput) {
    Write-Warning "Git working tree is not clean. The release will still use the current committed HEAD only."
}

$remoteUrl = Invoke-Git -Arguments @("remote", "get-url", $RemoteName)
$repository = Parse-GitHubRepository -RemoteUrl $remoteUrl
$repoSlug = "$($repository.Owner)/$($repository.Repo)"

$headers = @{
    Accept = "application/vnd.github+json"
    Authorization = "Bearer $Token"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$repoInfo = Invoke-RestMethod -Method GET -Headers $headers -Uri "https://api.github.com/repos/$repoSlug"
if (-not $TargetBranch) {
    $TargetBranch = $repoInfo.default_branch
}

$basicAuth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("x-access-token:$Token"))

$localTagCheck = Invoke-Git -Arguments @("rev-parse", "--verify", $tagName) -AllowFailure
if (-not $localTagCheck) {
    Write-Host "Creating local tag $tagName"
    Invoke-Git -Arguments @("tag", "-a", $tagName, "-m", "Release $tagName")
}
else {
    Write-Host "Using existing local tag $tagName"
}

Write-Host "Pushing current HEAD to $RemoteName/$TargetBranch"
Invoke-AuthenticatedGit -BasicAuthHeader $basicAuth -Arguments @("push", $RemoteName, "HEAD:$TargetBranch")

Write-Host "Pushing tag $tagName"
Invoke-AuthenticatedGit -BasicAuthHeader $basicAuth -Arguments @("push", $RemoteName, "refs/tags/$tagName")

$release = $null
try {
    $release = Invoke-RestMethod -Method GET -Headers $headers -Uri "https://api.github.com/repos/$repoSlug/releases/tags/$tagName"
    Write-Host "Existing release found for $tagName. Matching assets will be replaced."
}
catch {
    $response = $_.Exception.Response
    if (-not $response -or $response.StatusCode.value__ -ne 404) {
        throw
    }
}

if (-not $release) {
    $releaseBody = @{
        tag_name = $tagName
        target_commitish = $TargetBranch
        name = $tagName
        draft = $false
        prerelease = $false
        generate_release_notes = $true
    } | ConvertTo-Json

    Write-Host "Creating GitHub release $tagName"
    $release = Invoke-RestMethod -Method POST -Headers $headers -Uri "https://api.github.com/repos/$repoSlug/releases" -Body $releaseBody
}

$assetNames = @(
    [IO.Path]::GetFileName($setupPath),
    [IO.Path]::GetFileName($portablePath)
)

foreach ($asset in $release.assets) {
    if ($assetNames -contains $asset.name) {
        Write-Host "Deleting existing asset $($asset.name)"
        Invoke-RestMethod -Method DELETE -Headers $headers -Uri "https://api.github.com/repos/$repoSlug/releases/assets/$($asset.id)"
    }
}

$uploadUrl = $release.upload_url -replace '\{\?name,label\}', ''
foreach ($assetPath in @($setupPath, $portablePath)) {
    $assetName = [IO.Path]::GetFileName($assetPath)
    Write-Host "Uploading $assetName"
    Invoke-RestMethod `
        -Method POST `
        -Headers $headers `
        -ContentType "application/octet-stream" `
        -Uri "$uploadUrl?name=$assetName" `
        -InFile $assetPath | Out-Null
}

$releasePage = "https://github.com/$repoSlug/releases/tag/$tagName"
Write-Host ""
Write-Host "Release complete."
Write-Host "Repository : $repoSlug"
Write-Host "Branch     : $TargetBranch"
Write-Host "Tag        : $tagName"
Write-Host "Release    : $releasePage"
