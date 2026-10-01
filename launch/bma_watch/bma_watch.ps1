# Watches the BMA traffic site (cpudapp.bangkok.go.th/bmatraffic), the source of every BMA camera image and event.
# Every check prints one status line. When the site goes down or comes back, a Windows notification pops up and the
# console beeps. While the site stays down, the notification repeats every -RemindMinutes. Also warns when BMA is back
# but the production server's snapshot cache has not refreshed. Started by bma_watch.cmd; runs until the window is closed.
param(
    [int]$IntervalSeconds = 10,
    [int]$RemindMinutes = 30,
    [int]$StaleMinutes = 60,
    [string]$Base = 'https://cpudapp.bangkok.go.th/bmatraffic/'
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
$CamIds = @('7', '11', '12')        # tried in turn; one good image is enough
$CacheDir = Join-Path $Root 'instances\production\cache\bma_snapshots'
$LogFile = Join-Path $Root 'local\logs\bma_watch.log'

function Write-Log([string]$line) {
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch {}
}

function Show-Toast([string]$title, [string]$body) {
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $esc = [Security.SecurityElement]
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml("<toast scenario='reminder'><visual><binding template='ToastGeneric'><text>$($esc::Escape($title))</text><text>$($esc::Escape($body))</text></binding></visual><actions><action content='OK' arguments='ok' activationType='system'/></actions></toast>")
        $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
    } catch {
        Write-Host "    (notification failed: $($_.Exception.Message))" -ForegroundColor DarkGray
    }
}

function Send-Alert([string]$title, [string]$body, [bool]$bad) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $color = 'Green'
    if ($bad) { $color = 'Red' }
    Write-Host ""
    Write-Host "  >>> $title" -ForegroundColor $color
    Write-Host "      $body" -ForegroundColor $color
    Write-Host ""
    Write-Log "$stamp ALERT $title | $body"
    Show-Toast $title $body
    try {
        if ($bad) { [Console]::Beep(880, 300); [Console]::Beep(660, 300); [Console]::Beep(880, 300) }
        else { [Console]::Beep(660, 200); [Console]::Beep(990, 300) }
    } catch {}
}

# GET that never throws: returns status code (0 = no answer), body bytes and content type.
function Invoke-Get([string]$url, $session, [string]$referer) {
    $headers = @{}
    if ($referer) { $headers['Referer'] = $referer }
    try {
        $r = Invoke-WebRequest -Uri $url -WebSession $session -UserAgent $UA -Headers $headers -UseBasicParsing -TimeoutSec 20
        return @{ Code = [int]$r.StatusCode; Bytes = $r.RawContentLength; Type = [string]$r.Headers['Content-Type']; Text = [string]$r.Content }
    } catch {
        $code = 0
        $resp = $_.Exception.Response
        if ($resp) { $code = [int]$resp.StatusCode }
        return @{ Code = $code; Bytes = 0; Type = ''; Text = $_.Exception.Message }
    }
}

# One full check of the site: the page loads and at least one camera returns a real image.
function Test-Bma {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $page = Invoke-Get "${Base}index.aspx" $session $null
    $ms = $watch.ElapsedMilliseconds
    if ($page.Code -ne 200) {
        $why = "HTTP $($page.Code)"
        if ($page.Code -eq 0) { $why = 'no answer (timeout / network)' }
        return @{ Ok = $false; Detail = "page: $why ($ms ms)" }
    }
    foreach ($id in $CamIds) {
        $play = "${Base}PlayVideo.aspx?ID=$id"
        Invoke-Get $play $session "${Base}index.aspx" | Out-Null
        $ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $img = Invoke-Get "${Base}show.aspx?image=$id&time=$ts" $session $play
        # Under 2500 bytes is BMA's "no image" placeholder, the same rule the server uses
        if ($img.Code -eq 200 -and $img.Bytes -gt 2500 -and $img.Type -like 'image*') {
            return @{ Ok = $true; Detail = "page 200 ($ms ms), camera $id image $([math]::Round($img.Bytes / 1KB)) KB" }
        }
    }
    return @{ Ok = $false; Detail = "page 200 ($ms ms) but no camera image (cameras $($CamIds -join ', '))" }
}

# Minutes since the server last saved a BMA snapshot, or -1 if there is no cache.
function Get-CacheAge {
    if (-not (Test-Path $CacheDir)) { return -1 }
    $newest = Get-ChildItem $CacheDir -Filter *.jpg -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $newest) { return -1 }
    return [int]((Get-Date) - $newest.LastWriteTime).TotalMinutes
}

function Format-Age([int]$min) {
    if ($min -lt 0) { return 'none' }
    if ($min -lt 60) { return "$min min" }
    if ($min -lt 1440) { return "{0} h {1} min" -f [math]::Floor($min / 60), ($min % 60) }
    return "{0} d {1} h" -f [math]::Floor($min / 1440), [math]::Floor(($min % 1440) / 60)
}

Write-Host "======================================================================"
Write-Host "  BMA Watch - $Base"
Write-Host "  check every $IntervalSeconds s | repeat alert every $RemindMinutes min while down"
Write-Host "  log: $LogFile"
Write-Host "  Close this window to stop."
Write-Host "======================================================================"
Write-Host ""

$state = $null          # $true = up, $false = down, $null = first check
$changedAt = Get-Date
$lastAlert = Get-Date
$staleWarned = $false

while ($true) {
    $started = Get-Date
    $res = Test-Bma
    $now = Get-Date
    $age = Get-CacheAge
    $stamp = $now.ToString('yyyy-MM-dd HH:mm:ss')

    if ($res.Ok) { $tag = ' UP ' ; $color = 'Green' } else { $tag = 'DOWN'; $color = 'Red' }
    $since = ''
    if ($null -ne $state -and $state -eq $res.Ok) { $since = " | for $(Format-Age ([int]($now - $changedAt).TotalMinutes))" }
    Write-Host "[$stamp] " -NoNewline
    Write-Host "[$tag]" -ForegroundColor $color -NoNewline
    Write-Host " $($res.Detail)$since | server cache: $(Format-Age $age) old"
    Write-Log "$stamp $tag $($res.Detail) | cache $age min"

    if ($null -eq $state -or $state -ne $res.Ok) {
        if ($null -ne $state) { $changedAt = $now }
        if ($res.Ok) {
            if ($null -eq $state) { Send-Alert 'BMA ใช้งานได้' "เว็บ BMA ปกติ: $($res.Detail)" $false }
            else { Send-Alert 'BMA กลับมาแล้ว' "เว็บ BMA ใช้งานได้อีกครั้ง: $($res.Detail)" $false }
        } else {
            Send-Alert 'BMA ล่ม' "เว็บ BMA ใช้ไม่ได้: $($res.Detail). กล้อง BMA บนเว็บจะเป็นภาพเก่า ($(Format-Age $age))" $true
        }
        $lastAlert = $now
        $staleWarned = $false
        $state = $res.Ok
    } elseif (-not $res.Ok -and ($now - $lastAlert).TotalMinutes -ge $RemindMinutes) {
        Send-Alert 'BMA ยังล่มอยู่' "ล่มมา $(Format-Age ([int]($now - $changedAt).TotalMinutes)): $($res.Detail)" $true
        $lastAlert = $now
    }

    # BMA has been back long enough for a scan cycle, but the server has not saved a new image
    if ($res.Ok -and -not $staleWarned -and $age -ge $StaleMinutes -and ($now - $changedAt).TotalMinutes -ge $StaleMinutes) {
        Send-Alert 'เซิร์ฟเวอร์ไม่อัปเดตภาพ BMA' "BMA ใช้ได้แล้ว แต่ภาพในแคชเก่า $(Format-Age $age). ลองรัน launch\production\restart.bat" $true
        $staleWarned = $true
    }

    # Count the check itself in the interval: a 502 from BMA takes about 10 s to arrive
    $wait = $IntervalSeconds - ((Get-Date) - $started).TotalSeconds
    if ($wait -gt 0) { Start-Sleep -Milliseconds ([int]($wait * 1000)) }
}
