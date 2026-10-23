#!/usr/bin/env python3
"""
Native Linux driver for the Lake Shore 240 series temperature monitor.

The 240 presents itself as a Silicon Labs USBXpress device. Lake Shore ships a
Windows-only driver for it, and the device will not answer SCPI queries until it
has been handed a specific sequence of vendor control transfers. Sending the
wrong ones, or sending them to the wrong USB recipient, produces a device that
enumerates cleanly, accepts writes without error, and never replies.

The initialization sequence below was recovered by capturing USB traffic from the
official Windows driver with USBPcap and replaying it byte for byte. The two
things that mattered: every control transfer goes to the *interface*
(bmRequestType 0x41), not the device (0x40), and all seven steps are required.
Omitting any of them leaves the device silent.

See docs/reverse-engineering.md for the full investigation.

Requires: pyusb, libusb-1.0
    sudo apt install -y python3-usb libusb-1.0-0
"""

import time

import usb.core
import usb.util

VENDOR_ID = 0x1FB9
PRODUCT_ID = 0x0205

# Vendor control transfers, captured from the Windows driver.
# bmRequestType 0x41 = host-to-device | vendor | interface recipient.
REQUEST_TYPE_OUT = 0x41

_INIT_SEQUENCE = (
    # (bRequest, wValue, payload, description)
    (0x00, 0x0001, b"", "enable interface"),
    (0x03, 0x0800, b"", "interface configuration"),
    (0x13, 0x0000,
     bytes.fromhex("00000000000000000080000000200000"),
     "line configuration"),
    (0x19, 0x0000, bytes.fromhex("000000001113"), "handshake / modem config"),
    # 0x0001C200 little-endian = 115200 baud
    (0x1E, 0x0000, bytes.fromhex("00c20100"), "set baud rate 115200"),
    (0x07, 0x0200, b"", "purge transmit buffer"),
    (0x07, 0x0100, b"", "purge receive buffer"),
)

EP_OUT = 0x01
EP_IN = 0x81

DEFAULT_TIMEOUT_MS = 1000


class LakeShore240Error(RuntimeError):
    """Raised when the device cannot be opened or does not respond."""


class LakeShore240:
    """Talks ASCII SCPI to a Lake Shore 240 over raw USB bulk endpoints.

    Typical use:

        ls = LakeShore240()
        print(ls.idn())
        print(ls.kelvin(1), "K")
        ls.close()

    Every USB call carries a timeout, so a stalled endpoint raises rather than
    hanging the process. If a run does end badly, unplug and replug the 240
    before the next attempt — a stalled endpoint needs a device power cycle to
    clear, not just a script restart.
    """

    def __init__(self, vendor_id=VENDOR_ID, product_id=PRODUCT_ID,
                 timeout_ms=DEFAULT_TIMEOUT_MS, reset=True):
        self.timeout_ms = timeout_ms
        self._dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
        if self._dev is None:
            raise LakeShore240Error(
                f"No device with VID 0x{vendor_id:04X} PID 0x{product_id:04X}. "
                "Check the cable, then `lsusb`. If it is listed but this still "
                "fails, you likely need the udev rule from the README or sudo."
            )

        # The kernel's generic CDC driver may have claimed the interface.
        try:
            if self._dev.is_kernel_driver_active(0):
                self._dev.detach_kernel_driver(0)
        except (NotImplementedError, usb.core.USBError):
            pass  # not all platforms implement this; not fatal if it fails

        if reset:
            # Clears state left behind by a previous crashed run.
            try:
                self._dev.reset()
                time.sleep(0.1)
            except usb.core.USBError:
                pass

        self._dev.set_configuration()
        self._initialize()

    def _initialize(self):
        """Replay the captured USBXpress handshake.

        Each step is required and the order is the order the Windows driver
        used. A failure here is worth reporting loudly, because the symptom
        otherwise is a device that accepts commands and never answers.
        """
        for request, value, payload, description in _INIT_SEQUENCE:
            try:
                self._dev.ctrl_transfer(
                    REQUEST_TYPE_OUT, request, value, 0, payload,
                    timeout=self.timeout_ms,
                )
            except usb.core.USBError as exc:
                raise LakeShore240Error(
                    f"USBXpress init failed at step '{description}' "
                    f"(bRequest=0x{request:02X}, wValue=0x{value:04X}): {exc}"
                ) from exc
        self._drain()

    def _drain(self):
        """Empty the IN endpoint so a stale reply cannot be mistaken for a new one.

        Reads until the device stops producing data. A timeout here is the
        expected exit, not an error.
        """
        while True:
            try:
                data = self._dev.read(EP_IN, 64, timeout=50)
                if not data:
                    return
            except usb.core.USBError:
                return

    def query(self, command, timeout_ms=None):
        """Send a SCPI command and return its reply as a stripped string.

        Commands go out terminated with \\n; replies come back terminated with
        \\r\\n. Returns None if the device does not answer within the timeout,
        which usually means the handshake did not take.
        """
        timeout = timeout_ms or self.timeout_ms
        self._dev.write(EP_OUT, (command.strip() + "\n").encode("ascii"),
                        timeout=timeout)

        chunks = bytearray()
        deadline = time.time() + timeout / 1000.0
        while time.time() < deadline:
            try:
                chunks.extend(self._dev.read(EP_IN, 64, timeout=timeout))
            except usb.core.USBError:
                break
            if chunks.endswith(b"\r\n"):
                break

        text = chunks.decode("ascii", errors="replace").strip()
        return text or None

    def idn(self):
        """Identification string, e.g. 'LSCI,MODEL240-8P,...'."""
        return self.query("*IDN?")

    def kelvin(self, channel=1):
        """Temperature in Kelvin for one input channel, or None if no reading."""
        return self._query_float(f"KRDG? {int(channel)}")

    def ohms(self, channel=1):
        """Raw sensor resistance in ohms, or None if no reading.

        Worth logging alongside the temperature: resistance is what the
        instrument actually measures, and a resistance that looks sane while the
        temperature does not means the wrong sensor curve is loaded.
        """
        return self._query_float(f"SRDG? {int(channel)}")

    def _query_float(self, command):
        response = self.query(command)
        if response is None:
            return None
        try:
            return float(response.split(",")[0])
        except ValueError:
            return None

    def close(self):
        """Release the USB interface. Safe to call more than once."""
        if getattr(self, "_dev", None) is not None:
            usb.util.dispose_resources(self._dev)
            self._dev = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


if __name__ == "__main__":
    with LakeShore240() as instrument:
        print(instrument.idn())
        for ch in (1, 2):
            k = instrument.kelvin(ch)
            r = instrument.ohms(ch)
            if k is None:
                print(f"  channel {ch}: no reading")
            else:
                print(f"  channel {ch}: {k:8.3f} K   {k - 273.15:8.2f} C   {r:9.3f} ohm")
