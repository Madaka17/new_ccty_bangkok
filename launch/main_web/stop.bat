@echo off
title BKK StreetSmart - Stop Public Access
echo [*] Turning off Tailscale Funnel ...
tailscale funnel reset
tailscale funnel status
echo [OK] Public access closed. Server itself keeps running if its window is still open.
pause
