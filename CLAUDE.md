# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python daemon that bridges USB microphone hardware mute buttons to PipeWire/GNOME on Linux via USB HID Telephony Page (0x0B). Default device is the Shure MV7+; configurable for other HID Telephony mics via `--vid`/`--pid`.

## Running and Testing

```bash
# Manual test (default: Shure MV7+)
python3 hid-telephony-bridge.py --verbose

# With explicit device path
python3 hid-telephony-bridge.py --device /dev/hidrawN --verbose

# With custom USB IDs (for non-MV7+ devices)
python3 hid-telephony-bridge.py --vid 1234 --pid 5678 --verbose

# Auto-offhook mode (only active when an app is capturing audio)
python3 hid-telephony-bridge.py --auto-offhook --verbose

# Install everything (udev rule, systemd service, script to /usr/bin)
./install.sh

# Service management
systemctl --user status hid-telephony-bridge
systemctl --user restart hid-telephony-bridge
journalctl --user -u hid-telephony-bridge -f
```

No build step, no dependencies beyond Python 3.8+ stdlib and `pactl` (from `pipewire-pulse`).

## Architecture

Single-file daemon (`hid-telephony-bridge.py`) with one class:

- **`HIDTelephonyBridge`** — opens the hidraw device, sends the Off-Hook handshake to activate telephony mode, polls for HID input reports, toggles PipeWire source mute via `pactl`, and syncs the mute LED. The main loop uses `select.poll()` on the hidraw fd with a 500ms timeout.
- **`find_hidraw_device(vid, pid)`** — scans `/sys/class/hidraw/hidraw*/device/uevent` for matching VID/PID. The hidraw number is unstable across reboots/replugs.
- **`normalize_usb_id(raw)`** — converts user-supplied VID/PID (e.g. `14ed`, `0x14ED`) to 8-char uppercase zero-padded format for sysfs matching.

Supporting files:
- `99-hid-telephony-bridge.rules` — udev rule (hidraw permissions for `input` group)
- `hid-telephony-bridge.service` — systemd user service (bound to `pipewire-pulse.service`)
- `install.sh` — installs script, udev rule, and service to system paths
- `PKGBUILD` + `hid-telephony-bridge.install` — AUR packaging

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
- Default USB IDs: VID `0x14ED`, PID `0x1019` (Shure MV7+). Configurable via `--vid`/`--pid`.
- Report IDs (0x04/0x05/0x06) are common but device-specific — other mics may differ.
- Python 3.8 compatibility required (`str.removeprefix()` not available).
