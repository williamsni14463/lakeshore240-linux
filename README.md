# Lake Shore 240 — Native Linux Driver

Reads a Lake Shore 240 series temperature monitor directly over USB from Linux,
with no Windows machine, no vendor driver, and no USBXpress runtime.

```python
from lakeshore240 import LakeShore240

with LakeShore240() as ls:
    print(ls.idn())              # LSCI,MODEL240-8P,...
    print(ls.kelvin(1), "K")     # 77.351 K
    print(ls.ohms(1), "ohm")     # raw sensor resistance
```

---

## Why this exists

The 240 is a Silicon Labs USBXpress device. Lake Shore supports it on Windows
only, and the Linux side is not a matter of finding the right serial port — the
device will not answer a single SCPI query until it has been handed a specific
sequence of vendor control transfers.

Before that handshake the failure mode is unhelpful. The device enumerates. PyUSB
finds the endpoints. Writes complete without error. `*IDN?` returns nothing.
Everything at the USB transport layer looks healthy and no data ever comes back.

I needed temperature from a 240-8P inside a Raspberry Pi PLC running Linux, for
cryogenic controls on MAMBA at Fermilab, so the driver had to exist.

---

## How it was worked out

Guessing at control transfers did not converge. What did work was capturing the
USB traffic from the official Windows driver with [USBPcap](https://desowin.org/usbpcap/)
while it talked to the same unit, then diffing that against what my code was
sending.

Two things were wrong, and both were silent failures:

**The requests went to the wrong recipient.** I was sending `bmRequestType =
0x40`, which targets the USB *device*. The Windows driver uses `0x41`, which
targets the *interface*. The transfers completed without a USB error either way;
they just never reached the USBXpress interface that was supposed to act on them.

**Four of the seven steps were missing.** Line configuration, modem/handshake
configuration, baud rate, and the two buffer purges had all been omitted.

Replaying the full sequence in the captured order made it work on the first try.

| Step | bRequest | wValue | Payload | Purpose |
|---|---|---|---|---|
| 1 | `0x00` | `0x0001` | — | Enable interface |
| 2 | `0x03` | `0x0800` | — | Interface configuration |
| 3 | `0x13` | `0x0000` | `00000000000000000080000000200000` | Line configuration |
| 4 | `0x19` | `0x0000` | `000000001113` | Handshake / modem config |
| 5 | `0x1E` | `0x0000` | `00c20100` | Baud rate 115200 |
| 6 | `0x07` | `0x0200` | — | Purge transmit buffer |
| 7 | `0x07` | `0x0100` | — | Purge receive buffer |

All seven with `bmRequestType = 0x41`. Step 5's payload is `0x0001C200`
little-endian, which is 115200 — a useful confirmation that the capture was read
correctly rather than pattern-matched.

After that the protocol is ordinary ASCII SCPI over the bulk endpoints: commands
out on `0x01` terminated with `\n`, replies in on `0x81` terminated with `\r\n`.

The full investigation, including the two dead ends, is in
[docs/reverse-engineering.md](docs/reverse-engineering.md).

---

## Install

```bash
sudo apt install -y python3-usb libusb-1.0-0
git clone https://github.com/williamsni14463/lakeshore240-linux
cd lakeshore240-linux
```

To run without `sudo`, add a udev rule:

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1fb9", ATTR{idProduct}=="0205", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-lakeshore240.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Unplug and replug the instrument afterwards.

---

## API

| Call | Returns |
|---|---|
| `idn()` | Identification string |
| `kelvin(channel=1)` | Temperature in Kelvin, or `None` if the channel has no reading |
| `ohms(channel=1)` | Raw sensor resistance in ohms, or `None` |
| `query(command)` | Raw reply to any SCPI command |
| `close()` | Release the USB interface |

Also works as a context manager, which is the safer habit — a released interface
is one less thing to power-cycle.

Log `ohms()` alongside `kelvin()`. Resistance is what the instrument actually
measures; temperature is resistance pushed through a calibration curve. A
plausible resistance with an implausible temperature means the wrong curve is
loaded, and that is a failure you will otherwise chase for an afternoon.

---

## Examples

- [`examples/poll_temperature.py`](examples/poll_temperature.py) — print Kelvin,
  Celsius and ohms on an interval
- [`examples/threshold_to_plc.py`](examples/threshold_to_plc.py) — drive an
  Industrial Shields RPi PLC digital output when temperature crosses a threshold,
  with hysteresis

---

## Known rough edges

**A crashed run leaves a stalled endpoint.** If a script dies mid-transfer, the
next run will fail with a pipe error. Unplug and replug the 240 — a stalled
endpoint clears on device power cycle, not on script restart. The driver calls
`usb.reset()` on open, which handles most cases but not all.

**Tested on one model.** This was developed against a 240-8P on Raspberry Pi OS
Bookworm (64-bit) and Debian. The 240-2P uses the same USBXpress interface and
should work unchanged, but I have not had one to confirm it. Other Lake Shore
instruments using USBXpress may well need the same handshake with different
payloads; the capture method in the docs is the way to find out.

**The init payloads are replayed, not understood.** Steps 3 and 4 are byte
sequences lifted from a capture. I know what they accomplish, not what every
field means. If you need to change line settings rather than accept the
captured defaults, you will need Silicon Labs' USBXpress documentation.

---

## Context

Built for the MAMBA / MMBC rapid cycling bubble chamber prototype at Fermilab,
where a Cernox CX-1080 on a Lake Shore 240-8P had to feed temperature into a
Raspberry Pi PLC. The surrounding cryogenic instrumentation work is in
[cryo-rtd-readout](https://github.com/williamsni14463/cryo-rtd-readout), and the
PLC itself in
[raspberry-pi-plc-benchmarks](https://github.com/williamsni14463/raspberry-pi-plc-benchmarks).
