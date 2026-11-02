# Sets up the AI worker (YOLO on this PC's GPU for the Raspberry Pi, backend\vision\ai_worker.py):
#   - writes AI_WORKER_TOKEN into .env when it has none (the Pi needs the same value in its own .env),
#   - puts the "BKK AI Worker" icon on the Desktop (it runs launch\ai_worker\start.bat).
# With -Remove it deletes the icon only. No administrator rights needed. The token is never printed.
param([switch]$Remove)
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'BKK AI Worker.lnk'
if ($Remove) {
    Remove-Item $link -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed the Desktop icon 'BKK AI Worker'."
    return
}

$envFile = Join-Path $root '.env'
$lines = @()
if (Test-Path $envFile) { $lines = @(Get-Content $envFile -Encoding UTF8) }
$hasToken = $lines | Where-Object { $_ -match '^\s*AI_WORKER_TOKEN\s*=\s*\S' }
if ($hasToken) {
    Write-Host "[OK] .env already has AI_WORKER_TOKEN"
} else {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    $lines = @($lines | Where-Object { $_ -notmatch '^\s*AI_WORKER_TOKEN\s*=' })
    $lines += "# AI worker (:8100): the Pi sends this in X-AI-Token; copy the same line into the Pi's .env"
    $lines += "AI_WORKER_TOKEN=$token"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($envFile, (($lines -join "`n") + "`n"), $utf8)   # keep LF, no BOM
    Write-Host "[OK] token created in .env (AI_WORKER_TOKEN)"
}

$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = Join-Path $PSScriptRoot 'start.bat'
$s.WorkingDirectory = $root
$s.Description = 'BKK AI Worker: YOLO on this PC for the Raspberry Pi (:8100)'
$s.IconLocation = "$env:SystemRoot\System32\imageres.dll,109"
$s.WindowStyle = 7
$s.Save()
Write-Host "[OK] Desktop icon: BKK AI Worker  (stop: launch\ai_worker\stop.bat, log: launch\logs\ai_worker.log)"
