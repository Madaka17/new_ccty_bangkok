# Registers (or with -Remove, deletes) the "BKK StreetSmart watchdog" scheduled task for the signed-in user:
# watchdog.ps1 every 2 minutes while the user is logged on. No administrator rights needed.
param([switch]$Remove)
$name = 'BKK StreetSmart watchdog'
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed the task '$name'."
    return
}
$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$PSScriptRoot\run_hidden.vbs`""
$every = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $name -Action $action -Trigger @($every, $logon) -Settings $settings `
    -Description 'Restarts BKK StreetSmart production (:8000) and ENVIRO (:5050) when they stop answering. launch\watchdog' `
    -Force | Out-Null
Write-Host "[OK] Task '$name' runs every 2 minutes. Log: $PSScriptRoot\state\watchdog.log"
