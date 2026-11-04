@echo off
setlocal
chcp 65001 >nul
set "SRC=%~1"
if not defined SRC set "SRC=%~dp0"
set "PS=%TEMP%\folder_pack_%RANDOM%_%RANDOM%.ps1"
more +19 "%~f0" > "%PS%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS%" "%SRC%" "%~f0"
set "CODE=%ERRORLEVEL%"
del "%PS%" >nul 2>nul
if not "%CODE%"=="0" goto fail
echo.
pause
exit /b 0
:fail
echo.
echo Packaging failed. Check the source folder.
pause
exit /b 1
param([string]$Source = '', [string]$ToolPath = '')

$ErrorActionPreference = 'Stop'
$script:ToolName = if ($ToolPath) { Split-Path -Leaf $ToolPath } else { '' }

function Resolve-Folder([string]$path) {
    if (-not $path) { throw 'no source folder' }
    $item = Get-Item -LiteralPath $path -Force
    if (-not $item.PSIsContainer) { throw 'source is not a folder' }
    return $item.FullName.TrimEnd('\')
}

function Get-Version([string]$root) {
    $manifest = Join-Path $root 'plugin.toml'
    if (Test-Path -LiteralPath $manifest) {
        $text = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8
        $match = [regex]::Match($text, '(?m)^version\s*=\s*"([^"]+)"')
        if ($match.Success) { return $match.Groups[1].Value }
    }
    $versionFile = Join-Path $root 'VERSION'
    if (Test-Path -LiteralPath $versionFile) {
        $first = Get-Content -LiteralPath $versionFile -TotalCount 1
        if ($first) { return $first.Trim() }
    }
    return Get-Date -Format 'yyyyMMdd-HHmm'
}

function Get-PluginId([string]$root, [string]$fallback) {
    $manifest = Join-Path $root 'plugin.toml'
    if (Test-Path -LiteralPath $manifest) {
        $text = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8
        $match = [regex]::Match($text, '(?m)^id\s*=\s*"([^"]+)"')
        if ($match.Success) { return $match.Groups[1].Value }
    }
    return $fallback
}

function Test-Excluded([string]$relative) {
    $rel = $relative.Replace('\', '/')
    $parts = $rel -split '/'
    $dirs = @('.git', '.github', '.venv', 'venv', 'node_modules', '__pycache__',
        '.pytest_cache', '.ruff_cache', '.mypy_cache', '.idea', '.vscode',
        'dist', 'build', '.dsh-tmp', 'logs', 'tests', 'test', 'docs', 'tools')
    foreach ($part in $parts) {
        if ($dirs -contains $part) { return $true }
    }
    $name = $parts[-1]
    if ($name -match '\.(pyc|pyo|log|tmp|swp)$') { return $true }
    if ($script:ToolName -and $name -eq $script:ToolName) { return $true }
    if ($name -in @('.DS_Store', 'Thumbs.db', '.packageignore', '.gitignore',
            '.gitattributes', '.editorconfig', 'AGENTS.md', 'pytest.ini', 'ruff.toml')) { return $true }
    foreach ($pattern in $script:IgnorePatterns) {
        $p = $pattern.Replace('\', '/')
        if ($rel -like $p -or $name -like $p) { return $true }
        if ($p.EndsWith('/') -and ($rel -eq $p.TrimEnd('/') -or $rel.StartsWith($p))) { return $true }
    }
    return $false
}

function Get-GitFiles([string]$root) {
    if (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) { return $null }
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { return $null }
    $raw = & $git.Source -c core.quotepath=false -C $root ls-files --cached --others --exclude-standard 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return [pscustomobject]@{
        Files = @($raw | Where-Object { $_ -and $_.Trim() })
    }
}

function Copy-PackageFile([string]$root, [string]$package, [string]$relative) {
    if (Test-Excluded $relative) { return }
    $source = Join-Path $root ($relative.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { return }
    $destination = Join-Path $package ($relative.Replace('/', '\'))
    $parent = Split-Path -Parent $destination
    if ($parent) {
        $null = New-Item -ItemType Directory -Path $parent -Force
    }
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

function Copy-Generic([string]$root, [string]$package, $gitInfo) {
    if ($gitInfo) {
        foreach ($relative in $gitInfo.Files) {
            Copy-PackageFile $root $package $relative
        }
        return
    }
    $stack = New-Object System.Collections.Stack
    $stack.Push($root)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        $entries = Get-ChildItem -LiteralPath $current -Force
        foreach ($entry in $entries) {
            $relative = $entry.FullName.Substring($root.Length).TrimStart('\')
            if (Test-Excluded $relative) { continue }
            if ($entry.PSIsContainer) {
                $stack.Push($entry.FullName)
                continue
            }
            $destination = Join-Path $package $relative
            $parent = Split-Path -Parent $destination
            if ($parent) {
                $null = New-Item -ItemType Directory -Path $parent -Force
            }
            Copy-Item -LiteralPath $entry.FullName -Destination $destination -Force
        }
    }
}

$root = Resolve-Folder $Source
$name = Split-Path -Leaf $root
$isPlugin = (Test-Path -LiteralPath (Join-Path $root 'plugin.toml')) -and
    (Test-Path -LiteralPath (Join-Path $root 'plugin.py'))
$packageId = if ($isPlugin) { Get-PluginId $root $name } else { $name }
$version = Get-Version $root
$dist = Join-Path $root 'dist'
$null = New-Item -ItemType Directory -Path $dist -Force
$zip = Join-Path $dist ($packageId + '-' + $version + '.zip')
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }

$stage = Join-Path $env:TEMP ('folder_pack_' + [guid]::NewGuid().ToString('N'))
$package = Join-Path $stage $packageId
$gitInfo = $null
try {
    $null = New-Item -ItemType Directory -Path $package -Force
    $ignoreFile = Join-Path $root '.packageignore'
    $script:IgnorePatterns = @()
    if (Test-Path -LiteralPath $ignoreFile) {
        $script:IgnorePatterns = @(Get-Content -LiteralPath $ignoreFile -Encoding UTF8 |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -and -not $_.StartsWith('#') })
    }
    $gitInfo = Get-GitFiles $root
    Copy-Generic $root $package $gitInfo
    $count = (Get-ChildItem -LiteralPath $package -Recurse -File | Measure-Object).Count
    Compress-Archive -Path $package -DestinationPath $zip -CompressionLevel Optimal
} finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ''
Write-Host ('OK: ' + $zip)
$mode = if ($isPlugin) { 'plugin' } elseif ($gitInfo) { 'git' } else { 'folder' }
Write-Host ('mode: ' + $mode)
Write-Host ('files: ' + $count)
Write-Host 'Install via the target app if it supports this ZIP layout.'
