@echo off
REM Post-commit hook — update session-summary.md
powershell -ExecutionPolicy Bypass -Command ^
    $s = '.github/session-summary.md'; ^
    if (-not (Test-Path $s)) { exit 0 }; ^
    $sha = git rev-parse --short HEAD; ^
    $today = Get-Date -Format 'yyyy-MM-dd'; ^
    $c = Get-Content $s -Raw; ^
    $c = $c -replace '(?<=Session Summary — )\S+', $today; ^
    $c = $c -replace '(?<=`dev`（`)[^`]+', $sha; ^
    Set-Content $s -Value $c -Encoding UTF8 -NoNewline; ^
    exit 0
