# Keeps the public site up: run every 2 minutes by the "BKK StreetSmart watchdog" scheduled task (install.ps1).
# For production (:8000) and ENVIRO (:5050) it asks the page itself on 127.0.0.1. Two failed checks in a row
# (no answer, or a 5xx) run that server's restart.bat in a new minimized window, which also closes a window left
# at "pause" after a crash. A server stopped on purpose (stop.bat or kill_server.ps1 leaves
# state\stopped_<port>, start.bat removes it) is left alone. Log: state\watchdog.log.
# On 2026-10-03 both servers were found stopped with the public site answering 502, and nobody knew when.
$ErrorActionPreference = 'Continue'
$launch = Split-Path $PSScriptRoot -Parent
$state = Join-Path $PSScriptRoot 'state'
New-Item -ItemType Directory -Force $state | Out-Null
$log = Join-Path $state 'watchdog.log'
$FAILS_TO_RESTART = 2
$GRACE_SECONDS = 300          # after a restart, give the server this long to come up before checking again

function Write-Log($text) {
    Add-Content -Path $log -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $text) -Encoding utf8
}

function Test-Up($port) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 20
        return $r.StatusCode -lt 500
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        return ($code -and $code -lt 500)
    }
}

foreach ($server in @(@{ Port = 8000; Folder = 'production' }, @{ Port = 5050; Folder = 'enviro' })) {
    $port = $server.Port
    if (Test-Path (Join-Path $state "stopped_$port")) { continue }
    $failFile = Join-Path $state "fails_$port"
    $restartFile = Join-Path $state "restarted_$port"
    if ((Test-Path $restartFile) -and ((Get-Date) - (Get-Item $restartFile).LastWriteTime).TotalSeconds -lt $GRACE_SECONDS) {
        continue
    }
    if (Test-Up $port) {
        if (Test-Path $failFile) { Remove-Item $failFile -Force }
        continue
    }
    $fails = 1
    if (Test-Path $failFile) { $fails = [int](Get-Content $failFile -Raw) + 1 }
    if ($fails -lt $FAILS_TO_RESTART) {
        Set-Content -Path $failFile -Value $fails
        Write-Log "$($server.Folder) :$port did not answer (check $fails of $FAILS_TO_RESTART)"
        continue
    }
    Remove-Item $failFile -Force -ErrorAction SilentlyContinue
    Set-Content -Path $restartFile -Value (Get-Date -Format o)
    Write-Log "$($server.Folder) :$port down: running launch\$($server.Folder)\restart.bat"
    Start-Process -FilePath 'cmd.exe' -ArgumentList "/c `"$launch\$($server.Folder)\restart.bat`"" `
        -WorkingDirectory (Split-Path $launch -Parent) -WindowStyle Minimized
}
