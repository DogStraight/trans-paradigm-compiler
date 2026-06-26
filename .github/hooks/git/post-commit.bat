#!/usr/bin/env pwsh
# Post-commit hook — 更新 session-summary.md 的当前状态

$summary = ".github/session-summary.md"
if (-not (Test-Path $summary)) { exit 0 }

$sha = git rev-parse --short HEAD
$today = Get-Date -Format "yyyy-MM-dd"
$content = Get-Content $summary -Raw

# 更新分支行中的 SHA
$content = $content -replace '(?<=-\s\*\*分支\*\*:\s`dev`（`)[^`]+', $sha
# 更新标题日期
$content = $content -replace '(?<=# Session Summary — )\S+', $today

Set-Content $summary -Value $content -Encoding UTF8 -NoNewline
exit 0
