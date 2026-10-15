"""
Windows notifications for the monitor: one toast per round that had a change worth telling (something went down
or came back). Shown through PowerShell's WinRT toast API, so no extra package is needed.
"""
import os
import subprocess

from monitor_checks import LABELS

BAD = {"fail", "warn", "restart"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
SCRIPT = r"""
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $xml.GetElementsByTagName('text')
$null = $t.Item(0).AppendChild($xml.CreateTextNode($env:MON_TITLE))
$null = $t.Item(1).AppendChild($xml.CreateTextNode($env:MON_BODY))
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:MON_APP).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def worth_telling(e):
    if e["key"].startswith("watchdog:") and e["new"] == "warn":
        return False        # one missed check; the watchdog's restart line follows if it was real
    if e["new"] in BAD:
        return e["old"] != e["new"]
    return e["new"] == "ok" and e["old"] in ("fail", "warn")


def summarize(events):
    told = [e for e in events if worth_telling(e)]
    if not told:
        return None
    bad = [e for e in told if e["new"] in BAD]
    title = f"BKK Monitor: {len(bad)} problem(s)" if bad else "BKK Monitor: back to normal"
    lines = [f"{LABELS.get(e['target'], e['target'])} · {e['name']}: {e['new']}" for e in (bad or told)]
    body = "\n".join(lines[:4]) + (f"\n+{len(lines) - 4} more" if len(lines) > 4 else "")
    return title, body


def toast(title, body):
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
                         env={**os.environ, "MON_TITLE": title, "MON_BODY": body, "MON_APP": APP_ID},
                         creationflags=NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001 - a missed toast must not stop the collector
        pass
