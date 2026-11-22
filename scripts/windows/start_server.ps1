<#
Starts the AI Resume Screening web app in the background (no console window)
if it isn't already running, then opens it in the browser.

  start_server.ps1              # start if needed + open http://127.0.0.1:5000
  start_server.ps1 -NoBrowser   # start if needed only (used at Windows login)

Logs go to app.log in the project folder. Stop it with stop_server.ps1.
#>
param([switch]$NoBrowser)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # project folder
$url = "http://127.0.0.1:5000"

function Test-ServerUp {
    try { (Invoke-WebRequest "$url/login" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { $false }
}

if (-not (Test-ServerUp)) {
    $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
    # A hidden console (not pythonw) so libraries that print progress bars still work
    Start-Process -FilePath "py" -ArgumentList "app.py" -WorkingDirectory $root -WindowStyle Hidden
    # Loading the models takes ~20-60 seconds
    for ($i = 0; $i -lt 90 -and -not (Test-ServerUp); $i++) { Start-Sleep -Seconds 2 }
}

if (-not $NoBrowser) {
    if (Test-ServerUp) { Start-Process $url }
    else { Write-Host "The server did not start. Check app.log in $root" -ForegroundColor Red; Start-Sleep -Seconds 10 }
}
