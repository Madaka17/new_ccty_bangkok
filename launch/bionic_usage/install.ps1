# Installs or removes the Bionic usage collector for the current user.
#
#   powershell -ExecutionPolicy Bypass -File launch\bionic_usage\install.ps1
#   powershell -ExecutionPolicy Bypass -File launch\bionic_usage\install.ps1 -Uninstall
#
# Creates (or replaces) a per-user scheduled task that runs every 10 minutes while
# the user is logged on, hidden, with pythonw (no console window). It also
# creates a "Bionic Usage" shortcut on the Desktop that runs run.bat.
# No administrator rights are needed.

param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$TaskName = 'BKK Bionic usage collect'
$ShortcutName = 'Bionic Usage.lnk'
$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$Pythonw = Join-Path $RepoRoot '.venv\Scripts\pythonw.exe'
$Wrapper = Join-Path $ScriptDir 'scheduled_run.py'
$RunBat = Join-Path $ScriptDir 'run.bat'
$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop $ShortcutName

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Removed scheduled task '$TaskName'."
    } else {
        Write-Output "Scheduled task '$TaskName' was not installed."
    }
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
        Write-Output "Removed Desktop shortcut '$ShortcutName'."
    }
    exit 0
}

if (-not (Test-Path $Pythonw)) {
    throw "pythonw not found at $Pythonw. Create the venv first."
}
if (-not (Test-Path $Wrapper)) {
    throw "Wrapper not found at $Wrapper."
}

# Run every 10 minutes. A repetition duration of 10 years stands in for "forever",
# because some PowerShell versions reject an unlimited duration.
$start = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$action = New-ScheduledTaskAction -Execute $Pythonw `
    -Argument ('"{0}"' -f $Wrapper) -WorkingDirectory $RepoRoot

# Current user only, no elevation, runs only while that user is logged on.
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet -Hidden `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Write-Output "Installed scheduled task '$TaskName' (every 10 minutes, hidden)."

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $RunBat
$shortcut.WorkingDirectory = $ScriptDir
$shortcut.Description = 'Collect Bionic usage and open the report'
$shortcut.Save()
Write-Output "Created Desktop shortcut '$ShortcutName'."
