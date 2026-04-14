# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python daemon that bridges the Shure MV7+ USB microphone's hardware mute button to PipeWire/GNOME on Linux. The MV7+ uses USB HID Telephony Page (0x0B) — the same protocol Windows Teams/Zoom handle natively. Linux has no host-side implementation, so this daemon performs the handshake and syncs mute state.

## Running and Testing

```bash
# Manual test (after udev rule is installed)
python3 mv7-hid-bridge.py --verbose

# With explicit device path
python3 mv7-hid-bridge.py --device /dev/hidrawN --verbose

# Auto-offhook mode (only active when an app is capturing audio)
python3 mv7-hid-bridge.py --auto-offhook --verbose

# Install everything (udev rule, systemd service, script to ~/.local/bin)
./install.sh

# Service management
systemctl --user status mv7-hid-bridge
systemctl --user restart mv7-hid-bridge
journalctl --user -u mv7-hid-bridge -f
```

No build step, no dependencies beyond Python 3.8+ stdlib and `pactl` (from `pipewire-pulse`).

## Architecture

Single-file daemon (`mv7-hid-bridge.py`) with one class:

- **`MV7Bridge`** — opens the hidraw device, sends the Off-Hook handshake to activate telephony mode, polls for HID input reports, toggles PipeWire source mute via `pactl`, and syncs the MV7+ mute LED. The main loop uses `select.poll()` on the hidraw fd with a 500ms timeout.
- **Auto-detect** — `find_hidraw_device()` scans `/sys/class/hidraw/hidraw*/device/uevent` for VID `000014ED` / PID `00001019`. The hidraw number is unstable across reboots/replugs.

Supporting files: udev rule (hidraw permissions for `input` group), systemd user service (bound to `pipewire-pulse.service`), and an install script.

## HID Telephony Protocol

| Report | Direction | Purpose |
|--------|-----------|---------|
| 0x04 | Input | Bit 0: Hook Switch (abs), Bit 1: Phone Mute (rel) |
| 0x05 | Output | Bit 0: Off-Hook LED — must send ON before device emits 0x04 |
| 0x06 | Output | Bit 0: Mute LED — host-controlled indicator |

Phone Mute is **Relative**: sends `0x02` on press, `0x00` on release. Act only on press (toggle).

## Key Constraints

- **PipeWire commands must run as the session user**, never root (root gets "Host is down"). The daemon sets `XDG_RUNTIME_DIR` if missing.
- The MV7+ has an internal ALSA-level mute (`Microphone Capture Switch`) that is independent of the HID Telephony mute. This daemon operates at the PipeWire level only.
- USB IDs: VID `0x14ED`, PID `0x1019`.
- `CLAUDE-CLI-HANDOFF.md` contains the full diagnostic history, decoded HID report descriptor, and PipeWire node details.
