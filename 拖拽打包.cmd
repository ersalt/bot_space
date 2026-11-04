@echo off
setlocal
chcp 65001 >nul
set "SRC=%~1"
if not defined SRC set "SRC=%~dp0"
set "PS=%TEMP%\folder_pack_%RANDOM%_%RANDOM%.ps1"
more +19 "%~f0" > "%PS%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS%" "%SRC%"
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
param([string]$Source = '')

$ErrorActionPreference = 'Stop'

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
    if ($name -in @('.DS_Store', 'Thumbs.db', '.packageignore')) { return $true }
    foreach ($pattern in $script:IgnorePatterns) {
        $p = $pattern.Replace('\', '/')
        if ($rel -like $p -or $name -like $p) { return $true }
        if ($p.EndsWith('/') -and ($rel -eq $p.TrimEnd('/') -or $rel.StartsWith($p))) { return $true }
    }
    return $false
}

function Copy-Plugin([string]$root, [string]$package) {
    foreach ($name in @('plugin.toml', 'plugin.py', 'README.md', 'CHANGELOG.md', 'LICENSE')) {
        $source = Join-Path $root $name
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $package -Force
        }
    }
    foreach ($name in @('core', 'pages')) {
        $source = Join-Path $root $name
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $package -Recurse -Force
        }
    }
    $cache = Join-Path $package 'core\__pycache__'
    if (Test-Path -LiteralPath $cache) {
        Remove-Item -LiteralPath $cache -Recurse -Force
    }
}

function Copy-Generic([string]$root, [string]$package) {
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
$version = Get-Version $root
$dist = Join-Path $root 'dist'
$null = New-Item -ItemType Directory -Path $dist -Force
$zip = Join-Path $dist ($name + '-' + $version + '.zip')
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }

$stage = Join-Path $env:TEMP ('folder_pack_' + [guid]::NewGuid().ToString('N'))
$package = Join-Path $stage $name
try {
    $null = New-Item -ItemType Directory -Path $package -Force
    if ($isPlugin) {
        Copy-Plugin $root $package
    } else {
        $ignoreFile = Join-Path $root '.packageignore'
        $script:IgnorePatterns = @()
        if (Test-Path -LiteralPath $ignoreFile) {
            $script:IgnorePatterns = @(Get-Content -LiteralPath $ignoreFile -Encoding UTF8 |
                ForEach-Object { $_.Trim() } |
                Where-Object { $_ -and -not $_.StartsWith('#') })
        }
        Copy-Generic $root $package
    }
    $count = (Get-ChildItem -LiteralPath $package -Recurse -File | Measure-Object).Count
    Compress-Archive -Path $package -DestinationPath $zip -CompressionLevel Optimal
} finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ''
Write-Host ('OK: ' + $zip)
Write-Host ('mode: ' + $(if ($isPlugin) { 'plugin' } else { 'folder' }))
Write-Host ('files: ' + $count)
Write-Host 'Install via the target app if it supports this ZIP layout.'
