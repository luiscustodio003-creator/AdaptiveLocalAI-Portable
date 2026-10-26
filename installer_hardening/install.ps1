[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,

    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),

    [string]$BackupRoot = "",

    [string]$PythonPath = "",

    [switch]$RunTests,

    [string]$TestPath = "tests"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-CanonicalPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Resolve-ContainedPath {
    param(
        [string]$Root,
        [string]$RelativePath
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        throw "Caminho vazio no manifesto."
    }

    if ([System.IO.Path]::IsPathRooted($RelativePath)) {
        throw "Caminho absoluto proibido: $RelativePath"
    }

    $parts = $RelativePath -split '[\\/]'
    if ($parts -contains '..' -or $parts -contains '.') {
        throw "Travessia de diretorias proibida: $RelativePath"
    }

    $candidate = [System.IO.Path]::GetFullPath(
        (Join-Path $Root $RelativePath)
    )

    $prefix = $Root.TrimEnd('\', '/') + '\'
    if (-not $candidate.StartsWith(
        $prefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Caminho fora da raiz autorizada: $RelativePath"
    }

    return $candidate
}

function Assert-NoReparsePoint {
    param(
        [string]$Root,
        [string]$Target
    )

    $relative = $Target.Substring(
        $Root.TrimEnd('\', '/').Length
    ).TrimStart('\', '/')

    $current = $Root

    foreach ($part in ($relative -split '[\\/]')) {
        if ([string]::IsNullOrWhiteSpace($part)) { continue }

        $current = Join-Path $current $part

        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band
                [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Link/reparse point nao permitido: $current"
            }
        }
    }
}

$root = Get-CanonicalPath $ProjectRoot

if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw "Raiz do projeto inexistente: $root"
}

$manifestFull = Get-CanonicalPath $ManifestPath
if (-not (Test-Path -LiteralPath $manifestFull -PathType Leaf)) {
    throw "Manifesto inexistente: $manifestFull"
}

$manifest = Get-Content -LiteralPath $manifestFull -Raw |
    ConvertFrom-Json

if ($manifest.schema_version -ne 1) {
    throw "Versao de manifesto nao suportada."
}

if ($null -eq $manifest.files -or @($manifest.files).Count -eq 0) {
    throw "O manifesto nao contem ficheiros."
}

$items = @()
$destinations = @{}

foreach ($entry in $manifest.files) {
    if ([string]::IsNullOrWhiteSpace([string]$entry.source) -or
        [string]::IsNullOrWhiteSpace([string]$entry.destination)) {
        throw "Cada entrada exige source e destination."
    }

    if ([string]$entry.sha256 -notmatch '^[A-Fa-f0-9]{64}$') {
        throw "SHA-256 invalido para $($entry.source)."
    }

    $source = Resolve-ContainedPath $root ([string]$entry.source)
    $destination = Resolve-ContainedPath $root ([string]$entry.destination)

    $key = $destination.ToLowerInvariant()
    if ($destinations.ContainsKey($key)) {
        throw "Destino duplicado: $($entry.destination)"
    }
    $destinations[$key] = $true

    Assert-NoReparsePoint $root $source
    Assert-NoReparsePoint $root $destination

    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Ficheiro de origem inexistente: $($entry.source)"
    }

    $actualHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($actualHash -ne ([string]$entry.sha256).ToUpperInvariant()) {
        throw "SHA-256 nao coincide para $($entry.source)."
    }

    if (Test-Path -LiteralPath $destination -PathType Container) {
        throw "O destino e uma diretoria: $($entry.destination)"
    }

    $items += [PSCustomObject]@{
        Source = $source
        Destination = $destination
        RelativeDestination = [string]$entry.destination
        ExpectedHash = ([string]$entry.sha256).ToUpperInvariant()
        Existed = (Test-Path -LiteralPath $destination -PathType Leaf)
    }
}

if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $BackupRoot = Join-Path $root "backups\installer-transactions"
}

$backupBase = Get-CanonicalPath $BackupRoot
if (-not $backupBase.StartsWith(
    ($root + '\'),
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "A pasta de backups tem de estar dentro do projeto."
}

$transactionName = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N")
$transaction = Join-Path $backupBase $transactionName

New-Item -ItemType Directory -Path $transaction -Force | Out-Null

$journal = @()
$committed = $false

try {
    foreach ($item in $items) {
        $backupFile = $null

        if ($item.Existed) {
            $backupFile = Join-Path $transaction (
                "files\" + $item.RelativeDestination
            )

            $backupDirectory = Split-Path $backupFile -Parent
            New-Item -ItemType Directory -Path $backupDirectory -Force |
                Out-Null

            Copy-Item -LiteralPath $item.Destination `
                -Destination $backupFile

            $originalHash = (
                Get-FileHash -LiteralPath $item.Destination -Algorithm SHA256
            ).Hash

            $backupHash = (
                Get-FileHash -LiteralPath $backupFile -Algorithm SHA256
            ).Hash

            if ($originalHash -ne $backupHash) {
                throw "A verificacao do backup falhou: $($item.RelativeDestination)"
            }
        }

        $journal += [PSCustomObject]@{
            Destination = $item.RelativeDestination
            Existed = $item.Existed
            BackupFile = if ($backupFile) {
                $backupFile.Substring($transaction.Length).TrimStart('\', '/')
            } else { $null }
        }
    }

    $journalPath = Join-Path $transaction "journal.json"
    [PSCustomObject]@{
        schema_version = 1
        project_root = $root
        created_utc = [DateTime]::UtcNow.ToString("o")
        files = @($journal)
    } | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $journalPath -Encoding UTF8

    foreach ($item in $items) {
        $parent = Split-Path $item.Destination -Parent
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $item.Source `
            -Destination $item.Destination -Force

        $installedHash = (
            Get-FileHash -LiteralPath $item.Destination -Algorithm SHA256
        ).Hash

        if ($installedHash -ne $item.ExpectedHash) {
            throw "Verificacao pos-instalacao falhou: $($item.RelativeDestination)"
        }
    }

    if ($RunTests) {
        if ([string]::IsNullOrWhiteSpace($PythonPath) -or
            -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "RunTests exige um PythonPath valido."
        }

        $tests = Resolve-ContainedPath $root $TestPath
        if (-not (Test-Path -LiteralPath $tests)) {
            throw "Caminho de testes inexistente: $TestPath"
        }

        Push-Location $root
        try {
            & $PythonPath -m pytest $tests
            if ($LASTEXITCODE -ne 0) {
                throw "Os testes falharam com codigo $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }

    $committed = $true
    Write-Host "Instalacao concluida." -ForegroundColor Green
    Write-Host "Backup/transacao: $transaction"
}
catch {
    $installError = $_
    Write-Host "Falha na instalacao. A tentar restaurar os ficheiros..." `
        -ForegroundColor Red

    $restoreErrors = @()

    for ($journalIndex = $journal.Count - 1; $journalIndex -ge 0; $journalIndex--) {
        $entry = $journal[$journalIndex]
        try {
            $destination = Resolve-ContainedPath $root $entry.Destination

            if ($entry.Existed) {
                $backupFile = Join-Path $transaction $entry.BackupFile

                if (-not (Test-Path -LiteralPath $backupFile -PathType Leaf)) {
                    throw "Backup em falta: $backupFile"
                }

                $parent = Split-Path $destination -Parent
                New-Item -ItemType Directory -Path $parent -Force |
                    Out-Null
                Copy-Item -LiteralPath $backupFile `
                    -Destination $destination -Force
            }
            elseif (Test-Path -LiteralPath $destination -PathType Leaf) {
                Remove-Item -LiteralPath $destination -Force
            }
        }
        catch {
            $restoreErrors += $_.Exception.Message
        }
    }

    if ($restoreErrors.Count -gt 0) {
        Write-Host "ATENCAO: a restauracao nao ficou completa:" `
            -ForegroundColor Red
        $restoreErrors | ForEach-Object { Write-Host $_ }
    }

    throw $installError
}
finally {
    if (-not $committed) {
        Write-Host "A transacao falhou. Registos preservados em: $transaction" `
            -ForegroundColor Yellow
    }
}
