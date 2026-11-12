#!/bin/bash
# Pi hardening: SSH keys only + ufw firewall that lets the home LAN in.
# Run from the PC (Git Bash), as root on the Pi, reading this file from the PC:
#   ssh -i ~/.ssh/bkkpi_ed25519 test@192.168.1.109 sudo bash -s < launch/pi/harden_ssh_firewall.sh
# Safe to run twice. Undo:
#   sudo rm /etc/ssh/sshd_config.d/99-no-password.conf && sudo systemctl reload ssh
#   sudo ufw disable
set -u
LAN="192.168.1.0/24"
DROPIN=/etc/ssh/sshd_config.d/99-no-password.conf

if [ "$(id -u)" != 0 ]; then echo "run with sudo"; exit 1; fi

echo "== 1/2 SSH: keys only"
if ! grep -qiE '^\s*Include\s+/etc/ssh/sshd_config.d/' /etc/ssh/sshd_config; then
    echo "STOP: /etc/ssh/sshd_config does not include sshd_config.d; nothing changed"; exit 1
fi
has_key=no
for f in /home/*/.ssh/authorized_keys /root/.ssh/authorized_keys; do
    [ -s "$f" ] && { has_key=yes; echo "key file: $f"; }
done
if [ "$has_key" != yes ]; then
    echo "STOP: no authorized_keys found; turning off passwords would lock you out"; exit 1
fi
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' > "$DROPIN"
if ! sshd -t; then
    echo "STOP: sshd config test failed; removing $DROPIN"; rm -f "$DROPIN"; exit 1
fi
systemctl reload ssh
sshd -T | grep -Ei '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin) '

echo "== 2/2 firewall (ufw): home LAN in, everything out"
if ! command -v ufw >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y ufw >/dev/null || {
        apt-get update >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y ufw >/dev/null; } || {
        echo "STOP: could not install ufw; SSH step is done"; exit 1; }
fi
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow from "$LAN" comment 'home LAN' >/dev/null
ufw --force enable
ufw status verbose | head -12
echo "== done. Note: ports published by Docker bypass ufw."
