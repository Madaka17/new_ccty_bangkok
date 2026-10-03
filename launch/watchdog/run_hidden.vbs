' Runs watchdog.ps1 without flashing a console window every 2 minutes (the scheduled task starts this file).
Dim dir
dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & dir & "\watchdog.ps1""", 0, False
