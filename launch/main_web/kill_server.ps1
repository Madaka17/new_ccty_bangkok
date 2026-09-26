# Called by stop.bat and restart.bat. Closes the console that runs launch\main_web\start.bat or restart.bat, so no
# old window is left waiting at "pause", then anything still listening on the port. The console that called this
# script is left alone (restart.bat goes on to start the new server in it).
param([int]$Port = 8000)

$caller = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
$stopped = 0

Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
    Where-Object { $_.ProcessId -ne $caller -and $_.CommandLine -match 'main_web\\(re)?start\.bat' } |
    ForEach-Object {
        taskkill /F /T /PID $_.ProcessId *> $null
        Write-Host "[*] Closed server window (PID $($_.ProcessId))"
        $stopped++
    }

# A server started some other way (e.g. launch\localhost_8000\start.bat)
Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -gt 0 } |
    ForEach-Object {
        taskkill /F /T /PID $_.OwningProcess *> $null
        Write-Host "[*] Stopped process on port $Port (PID $($_.OwningProcess))"
        $stopped++
    }

if (-not $stopped) { Write-Host "[*] No server running on port $Port." }
