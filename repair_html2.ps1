
$ErrorActionPreference = "Stop"

$path = "D:\Dev\Python\AdaptiveLocalAI-Portable\src\ui\index.html"
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)

function U([int[]]$c) {
    return -join ($c | ForEach-Object { [char]$_ })
}

$html = [System.IO.File]::ReadAllText($path, $utf8)
$original = $html

$fixes = @(
    @((U @(0x61,0x6A,0x75,0x73,0x74,0xC3,0xA1,0x76,0x65,0x6C)), (U @(0x61,0x6A,0x75,0x73,0x74,0xE1,0x76,0x65,0x6C))),
    @((U @(0x43,0x6F,0x6E,0x66,0x69,0x67,0x75,0x72,0x61,0xC3,0xA7,0xC3,0xA3,0x6F)), (U @(0x43,0x6F,0x6E,0x66,0x69,0x67,0x75,0x72,0x61,0xE7,0xE3,0x6F))),
    @((U @(0xC3,0xA2,0xE2,0x82,0xAC,0xC2,0xA6)), (U @(0x2026))),
    @((U @(0xC3,0xA2,0xE2,0x82,0xAC,0xE2,0x82,0xAC,0xC2,0x94)), (U @(0x2014))),
    @((U @(0xC3,0xA2,0xCB,0x9C,0xC2,0xB0)), (U @(0x2630))),
    @((U @(0xC3,0x82,0xC2,0xB7)), (U @(0xB7)))
)

foreach ($fix in $fixes) {
    $html = $html.Replace($fix[0], $fix[1])
}

if ($html -ceq $original) {
    Write-Host "No changes made." -ForegroundColor Yellow
    exit 0
}

$backup = "$path.bak-before-repair2-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$temp = "$path.repair-tmp"

Copy-Item -LiteralPath $path -Destination $backup
[System.IO.File]::WriteAllText($temp, $html, (New-Object System.Text.UTF8Encoding($false)))

$check = [System.IO.File]::ReadAllText($temp, $utf8)
if ($check -cne $html) {
    Remove-Item -LiteralPath $temp -Force
    throw "Validation failed. Original HTML preserved."
}

Move-Item -LiteralPath $temp -Destination $path -Force
Write-Host "Repair 2 completed. Backup: $backup" -ForegroundColor Green
