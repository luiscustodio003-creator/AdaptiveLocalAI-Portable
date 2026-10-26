$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$UiUrl = "http://127.0.0.1:8080/"
$HealthUrl = "http://127.0.0.1:8080/api/health"

function Test-AdaptiveLocalAIHealth {
    try {
        $Response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        if ([int]$Response.StatusCode -ne 200) { return $false }
        $Payload = $Response.Content | ConvertFrom-Json
        return ($Payload.ok -eq $true -and $Payload.app -eq "AdaptiveLocalAI-Portable")
    } catch {
        return $false
    }
}

function Test-TcpPort {
    param([string]$Address, [int]$Port)
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Async = $Client.BeginConnect($Address, $Port, $null, $null)
        if (-not $Async.AsyncWaitHandle.WaitOne(500)) { return $false }
        return $Client.Connected
    } catch {
        return $false
    } finally {
        $Client.Close()
    }
}

# If the API is already alive, reuse it instead of creating a duplicate server.
if (Test-AdaptiveLocalAIHealth) {
    Write-Host "AdaptiveLocalAI ja esta ativo. A abrir a interface..." -ForegroundColor Green
    Start-Process -FilePath $UiUrl
    exit 0
}

# Do not start a second app if something else owns port 8080.
if (Test-TcpPort -Address "127.0.0.1" -Port 8080) {
    throw "A porta 8080 esta ocupada, mas a API AdaptiveLocalAI nao respondeu. Verifica o processo antes de voltar a arrancar."
}

$Python = Get-Command py -ErrorAction SilentlyContinue
if ($Python) {
    $Version = & py -3.12 -c "import sys; print(sys.version_info >= (3, 12))" 2>$null
    if ($Version -eq "True") {
        $PythonExe = "py"
        $PythonArgs = @("-3.12", "src\app.py")
    } else {
        $PythonExe = "py"
        $PythonArgs = @("src\app.py")
    }
} else {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) { throw "Python nao encontrado. Instala Python 3.12 ou posterior." }
    $PythonExe = $Python.Source
    $PythonArgs = @("src\app.py")
}

Write-Host "`nAdaptiveLocalAI-Portable" -ForegroundColor Cyan
Write-Host "Pasta: $Root"
Write-Host "A iniciar API local..." -ForegroundColor Green
Write-Host "O navegador so abrira depois de /api/health responder HTTP 200."
Write-Host "A calibracao dos modelos pode continuar em segundo plano; nao bloqueia o arranque da interface."

# Wait in a background job so the app can keep writing its normal console output.
$BrowserJob = Start-Job -ArgumentList $UiUrl, $HealthUrl -ScriptBlock {
    param($PageUrl, $ApiHealthUrl)
    $Deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $Deadline) {
        try {
            $Response = Invoke-WebRequest -Uri $ApiHealthUrl -UseBasicParsing -TimeoutSec 2
            if ([int]$Response.StatusCode -eq 200) {
                $Payload = $Response.Content | ConvertFrom-Json
                if ($Payload.ok -eq $true -and $Payload.app -eq "AdaptiveLocalAI-Portable") {
                    Start-Process -FilePath $PageUrl
                    Write-Output "READY: navegador aberto depois da API ficar pronta."
                    return
                }
            }
        } catch {
            # The API is still starting; retry without opening the browser early.
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Output "TIMEOUT: a API nao ficou pronta em 60 segundos; o navegador nao foi aberto."
}

try {
    & $PythonExe @PythonArgs
} finally {
    if ($BrowserJob) {
        if ($BrowserJob.State -eq "Running") { Stop-Job -Job $BrowserJob -ErrorAction SilentlyContinue }
        $JobOutput = Receive-Job -Job $BrowserJob -ErrorAction SilentlyContinue
        if ($JobOutput) { $JobOutput | ForEach-Object { Write-Host $_ } }
        Remove-Job -Job $BrowserJob -Force -ErrorAction SilentlyContinue
    }
}