# Registers the per-user scheduled task that pulls the Raspberry Pi backups to this PC every day at 04:30
# (local/pipeline/pull_pi_backup.py). No admin rights needed. Safe to run again: an existing task is replaced.
#
#   powershell -ExecutionPolicy Bypass -File E:\new_ccty_bangkok\launch\backup\install_pull_task.ps1
#
# The task only runs while the user is logged on (LogonType Interactive). If the PC was off, asleep or logged
# out at 04:30, it catches up at the next logon (StartWhenAvailable). WakeToRun wakes a sleeping PC for it.
# Remove it with: Unregister-ScheduledTask -TaskName 'BKK StreetSmart pull Pi backup' -Confirm:$false

$ErrorActionPreference = 'Stop'

$TaskName = 'BKK StreetSmart pull Pi backup'
$WorkDir  = 'E:\new_ccty_bangkok'
$Python   = Join-Path $WorkDir '.venv\Scripts\pythonw.exe'
$Script   = Join-Path $WorkDir 'local\pipeline\pull_pi_backup.py'

foreach ($p in @($Python, $Script)) {
    if (-not (Test-Path -LiteralPath $p)) { throw "Missing: $p" }
}

$action = New-ScheduledTaskAction -Execute $Python -Argument ('"' + $Script + '"') -WorkingDirectory $WorkDir
$trigger = New-ScheduledTaskTrigger -Daily -At 04:30
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Replaced existing task '$TaskName'."
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'Daily 04:30: copy the Raspberry Pi backups to D:\BKK-Backup\pi (off the Pi SSD).' | Out-Null

$t = Get-ScheduledTask -TaskName $TaskName
Write-Output ("Registered '{0}', state: {1}" -f $t.TaskName, $t.State)
Write-Output ("Next run: {0}" -f (Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)
