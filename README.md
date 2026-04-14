# mv7-hid-bridge

Bridges the **Shure MV7+** hardware mute button to Linux desktops. Press the button on the mic, and PipeWire mutes — the GNOME microphone indicator updates, the mute LED on the mic lights up, and apps actually stop receiving audio. Muting from the desktop side (GNOME settings, `pactl`, etc.) syncs back to the LED.

## The problem

Many USB microphones with mute buttons — the Shure MV7+, Elgato Wave, Blue Yeti X, and others — implement the **USB HID Telephony Page (0x0B)**. This is the same protocol that Teams, Zoom, and other UC apps use on Windows and macOS to sync call state with headsets and mics.

The protocol requires a **handshake**: the host must send an "Off-Hook" signal before the device will report button events. On Windows, UC apps do this automatically via the Windows Telephony API. On macOS, CoreAudio handles it. **On Linux, nothing implements the host side** — so the mute button silently does nothing.

The mic still works as an audio device. It's just that the mute button, which physically exists and has an LED, is completely ignored by the OS.

## How it works

```
                             Off-Hook ON (report 0x05)
                ┌──────────────────────────────────────────┐
                │                                          ▼
        ┌───────────────┐                          ┌──────────────┐
        │               │   Phone Mute pressed     │              │
        │    Bridge     │◄─────────────────────────│   MV7+ HID   │
        │    daemon     │     (report 0x04)        │   (hidraw)   │
        │               │                          │              │
        │               │   Mute LED sync          │              │
        │               │─────────────────────────►│              │
        └───────┬───────┘     (report 0x06)        └──────────────┘
                │
                │  pactl set-source-mute
                ▼
        ┌───────────────┐
        │   PipeWire    │──► GNOME mic indicator
        │   source      │──► Application audio
        └───────────────┘
```

1. Sends **Off-Hook** (Report 0x05) to activate the MV7+'s telephony mode
2. Reads **Phone Mute** toggle events (Report 0x04) from the hidraw device
3. Toggles PipeWire source mute via `pactl`
4. Syncs the **Mute LED** (Report 0x06) bidirectionally — button press or desktop mute both update it

The daemon polls PipeWire state every 500ms to catch mute changes from the desktop side.

## Requirements

- Linux with PipeWire (any distro — Arch, Fedora, Ubuntu 22.04+, etc.)
- Python 3.8+ (stdlib only, no pip dependencies)
- `pactl` (from `pipewire-pulse` or `libpulse`)
- Shure MV7+ connected via USB

## Installation

```bash
git clone https://github.com/fuxx/mv7-hid-bridge.git
cd mv7-hid-bridge
chmod +x install.sh
./install.sh
```

The install script will:
- Copy the bridge script to `~/.local/bin/`
- Install a udev rule granting the `input` group access to the hidraw device (needs sudo)
- Add your user to the `input` group if needed (needs re-login to take effect)
- Install and enable a systemd user service

### Manual setup

If you prefer to set things up yourself:

```bash
# 1. udev rule for hidraw permissions
sudo cp 99-shure-mv7-hid.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

# 2. Add yourself to the input group (then re-login)
sudo usermod -aG input $USER

# 3. Test it
python3 mv7-hid-bridge.py --verbose

# 4. Install as a systemd user service
cp mv7-hid-bridge.py ~/.local/bin/mv7-hid-bridge
chmod +x ~/.local/bin/mv7-hid-bridge
mkdir -p ~/.config/systemd/user
cp mv7-hid-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mv7-hid-bridge
```

## Usage

Once installed, the service starts automatically with your desktop session (bound to `pipewire-pulse.service`). It will auto-detect the MV7+ on any hidraw device node.

```bash
# Check status
systemctl --user status mv7-hid-bridge

# Watch logs
journalctl --user -u mv7-hid-bridge -f

# Restart after a config change
systemctl --user restart mv7-hid-bridge
```

### Options

```
mv7-hid-bridge [--device /dev/hidrawN] [--auto-offhook] [--verbose]
```

| Flag | Description |
|------|-------------|
| `--device` | Force a specific hidraw path instead of auto-detecting |
| `--auto-offhook` | Only activate telephony mode when an app is capturing audio (adds ~2s latency) |
| `--verbose` | Debug logging |

To enable auto-offhook mode permanently, edit `~/.config/systemd/user/mv7-hid-bridge.service` and add `--auto-offhook` to the `ExecStart` line.

## Roadmap

This userspace daemon is a working solution, but the proper fix is in the kernel. The plan:

1. **HID-BPF program** — a BPF program attached to the MV7+'s VID:PID that handles the Off-Hook handshake in-kernel and emits `KEY_MICMUTE` via the input subsystem. No daemon needed — GNOME, KDE, and other desktops already handle `KEY_MICMUTE` natively. Requires `CONFIG_HID_BPF=y` (available since kernel 6.3, enabled by default on Arch 6.8+).
2. **AUR package** — making the current userspace bridge easy to install on Arch Linux.
3. **Upstream kernel support** — the same HID Telephony handshake pattern applies to many USB mics. A generic kernel driver or `hid-input.c` patch could make all of them work out of the box.

## License

GPL-3.0 — see [LICENSE](LICENSE)
