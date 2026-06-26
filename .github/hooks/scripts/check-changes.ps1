$statusLines = git status --short 2>$null
$untracked = git ls-files --others --exclude-standard 2>$null

$changeCount = 0
if ($statusLines) {
    $changeCount += ($statusLines | Measure-Object).Length
}
if ($untracked) {
    $changeCount += ($untracked | Measure-Object).Length
}

if ($changeCount -gt 0) {
    $message = "There are $changeCount uncommitted changes. Please commit before continuing."
    $output = @{
        systemMessage = $message
        continue = $true
    }
    Write-Output ($output | ConvertTo-Json -Compress)
    exit 0
}

exit 0
