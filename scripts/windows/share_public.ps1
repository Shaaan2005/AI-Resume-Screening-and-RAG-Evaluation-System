<#
Shares the app on a public https link through a free Cloudflare quick tunnel
(no account needed; install once with: winget install Cloudflare.cloudflared).

While sharing, the app runs in public-safe demo mode:
  - it searches a clean index of only the sample resumes in resumes/
    (chromadb_public/, built automatically the first time), never your uploads
  - visitors get a separate account database (demo_users.db)
  - visitors' uploaded resumes are scored, then deleted

The link is printed below and saved in tunnel.log. It changes every time.
Press Ctrl+C to stop sharing; the app then restarts in normal local mode.
#>
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$url = "http://127.0.0.1:5000"
Set-Location $root

$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) {
    $cf = Get-ChildItem "C:\Program Files*\cloudflared\cloudflared.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $cf) {
    Write-Host "cloudflared is not installed. Run: winget install Cloudflare.cloudflared" -ForegroundColor Red
    Read-Host "Press Enter to close"; exit 1
}

function Test-ServerUp {
    try { (Invoke-WebRequest "$url/login" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { $false }
}

& (Join-Path $PSScriptRoot "stop_server.ps1") | Out-Null

if (-not (Test-Path (Join-Path $root "chromadb_public"))) {
    Write-Host "Building the clean public search index (first time only, ~1-3 minutes)..." -ForegroundColor Cyan
    py vector_store.py chromadb_public
}

Write-Host "Starting the app in public demo mode..." -ForegroundColor Cyan
$env:DEMO_MODE = "1"
$env:CHROMA_PATH = "chromadb_public"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
Start-Process -FilePath "py" -ArgumentList "app.py" -WorkingDirectory $root -WindowStyle Hidden
for ($i = 0; $i -lt 90 -and -not (Test-ServerUp); $i++) { Start-Sleep -Seconds 2 }
if (-not (Test-ServerUp)) { Write-Host "The app did not start; check app.log." -ForegroundColor Red }

Write-Host ""
Write-Host "Opening the public link. Look for the https://....trycloudflare.com address below." -ForegroundColor Green
Write-Host "Keep this window open while sharing. Press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""
$log = Join-Path $root "tunnel.log"
Remove-Item $log -ErrorAction SilentlyContinue
try {
    & $cf tunnel --no-autoupdate --logfile $log --url $url
}
finally {
    Write-Host "Stopping the public link and returning the app to normal local mode..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "stop_server.ps1") | Out-Null
    Remove-Item Env:DEMO_MODE, Env:CHROMA_PATH -ErrorAction SilentlyContinue
    & (Join-Path $PSScriptRoot "start_server.ps1") -NoBrowser
}
