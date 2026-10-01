# Installs (or repairs) the cloudflared Windows service for the tunnel in config.yml next to this script.
# Run as administrator:  powershell -ExecutionPolicy Bypass -File launch\cloudflare\install_service.ps1
# The service runs as LocalSystem, which does not read %USERPROFILE%\.cloudflared, so it is pointed at this
# config.yml explicitly.
$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$config = Join-Path $PSScriptRoot 'config.yml'

& $exe tunnel --config $config ingress validate
if ($LASTEXITCODE -ne 0) { throw "config.yml is not valid" }

if (-not (Get-Service cloudflared -ErrorAction SilentlyContinue)) {
    # exits non-zero when there is no config.yml in a default folder, but the service is created anyway
    & $exe service install
    if (-not (Get-Service cloudflared -ErrorAction SilentlyContinue)) { throw "cloudflared service install failed" }
}
# Kill rather than Stop-Service: a service started without --config never answers a stop request (StopPending forever)
$svcPid = (Get-CimInstance Win32_Service -Filter "Name='cloudflared'").ProcessId
if ($svcPid) { Stop-Process -Id $svcPid -Force }
for ($i = 0; $i -lt 30 -and (Get-Service cloudflared).Status -ne 'Stopped'; $i++) { Start-Sleep -Milliseconds 500 }
# Set in the registry: "sc.exe config binPath=" loses the inner quotes when called from PowerShell 5.1
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\cloudflared' ImagePath "`"$exe`" --config `"$config`" tunnel run"
sc.exe config cloudflared start= delayed-auto | Out-Null
sc.exe failure cloudflared reset= 86400 actions= restart/5000/restart/5000/restart/60000 | Out-Null
Start-Service cloudflared
Start-Sleep -Seconds 3
Get-Service cloudflared | Format-Table Name, Status, StartType -AutoSize
(Get-CimInstance Win32_Service -Filter "Name='cloudflared'").PathName
