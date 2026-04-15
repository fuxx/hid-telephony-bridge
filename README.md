# hid-telephony-bridge

Bridges USB microphone hardware mute buttons to Linux desktops via **USB HID Telephony**. Press the button on the mic, and PipeWire mutes — the GNOME microphone indicator updates, the mute LED on the mic lights up, and apps actually stop receiving audio. Muting from the desktop side (GNOME settings, `pactl`, etc.) syncs back to the LED.

Default device: **Shure MV7+**. Configurable for any USB mic implementing HID Telephony Page (0x0B) via `--vid`/`--pid`.

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

1. Sends **Off-Hook** (Report 0x05) to activate telephony mode
2. Reads **Phone Mute** toggle events (Report 0x04) from the hidraw device
3. Toggles PipeWire source mute via `pactl`
4. Syncs the **Mute LED** (Report 0x06) bidirectionally — button press or desktop mute both update it

The daemon polls PipeWire state every 500ms to catch mute changes from the desktop side.

### Hot-plug support

The daemon handles USB disconnect and reconnect automatically. If the mic is unplugged, it polls for the device with exponential backoff (2s → 30s cap) until it reappears — no manual service restart needed. This is handled entirely in userspace because Linux udev (which detects hardware events) runs as root and cannot directly trigger systemd *user* services.

## Requirements

- Linux with PipeWire (any distro — Arch, Fedora, Ubuntu 22.04+, etc.)
- Python 3.8+ (stdlib only, no pip dependencies)
- `pactl` (from `pipewire-pulse` or `libpulse`)
- A USB microphone with HID Telephony support (tested: Shure MV7+)

## Installation

### Arch Linux (AUR)

```bash
yay -S hid-telephony-bridge
sudo usermod -aG input $USER   # then re-login, or: newgrp input
systemctl --user enable --now hid-telephony-bridge
```

### From source

```bash
git clone https://github.com/fuxx/hid-telephony-bridge.git
cd hid-telephony-bridge
chmod +x install.sh
./install.sh
```

The install script will:
- Install the bridge script to `/usr/bin/` (needs sudo)
- Install a udev rule granting the `input` group access to the hidraw device
- Add your user to the `input` group if needed (re-login or `newgrp input` to apply)
- Install and enable a systemd user service

### Manual setup

If you prefer to set things up yourself:

```bash
# 1. udev rule for hidraw permissions
sudo install -Dm644 99-hid-telephony-bridge.rules /etc/udev/rules.d/99-hid-telephony-bridge.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

# 2. Add yourself to the input group (then re-login, or: newgrp input)
sudo usermod -aG input $USER

# 3. Test it
python3 hid-telephony-bridge.py --verbose

# 4. Install as a systemd user service
sudo install -Dm755 hid-telephony-bridge.py /usr/bin/hid-telephony-bridge
sudo install -Dm644 hid-telephony-bridge.service /usr/lib/systemd/user/hid-telephony-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now hid-telephony-bridge
```

## Usage

Once installed, the service starts automatically with your desktop session (bound to `pipewire-pulse.service`). It will auto-detect the device on any hidraw node.

```bash
# Check status
systemctl --user status hid-telephony-bridge

# Watch logs
journalctl --user -u hid-telephony-bridge -f

# Restart after a config change
systemctl --user restart hid-telephony-bridge
```

### Options

```
hid-telephony-bridge [--vid VID] [--pid PID] [--device /dev/hidrawN] [--auto-offhook] [--verbose]
```

| Flag | Description |
|------|-------------|
| `--vid` | USB Vendor ID in hex (default: `14ed` for Shure) |
| `--pid` | USB Product ID in hex (default: `1019` for MV7+) |
| `--device` | Force a specific hidraw path instead of auto-detecting |
| `--auto-offhook` | Only activate telephony mode when an app is capturing audio (adds ~2s latency) |
| `--verbose` | Debug logging |

To enable auto-offhook mode permanently, use a systemd drop-in:

```bash
systemctl --user edit hid-telephony-bridge.service
```

Then add:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/hid-telephony-bridge --auto-offhook --verbose
```

## Other devices

The daemon should work with any USB microphone that implements HID Telephony Page (0x0B) with the standard report layout (reports 0x04/0x05/0x06). To use it with a different device:

1. **Find your device's USB IDs** — plug in the mic and run:
   ```bash
   lsusb
   ```
   Look for your device in the output. The VID:PID pair is in the `ID` column:
   ```
   Bus 005 Device 005: ID 14ed:1019 Shure Inc Shure MV7+
                           ^^^^:^^^^
                           VID   PID
   ```

2. **Add a udev rule** — duplicate the line in `99-hid-telephony-bridge.rules` with your VID/PID:
   ```
   SUBSYSTEM=="hidraw", ATTRS{idVendor}=="XXXX", ATTRS{idProduct}=="XXXX", MODE="0660", GROUP="input", TAG+="uaccess"
   ```

3. **Override VID/PID** via systemd drop-in:
   ```bash
   systemctl --user edit hid-telephony-bridge.service
   ```
   ```ini
   [Service]
   ExecStart=
   ExecStart=/usr/bin/hid-telephony-bridge --vid XXXX --pid XXXX --verbose
   ```

If your device uses different HID report IDs, please open an issue with the output of:
```bash
sudo usbhid-dump -d XXXX:XXXX -e descriptor
```

## Releasing / AUR publishing

Releases use a two-step process to prevent supply chain attacks — CI builds but never pushes to AUR. Only a local, manually verified push can update the AUR package.

### 1. Tag and push

```bash
git tag v0.1.0
git push origin main --tags
```

This triggers the CI workflow (`.github/workflows/build-package.yml`) which:
- Builds the package in a clean Arch Linux container
- Computes SHA256 checksums of the source tarball, PKGBUILD, and `.SRCINFO`
- Uploads everything as a build artifact (PKGBUILD, .SRCINFO, checksums, .pkg.tar.zst)

### 2. Verify and push to AUR locally

Download `checksums.txt` from the GitHub Actions artifact, then:

```bash
./aur-push.sh v0.1.0
```

The script will:
- Download the source tarball and compute its SHA256 locally
- Compare against the CI checksum — **aborts on mismatch**
- Show the PKGBUILD and .SRCINFO for review
- Ask for confirmation before pushing to the AUR git repo

This ensures the tarball GitHub serves hasn't been tampered with between CI build and AUR publish. No secrets or SSH keys are stored in GitHub.

## Roadmap

This userspace daemon is a working solution, but the proper fix is in the kernel:

1. **HID-BPF program** — a BPF program that handles the Off-Hook handshake in-kernel and emits `KEY_MICMUTE` via the input subsystem. No daemon needed — GNOME, KDE, and other desktops already handle `KEY_MICMUTE` natively. Requires `CONFIG_HID_BPF=y` (available since kernel 6.3, enabled by default on Arch 6.8+).
2. **Upstream kernel support** — the same HID Telephony handshake pattern applies to many USB mics. A generic kernel driver or `hid-input.c` patch could make all of them work out of the box.

## License

GPL-3.0 — see [LICENSE](LICENSE)
