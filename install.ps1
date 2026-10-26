[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'

$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
$sourceHtml = Join-Path $PSScriptRoot 'payload\src\ui\index.html'
$sourceTest = Join-Path $PSScriptRoot 'payload\tests\test_ui_stage1.py'
$targetHtml = Join-Path $project 'src\ui\index.html'
$targetTests = Join-Path $project 'tests'
$targetTest = Join-Path $targetTests 'test_ui_stage1.py'

if (-not (Test-Path -LiteralPath $sourceHtml -PathType Leaf)) { throw "Ficheiro atualizado não encontrado: $sourceHtml" }
if (-not (Test-Path -LiteralPath $sourceTest -PathType Leaf)) { throw "Teste da Etapa 1 não encontrado: $sourceTest" }
if (-not (Test-Path -LiteralPath $targetHtml -PathType Leaf)) { throw "Interface atual não encontrada: $targetHtml" }
if (-not (Test-Path -LiteralPath (Join-Path $project 'src\app.py') -PathType Leaf)) { throw "Não parece ser a raiz do AdaptiveLocalAI-Portable: src\app.py não encontrado." }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $project "backups\etapa1_$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item -LiteralPath $targetHtml -Destination (Join-Path $backupDir 'index.html')
$hadStageTest = Test-Path -LiteralPath $targetTest
if ($hadStageTest) { Copy-Item -LiteralPath $targetTest -Destination (Join-Path $backupDir 'test_ui_stage1.py') }

Write-Host "Backup: $backupDir" -ForegroundColor Cyan
Write-Host 'A instalar a interface da Etapa 1...' -ForegroundColor Cyan
Copy-Item -LiteralPath $sourceHtml -Destination $targetHtml -Force
New-Item -ItemType Directory -Path $targetTests -Force | Out-Null
Copy-Item -LiteralPath $sourceTest -Destination $targetTest -Force

Push-Location $project
try {
    py -3.12 -m pytest .\tests -v --import-mode=importlib
    $testExit = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($testExit -ne 0) {
    Write-Host 'TESTES FALHARAM. A repor a interface anterior...' -ForegroundColor Red
    Copy-Item -LiteralPath (Join-Path $backupDir 'index.html') -Destination $targetHtml -Force
    if ($hadStageTest) {
        Copy-Item -LiteralPath (Join-Path $backupDir 'test_ui_stage1.py') -Destination $targetTest -Force
    } else {
        Remove-Item -LiteralPath $targetTest -Force -ErrorAction SilentlyContinue
    }
    throw "Instalação revertida automaticamente. Código de saída do pytest: $testExit. Backup preservado em $backupDir"
}

Write-Host ''
Write-Host 'ETAPA 1 INSTALADA E TESTES APROVADOS.' -ForegroundColor Green
Write-Host "Projeto: $project"
Write-Host "Backup para reversão: $backupDir"
Write-Host 'Para reverter, executar .\rollback.ps1 -ProjectRoot "D:\Dev\Python\AdaptiveLocalAI-Portable"'
