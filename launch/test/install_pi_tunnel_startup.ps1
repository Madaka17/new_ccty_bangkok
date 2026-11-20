# Starts the Bionic tunnel to the Pi (pi_bionic_tunnel.py) at every logon, with a shortcut in this user's
# Startup folder. No admin needed: "schtasks /SC ONLOGON" asks for admin rights ("Access is denied").
# Production on the Pi reaches Bionic only through this tunnel, so without it the flood watch has no AI
# after a reboot.
#   powershell -NoProfile -ExecutionPolicy Bypass -File launch\test\install_pi_tunnel_startup.ps1
#   ... -Uninstall   removes the shortcut
param([switch]$Uninstall)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'BKK Bionic tunnel to Pi.lnk'

if ($Uninstall) {
    if (Test-Path $lnk) { Remove-Item $lnk; "removed: $lnk" } else { "not installed: $lnk" }
    exit 0
}

$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
$s.Arguments = '"' + (Join-Path $root 'launch\test\pi_bionic_tunnel.py') + '"'
$s.WorkingDirectory = $root
$s.Description = 'Keep the ssh tunnel that lets the Pi production server reach Bionic on this PC'
$s.Save()
"installed: $lnk"
"runs: $($s.TargetPath) $($s.Arguments)"
