#!/usr/bin/env python3
"""
mv7-hid-bridge - HID Telephony bridge for Shure MV7+ on Linux/PipeWire

Bridges the MV7+'s USB HID Telephony mute button to PipeWire source mute,
enabling native GNOME microphone indicator and proper mute state sync.

The MV7+ implements USB HID Telephony Page (0x0B):
  - Report 0x04 IN:  Phone Mute (bit 1, relative) + Hook Switch (bit 0)
  - Report 0x05 OUT: Off-Hook LED (bit 0) - activates telephony mode
  - Report 0x06 OUT: Mute LED (bit 0) - host-controlled mute indicator

The device only sends Report 0x04 events AFTER the host sends Off-Hook ON.
This is the standard HID Telephony handshake (Windows Teams/Zoom do this
automatically via the Unified Communications API; Linux has no equivalent).

Modes:
  always (default): Off-Hook is set on startup. Mute button always works.
  auto-offhook:     Off-Hook only when a PipeWire capture stream is active
                    (i.e., an app is using the microphone). More correct but
                    adds ~2s latency before the button becomes responsive.

Usage:
  mv7-hid-bridge [--auto-offhook] [--device /dev/hidrawN]
"""

import argparse
import glob
import logging
import os
import select
import signal
import subprocess
import sys
import time

# HID Report constants 
REPORT_TELEPHONY_IN  = 0x04
REPORT_OFFHOOK_OUT   = 0x05
REPORT_MUTELED_OUT   = 0x06

MUTE_BIT  = 1  # bit index in Report 0x04 data byte
HOOK_BIT  = 0

# USB IDs for Shure MV7+ 
USB_VID = "000014ED"
USB_PID = "00001019"

# Logging 
log = logging.getLogger("mv7-hid-bridge")


def find_hidraw_device():
    """Auto-detect the MV7+ hidraw device via sysfs."""
    for entry in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent_path = os.path.join(entry, "device", "uevent")
            with open(uevent_path) as f:
                uevent = f.read()
            if USB_VID in uevent and USB_PID in uevent:
                devnode = "/dev/" + os.path.basename(entry)
                log.debug("Found MV7+ at %s", devnode)
                return devnode
        except (OSError, IOError):
            continue
    return None


def send_hid_report(fd, report_id, data_byte):
    """Write a 2-byte output report to hidraw."""
    try:
        os.write(fd, bytes([report_id, data_byte]))
    except OSError as e:
        log.error("HID write failed (report 0x%02x): %s", report_id, e)
        raise


def pactl(*args):
    """Run pactl with correct PipeWire/PulseAudio env."""
    env = os.environ.copy()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    try:
        result = subprocess.run(
            ["pactl", *args],
            capture_output=True, text=True, timeout=5, env=env,
        )
        if result.returncode != 0 and result.stderr.strip():
            log.warning("pactl %s: %s", " ".join(args), result.stderr.strip())
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.error("pactl timed out: %s", " ".join(args))
        return ""
    except FileNotFoundError:
        log.error("pactl not found - is PipeWire/pulseaudio-utils installed?")
        return ""


def get_source_mute():
    """Read current mute state of the default PipeWire source."""
    out = pactl("get-source-mute", "@DEFAULT_SOURCE@")
    return "yes" in out.lower()


def set_source_mute(muted):
    """Set mute state on the default PipeWire source."""
    pactl("set-source-mute", "@DEFAULT_SOURCE@", "1" if muted else "0")


def has_active_capture_streams():
    """Check whether any app is currently capturing audio."""
    out = pactl("list", "source-outputs", "short")
    lines = [l for l in out.splitlines() if l.strip()]
    return len(lines) > 0


class MV7Bridge:
    """
    Main bridge: HID Telephony - PipeWire mute state.

    Lifecycle:
      1. open()       - open hidraw device
      2. run()        - blocking main loop (handles signals)
      3. close()      - clean up, send Off-Hook OFF

    The bridge toggles PipeWire source mute on each Report 0x04 press
    event and keeps the MV7+ Mute LED in sync with the actual state.
    """

    def __init__(self, device=None, auto_offhook=False):
        self.device_path = device
        self.auto_offhook = auto_offhook
        self._fd = None
        self._poll = None
        self._running = False
        self._offhook = False
        self._muted = False

    # -- Device I/O ---------------------------------------------------

    def open(self):
        path = self.device_path or find_hidraw_device()
        if not path:
            raise RuntimeError(
                "Shure MV7+ hidraw device not found. "
                "Is the mic connected? Check /dev/hidraw* permissions."
            )
        self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self._poll = select.poll()
        self._poll.register(self._fd, select.POLLIN)
        self.device_path = path
        log.info("Opened %s", path)

    def close(self):
        if self._fd is not None:
            if self._offhook:
                self._set_offhook(False)
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        log.info("Device closed")

    # -- HID Telephony control ----------------------------------------

    def _set_offhook(self, active):
        """Send Off-Hook LED report. Activates/deactivates telephony mode."""
        send_hid_report(self._fd, REPORT_OFFHOOK_OUT, 0x01 if active else 0x00)
        self._offhook = active
        if not active:
            self._set_mute_led(False)
        log.info("Off-Hook %s", "ON" if active else "OFF")

    def _set_mute_led(self, on):
        """Control the MV7+ mute indicator LED."""
        send_hid_report(self._fd, REPORT_MUTELED_OUT, 0x01 if on else 0x00)

    def _sync_mute_state(self, muted):
        """Propagate mute state to PipeWire and MV7+ LED."""
        self._muted = muted
        set_source_mute(muted)
        self._set_mute_led(muted)
        log.info("Mute %s", "ON" if muted else "OFF")

    # -- Report parsing -----------------------------------------------

    def _handle_report(self, data):
        if len(data) < 2:
            return
        report_id = data[0]

        if report_id == REPORT_TELEPHONY_IN:
            mute_pressed = (data[1] >> MUTE_BIT) & 1
            # Phone Mute usage is Relative - each press is a toggle event.
            # We get 0x02 on press and 0x00 on release; act only on press.
            if mute_pressed:
                self._sync_mute_state(not self._muted)

    # -- Main loop ----------------------------------------------------

    def run(self):
        self.open()
        self._running = True

        def _stop(signum, frame):
            log.info("Caught signal %d, shutting down", signum)
            self._running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        # Activate telephony mode
        if not self.auto_offhook:
            self._set_offhook(True)
            # Sync initial mute state from PipeWire
            self._muted = get_source_mute()
            self._set_mute_led(self._muted)
            log.info("Initial mute state: %s", "ON" if self._muted else "OFF")
        else:
            log.info("Auto off-hook mode - waiting for capture streams")

        last_stream_check = 0.0
        stream_check_interval = 2.0  # seconds

        while self._running:
            # -- Auto off-hook: monitor capture streams -----------
            if self.auto_offhook:
                now = time.monotonic()
                if now - last_stream_check >= stream_check_interval:
                    last_stream_check = now
                    streams_active = has_active_capture_streams()
                    if streams_active and not self._offhook:
                        self._set_offhook(True)
                        self._muted = get_source_mute()
                        self._set_mute_led(self._muted)
                    elif not streams_active and self._offhook:
                        self._set_offhook(False)
                        self._muted = False

            # -- Poll hidraw for incoming reports -----------------
            try:
                events = self._poll.poll(500)  # 500ms timeout
            except InterruptedError:
                continue

            for fd_no, event in events:
                if event & select.POLLIN:
                    try:
                        data = os.read(self._fd, 64)
                        if data:
                            self._handle_report(data)
                    except BlockingIOError:
                        pass
                if event & (select.POLLERR | select.POLLHUP):
                    log.error("Device disconnected")
                    self._running = False

            # -- Sync LED if mute changed externally (e.g. GNOME) --
            if self._offhook:
                pw_muted = get_source_mute()
                if pw_muted != self._muted:
                    self._muted = pw_muted
                    self._set_mute_led(pw_muted)
                    log.info("External mute change detected: %s",
                             "ON" if pw_muted else "OFF")

        self.close()

    def stop(self):
        self._running = False


def main():
    parser = argparse.ArgumentParser(
        description="HID Telephony bridge for Shure MV7+ on Linux/PipeWire",
    )
    parser.add_argument(
        "-d", "--device",
        help="hidraw device path (auto-detected if omitted)",
    )
    parser.add_argument(
        "-a", "--auto-offhook",
        action="store_true",
        help="Activate telephony only when an app is capturing audio",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s: %(message)s",
    )

    bridge = MV7Bridge(device=args.device, auto_offhook=args.auto_offhook)
    try:
        bridge.run()
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(1)
    except Exception:
        log.exception("Unexpected error")
        bridge.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
