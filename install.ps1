# CommitSense pre-push hook installer (Windows)

$ErrorActionPreference = "Stop"

$CommitSenseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$HooksDir = Join-Path (Join-Path ".git" "hooks") ""
$HookFile = Join-Path ".git" "hooks"
$HookFile = Join-Path $HookFile "pre-push"

# Check we're in a git repo
if (-not (Test-Path ".git")) {
    Write-Error "Not a git repository (no .git/ found). Run this from the root of a git repo."
    exit 1
}

# Check Python
try {
    python --version | Out-Null
} catch {
    Write-Error "Python 3 is required but not found."
    exit 1
}

# Create hooks dir if missing
$HooksDir = Join-Path ".git" "hooks"
if (-not (Test-Path $HooksDir)) {
    New-Item -ItemType Directory -Path $HooksDir | Out-Null
}

# Back up existing hook
if (Test-Path $HookFile) {
    Copy-Item $HookFile "$HookFile.bak"
    Write-Host "Backed up existing pre-push hook -> $HookFile.bak"
}

# Write the hook shim (bash script -- Git for Windows uses MinGW bash)
# Convert Windows path to Unix-style for bash
$UnixRoot = $CommitSenseRoot -replace '\\', '/' -replace '^([A-Za-z]):', '/$1'

$HookContent = @"
#!/usr/bin/env bash
cd '$UnixRoot'
python -m hooks.pre_push
"@

Set-Content -Path $HookFile -Value $HookContent -Encoding UTF8 -NoNewline

Write-Host ""
Write-Host "[OK] CommitSense pre-push hook installed"
Write-Host "  Hook: $HookFile"
Write-Host "  Root: $CommitSenseRoot"
