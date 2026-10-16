# Registers (or with -Remove, deletes) two scheduled tasks for the signed-in user, both started at logon with pythonw (no window):
#   "BKK Monitor collector": launch\monitor\collector.py, checks servers, AI agents and YOLO every 30 s.
#   "BKK Monitor web": launch\monitor\monitor_web.py, read-only page for the phone on 127.0.0.1:8090
#   (publish it on the tailnet with: tailscale serve --bg 8090).
# Also puts the "BKK Monitor" icon on the Desktop and starts both tasks now. No administrator rights needed.
param([switch]$Remove)
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
$link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'BKK Monitor.lnk'
$tasks = @(
    @{
        Name = 'BKK Monitor collector'
        Script = 'collector.py'
        Description = 'BKK Monitor: checks servers, AI agents and YOLO every 30 s. launch\monitor'
        Started = "[OK] Task 'BKK Monitor collector' started (runs at every logon). Desktop icon: BKK Monitor. Log: $PSScriptRoot\state\collector.log"
    },
    @{
        Name = 'BKK Monitor web'
        Script = 'monitor_web.py'
        Description = 'BKK Monitor web: read-only page for the phone on 127.0.0.1:8090 (tailscale serve --bg 8090). launch\monitor'
        Started = "[OK] Task 'BKK Monitor web' started: http://127.0.0.1:8090/ (view only)."
    }
)
if ($Remove) {
    foreach ($t in $tasks) {
        Stop-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue
    }
    Remove-Item $link -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed the tasks 'BKK Monitor collector' and 'BKK Monitor web' and the Desktop icon."
    return
}
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$PSScriptRoot\$($t.Script)`"" -WorkingDirectory $root
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $logon -Settings $settings `
        -Description $t.Description -Force | Out-Null
    Start-ScheduledTask -TaskName $t.Name
}
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $pyw
$s.Arguments = "`"$PSScriptRoot\monitor_app.py`""
$s.WorkingDirectory = $root
$s.IconLocation = "$PSScriptRoot\icons\monitor.ico"
$s.Save()
foreach ($t in $tasks) { Write-Host $t.Started }
Write-Host "     For the phone, once: tailscale serve --bg 8090   then open https://<this PC>.<tailnet>.ts.net/ in the Tailscale-connected phone."
