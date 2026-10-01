# Called by stop.bat and restart.bat. Closes the console that runs launch\<Folder>\start.bat, start_local.bat or
# restart.bat, so no old window is left waiting at "pause", then anything still listening on the port. The console
# that called this script is left alone (restart.bat goes on to start the new server in it).
# -Folder defaults from the port (8000 production, 8001 test, 5050 enviro), so stopping one server never closes another.
param([int]$Port = 8000, [string]$Folder = '')

if (-not $Folder) {
    $Folder = @{ 8000 = 'production'; 8001 = 'test'; 5050 = 'enviro' }[$Port]
}

$caller = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
$stopped = 0

if ($Folder) {
    Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object { $_.ProcessId -ne $caller -and $_.CommandLine -match "launch\\$Folder\\(re)?start(_local)?\.bat" } |
        ForEach-Object {
            taskkill /F /T /PID $_.ProcessId *> $null
            Write-Host "[*] Closed server window (PID $($_.ProcessId))"
            $stopped++
        }
}

# A server started some other way (e.g. python server.py by hand)
Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -gt 0 } |
    ForEach-Object {
        taskkill /F /T /PID $_.OwningProcess *> $null
        Write-Host "[*] Stopped process on port $Port (PID $($_.OwningProcess))"
        $stopped++
    }

if (-not $stopped) { Write-Host "[*] No server running on port $Port." }
