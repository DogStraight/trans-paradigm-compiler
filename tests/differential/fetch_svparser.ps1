# fetch_svparser.ps1 - Build sv-parser parse_sv differential target (optional dep).
#
# Same pattern as fetch_verible.ps1: the sv-parser differential
# (run_differential_svparser.py) needs parse_sv.exe; this script builds it from
# the local mirror and copies it to tests/differential/.tools/sv-parser/.
#
# Prereqs:
#   - Rust toolchain (this machine: D:\rust, GNU host+target - the VS BuildTools
#     Windows SDK desktop libs lack kernel32.lib so the msvc target cannot link)
#   - sv-parser source mirror (E:\research\sv-parser, shallow clone)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tests/differential/fetch_svparser.ps1
#   $env:SV_PARSER can override parse_sv.exe location

$ErrorActionPreference = "Stop"

# --- Locate Rust (RUSTUP_HOME/CARGO_HOME or common locations) ---
# 本机约定：rustup 装到 D:\rust\rustup + D:\rust\cargo
$rustupHome = $env:RUSTUP_HOME
$cargoHome = $env:CARGO_HOME
if (-not $rustupHome -and (Test-Path "D:\rust\rustup")) {
    $rustupHome = "D:\rust\rustup"
}
if (-not $cargoHome -and (Test-Path "D:\rust\cargo")) {
    $cargoHome = "D:\rust\cargo"
}
if (-not $rustupHome) { $rustupHome = Join-Path $env:USERPROFILE ".rustup" }
if (-not $cargoHome) { $cargoHome = Join-Path $env:USERPROFILE ".cargo" }
$cargoBin = Join-Path $cargoHome "bin"
if (-not (Test-Path (Join-Path $cargoBin "cargo.exe"))) {
    Write-Error "cargo not found ($cargoBin). Install Rust first: https://rustup.rs"
}

# --- Locate sv-parser mirror ---
$svParser = $env:SV_PARSER_SRC
if (-not $svParser) { $svParser = "E:\research\sv-parser" }
if (-not (Test-Path (Join-Path $svParser "Cargo.toml"))) {
    Write-Error "sv-parser mirror not found ($svParser). Set SV_PARSER_SRC or clone: git clone https://github.com/dalance/sv-parser"
}

# --- Locate mingw-w64 (GNU target linker) ---
$gcc = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "gcc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $gcc) {
    # Fallback: gcc on PATH
    $gccPath = Get-Command gcc -ErrorAction SilentlyContinue
    if (-not $gccPath) {
        Write-Error "gcc not found. Install mingw-w64: winget install -e --id BrechtSanders.WinLibs.POSIX.UCRT"
    }
}
$gccDir = if ($gcc) { Split-Path $gcc.FullName } else { Split-Path $gccPath.Source }

# --- Build ---
$env:PATH = "$cargoBin;$gccDir;$env:PATH"
$env:RUSTUP_HOME = $rustupHome
$env:CARGO_HOME = $cargoHome

Push-Location $svParser
try {
    # Ensure GNU host toolchain is default (build scripts also use gcc,
    # avoiding the msvc link.exe requirement)
    rustup default stable-x86_64-pc-windows-gnu | Out-Null
    cargo build --example parse_sv --release
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed (exit $LASTEXITCODE)" }
}
finally {
    Pop-Location
}

# --- Copy to repo tools dir ---
$dst = Join-Path $PSScriptRoot ".tools\sv-parser"
New-Item -ItemType Directory -Path $dst -Force | Out-Null
$srcExe = Join-Path $svParser "target\release\examples\parse_sv.exe"
Copy-Item $srcExe (Join-Path $dst "parse_sv.exe") -Force

Write-Host "parse_sv.exe ready: $dst\parse_sv.exe"
Write-Host "Run differential: python tests/differential/run_differential_svparser.py"
