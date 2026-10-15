# Registers (or with -Remove, deletes) the "BKK Monitor collector" scheduled task for the signed-in user: it starts
# launch\monitor\collector.py with pythonw (no window) at logon and keeps it running. Also puts the "BKK Monitor"
# icon on the Desktop and starts the collector now. No administrator rights needed.
param([switch]$Remove)
$name = 'BKK Monitor collector'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
$link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'BKK Monitor.lnk'
if ($Remove) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $link -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed the task '$name' and the Desktop icon."
    return
}
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$PSScriptRoot\collector.py`"" -WorkingDirectory $root
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $logon -Settings $settings `
    -Description 'BKK Monitor: checks servers, AI agents and YOLO every 30 s. launch\monitor' -Force | Out-Null
Start-ScheduledTask -TaskName $name
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $pyw
$s.Arguments = "`"$PSScriptRoot\monitor_app.py`""
$s.WorkingDirectory = $root
$s.IconLocation = "$PSScriptRoot\icons\monitor.ico"
$s.Save()
Write-Host "[OK] Task '$name' started (runs at every logon). Desktop icon: BKK Monitor. Log: $PSScriptRoot\state\collector.log"
