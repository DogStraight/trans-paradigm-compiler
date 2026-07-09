# check-hardcode.ps1 — 检查 linter/ 引擎代码中是否引入了硬编码语言知识
# 在 post-commit 中自动运行。

$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$lintDir = Join-Path $root "lint"
$anyIssue = $false

# ── 规则 1: 禁止 keyword.end* 在 .py 中硬编码 ──
Write-Host "[hardcode-check] 检查 keyword.end* 硬编码..." -ForegroundColor DarkGray
$matches = Select-String -Path (Join-Path $lintDir "*.py") -Pattern 'keyword\.end\w+' -SimpleMatch:$false
if ($matches) {
    foreach ($m in $matches) {
        Write-Host "  ❌ 发现硬编码 keyword.end*: $($m.Path):$($m.LineNumber) → $($m.Line.Trim())" -ForegroundColor Red
        $anyIssue = $true
    }
}

# ── 规则 2: 禁止 space.* / newline.* 在 .py 中硬编码 ──
Write-Host "[hardcode-check] 检查 token 类型硬编码..." -ForegroundColor DarkGray
$matches = Select-String -Path (Join-Path $lintDir "*.py") -Pattern '"(?:space|newline)\.[\w.]+"' -SimpleMatch:$false
if ($matches) {
    foreach ($m in $matches) {
        Write-Host "  ❌ 发现硬编码 token: $($m.Path):$($m.LineNumber) → $($m.Line.Trim())" -ForegroundColor Red
        $anyIssue = $true
    }
}

# ── 规则 3: 禁止中文字符在代码中硬编码 ──
Write-Host "[hardcode-check] 检查中文错误消息..." -ForegroundColor DarkGray
$matches = Select-String -Path (Join-Path $lintDir "*.py") -Pattern '[\x{4e00}-\x{9fff}]' -SimpleMatch:$false
if ($matches) {
    foreach ($m in $matches) {
        Write-Host "  ❌ 发现中文字符: $($m.Path):$($m.LineNumber) → $($m.Line.Trim())" -ForegroundColor Red
        $anyIssue = $true
    }
}

# ── 结果 ──
if ($anyIssue) {
    Write-Host "`n[hardcode-check] ❌ 发现硬编码语言知识，请修复后提交。" -ForegroundColor Red
    exit 1
} else {
    Write-Host "[hardcode-check] ✅ 未发现硬编码语言知识。" -ForegroundColor Green
    exit 0
}
