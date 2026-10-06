# Opens or closes the camera status window (launch\camera_status.bat, a new round every 5 minutes) next to the
# production server. launch\production\start.bat opens it unless one is already open; stop.bat closes it.
param([switch]$Stop)

$bat = Join-Path $PSScriptRoot 'camera_status.bat'
# Only the watching window: a "camera_status.bat --once" run in a terminal is left alone
$open = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
    Where-Object { $_.CommandLine -match 'launch\\camera_status\.bat' -and $_.CommandLine -notmatch '--once|--all|8001' })

if ($Stop) {
    foreach ($p in $open) {
        taskkill /F /T /PID $p.ProcessId *> $null
        Write-Host "[*] Closed camera status window (PID $($p.ProcessId))"
    }
} elseif ($open) {
    Write-Host '[OK] Camera status window is already open.'
} else {
    Start-Process -FilePath 'cmd.exe' -ArgumentList "/c `"`"$bat`"`""
    Write-Host '[*] Camera status window opened: every camera checked every 5 minutes, log in instances\production\camera_status.log'
}
