$summaryPath = Join-Path $PWD ".github" "session-summary.md"
if (Test-Path $summaryPath) {
    $content = Get-Content $summaryPath -Raw
    $output = @{
        systemMessage = "Session summary available at .github/session-summary.md. Read it before starting:"
        continue = $true
    }
    Write-Output ($output | ConvertTo-Json -Compress)
}
exit 0
