#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIDGE="$SCRIPT_DIR/hid-telephony-bridge.py"
UDEV_RULE="$SCRIPT_DIR/99-hid-telephony-bridge.rules"
SERVICE="$SCRIPT_DIR/hid-telephony-bridge.service"

echo "=== USB HID Telephony Mute Bridge - Installer ==="
echo

# 1. Install the script
echo "[1/4] Installing bridge script → /usr/bin/hid-telephony-bridge (needs sudo)"
sudo install -Dm755 "$BRIDGE" /usr/bin/hid-telephony-bridge

# 2. Install udev rule (needs root)
echo "[2/4] Installing udev rule → /etc/udev/rules.d/"
sudo install -Dm644 "$UDEV_RULE" /etc/udev/rules.d/99-hid-telephony-bridge.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

# 3. Add user to input group if not already
if ! groups | grep -qw input; then
    echo "      Adding $(whoami) to 'input' group (needs sudo)"
    sudo usermod -aG input "$(whoami)"
    echo "      Re-login for group to take effect, or run: newgrp input"
fi

# 4. Install and enable systemd user service
echo "[3/4] Installing systemd user service"
sudo install -Dm644 "$SERVICE" /usr/lib/systemd/user/hid-telephony-bridge.service
systemctl --user daemon-reload

echo "[4/4] Enabling and starting service"
systemctl --user enable --now hid-telephony-bridge.service

echo
echo "=== Done ==="
echo "Check status:  systemctl --user status hid-telephony-bridge"
echo "Watch logs:    journalctl --user -u hid-telephony-bridge -f"
echo "Test:          Press the mute button - desktop mic indicator should toggle"
