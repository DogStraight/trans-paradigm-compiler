# fetch_verible.ps1 — 下载 Verible 官方 Windows 二进制（差分测试依赖）
#
# 差分测试（tests/differential/run_differential.py）需要 verible-verilog-format。
# 本脚本从 chipsalliance/verible 最新 release 拉取 win64 zip 并解压到
# tests/differential/.tools/verible/（该目录已在 .gitignore，不入库）。
#
# 用法:
#     powershell -ExecutionPolicy Bypass -File tests/differential/fetch_verible.ps1
#     # 之后直接跑差分：
#     python tests/differential/run_differential.py
#
# 注：Verible 是 CHIPS Alliance 官方工具（Apache-2.0），二进制仅作测试夹具，
# 不随仓库分发（.tools/ 已 gitignore）。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dest = Join-Path $PSScriptRoot ".tools\verible"

if (Test-Path (Join-Path $dest "verible-verilog-format.exe")) {
    Write-Host "already present: $dest"
    exit 0
}

$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/chipsalliance/verible/releases/latest" `
    -Headers @{ "User-Agent" = "tpc-differential" }
$asset = $rel.assets | Where-Object { $_.name -match "win64.*zip$" } | Select-Object -First 1
if (-not $asset) {
    throw "no win64 zip asset in latest verible release"
}
Write-Host "downloading: $($asset.name) ($([math]::Round($asset.size/1MB,1)) MB)"
$zip = Join-Path $env:TEMP "verible.zip"
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip
New-Item -ItemType Directory -Force (Split-Path -Parent $dest) | Out-Null
Expand-Archive $zip -DestinationPath (Split-Path -Parent $dest) -Force
# 解压产物是 verible-vXXX-...-win64/ 目录 → 统一为 .tools/verible/
$extracted = Get-ChildItem (Split-Path -Parent $dest) -Directory | Where-Object { $_.Name -match "win64" } | Select-Object -First 1
if ($extracted.Name -ne "verible") {
    Move-Item $extracted.FullName $dest -ErrorAction Stop
}
Remove-Item $zip -ErrorAction SilentlyContinue
Write-Host "verible ready: $dest"
