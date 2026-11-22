<#
Creates (for the current Windows user):
  - a Startup entry: the server starts in the background at every login
  - a desktop shortcut "AI Resume Screening": opens the app (starting it if needed)
  - a desktop shortcut "Stop AI Resume Screening"
  - a desktop shortcut "Share AI Resume Screening": public link via share_public.ps1

Run once:   powershell -ExecutionPolicy Bypass -File scripts\windows\install_shortcuts.ps1
Undo:       powershell -ExecutionPolicy Bypass -File scripts\windows\install_shortcuts.ps1 -Remove
#>
param([switch]$Remove)

$start = Join-Path $PSScriptRoot "start_server.ps1"
$stop = Join-Path $PSScriptRoot "stop_server.ps1"
$share = Join-Path $PSScriptRoot "share_public.ps1"
$shell = New-Object -ComObject WScript.Shell
$startup = [Environment]::GetFolderPath("Startup")
$desktop = [Environment]::GetFolderPath("Desktop")

$links = @(
    @{ Path = Join-Path $startup "AI Resume Screening (background).lnk"; Script = $start; Extra = "-NoBrowser" },
    @{ Path = Join-Path $desktop "AI Resume Screening.lnk"; Script = $start; Extra = "" },
    @{ Path = Join-Path $desktop "Stop AI Resume Screening.lnk"; Script = $stop; Extra = "" },
    @{ Path = Join-Path $desktop "Share AI Resume Screening.lnk"; Script = $share; Extra = ""; Visible = $true }
)

foreach ($l in $links) {
    if ($Remove) {
        if (Test-Path $l.Path) { Remove-Item $l.Path -Confirm:$false; Write-Host "Removed $($l.Path)" }
        continue
    }
    $s = $shell.CreateShortcut($l.Path)
    $s.TargetPath = "powershell.exe"
    $style = if ($l.Visible) { "Normal" } else { "Hidden" }
    $s.Arguments = "-NoProfile -WindowStyle $style -ExecutionPolicy Bypass -File `"$($l.Script)`" $($l.Extra)".Trim()
    $s.WorkingDirectory = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $s.IconLocation = "shell32.dll,13"
    $s.Save()
    Write-Host "Created $($l.Path)"
}
