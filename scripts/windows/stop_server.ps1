<#
Stops the AI Resume Screening web app started by start_server.ps1
(frees the ~2 GB of memory the models use).
#>
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='py.exe'" |
    Where-Object { $_.CommandLine -match '\bapp\.py\b' }

if (-not $procs) { Write-Host "The server is not running."; exit 0 }
foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -Confirm:$false }
Write-Host "Server stopped."
