
$ErrorActionPreference = "Stop"

$path = "D:\Dev\Python\AdaptiveLocalAI-Portable\src\ui\index.html"
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)

function U([int[]]$c) {
    return -join ($c | ForEach-Object { [char]$_ })
}

$html = [System.IO.File]::ReadAllText($path, $utf8)
$original = $html

# Correct known punctuation sequences only.
$html = $html.Replace((U @(0xE2,0x80,0xA6)), (U @(0x2026)))
$html = $html.Replace((U @(0xE2,0x80,0x94)), (U @(0x2014)))
$html = $html.Replace((U @(0xC2,0xB7)), (U @(0xB7)))

# Common mojibake forms as they appear in the current HTML.
$html = $html.Replace((U @(0xC3,0xA2,0xE2,0x82,0xAC,0xC2,0xA6)), (U @(0x2026)))
$html = $html.Replace((U @(0xC3,0xA2,0xE2,0x82,0xAC,0xE2,0x82,0xAC,0xC2,0x94)), (U @(0x2014)))
$html = $html.Replace((U @(0xC3,0x82,0xC2,0xB7)), (U @(0xB7)))

if ($html -ceq $original) {
    Write-Host "No matching punctuation changed." -ForegroundColor Yellow
    exit 0
}

$backup = "$path.bak-before-repair3-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$temp = "$path.repair-tmp"

Copy-Item -LiteralPath $path -Destination $backup
[System.IO.File]::WriteAllText($temp, $html, (New-Object System.Text.UTF8Encoding($false)))

$check = [System.IO.File]::ReadAllText($temp, $utf8)
if ($check -cne $html) {
    Remove-Item -LiteralPath $temp -Force
    throw "Validation failed. Original HTML preserved."
}

Move-Item -LiteralPath $temp -Destination $path -Force
Write-Host "Repair 3 completed. Backup: $backup" -ForegroundColor Green
