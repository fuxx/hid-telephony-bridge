#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIDGE="$SCRIPT_DIR/mv7-hid-bridge.py"
UDEV_RULE="$SCRIPT_DIR/99-shure-mv7-hid.rules"
SERVICE="$SCRIPT_DIR/mv7-hid-bridge.service"

echo "=== Shure MV7+ HID Telephony Bridge - Installer ==="
echo

# 1. Install the script
echo "[1/4] Installing bridge script → ~/.local/bin/mv7-hid-bridge"
mkdir -p ~/.local/bin
cp "$BRIDGE" ~/.local/bin/mv7-hid-bridge
chmod +x ~/.local/bin/mv7-hid-bridge

# 2. Install udev rule (needs root)
echo "[2/4] Installing udev rule → /etc/udev/rules.d/ (needs sudo)"
sudo cp "$UDEV_RULE" /etc/udev/rules.d/99-shure-mv7-hid.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

# 3. Add user to input group if not already
if ! groups | grep -qw input; then
    echo "[2b]  Adding $(whoami) to 'input' group (needs sudo, re-login required)"
    sudo usermod -aG input "$(whoami)"
    echo "       ⚠ You must log out and back in for group membership to take effect."
    echo "       After re-login, run: install.sh  (it will skip this step)"
fi

# 4. Install and enable systemd user service
echo "[3/4] Installing systemd user service"
mkdir -p ~/.config/systemd/user
cp "$SERVICE" ~/.config/systemd/user/mv7-hid-bridge.service
systemctl --user daemon-reload

echo "[4/4] Enabling and starting service"
systemctl --user enable --now mv7-hid-bridge.service

echo
echo "=== Done ==="
echo "Check status:  systemctl --user status mv7-hid-bridge"
echo "Watch logs:    journalctl --user -u mv7-hid-bridge -f"
echo "Test:          Press the MV7+ mute button - GNOME mic indicator should toggle"
