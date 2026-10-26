[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [string]$BackupDirectory = ''
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
$backupRoot = Join-Path $project 'backups'

if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
    $candidate = Get-ChildItem -LiteralPath $backupRoot -Directory -Filter 'etapa1_*' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $candidate) { throw "Não foi encontrado backup etapa1_* em $backupRoot" }
    $BackupDirectory = $candidate.FullName
}
$backup = (Resolve-Path -LiteralPath $BackupDirectory).Path
$backupHtml = Join-Path $backup 'index.html'
$targetHtml = Join-Path $project 'src\ui\index.html'
if (-not (Test-Path -LiteralPath $backupHtml -PathType Leaf)) { throw "Backup de index.html não encontrado em $backup" }
Copy-Item -LiteralPath $backupHtml -Destination $targetHtml -Force
$backupTest = Join-Path $backup 'test_ui_stage1.py'
$targetTest = Join-Path $project 'tests\test_ui_stage1.py'
if (Test-Path -LiteralPath $backupTest -PathType Leaf) {
    Copy-Item -LiteralPath $backupTest -Destination $targetTest -Force
} else {
    Remove-Item -LiteralPath $targetTest -Force -ErrorAction SilentlyContinue
}
Write-Host 'REPOSIÇÃO CONCLUÍDA.' -ForegroundColor Green
Write-Host "Interface restaurada a partir de: $backup"
