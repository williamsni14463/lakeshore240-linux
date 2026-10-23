# Working out the USBXpress handshake

The README has the answer. This is how I got there, including the parts that did
not work, because the dead ends are most of what made the problem hard.

---

## The symptom

The Raspberry Pi found the device immediately:

```
VID: 0x1FB9
PID: 0x0205
```

PyUSB enumerated it, located the bulk endpoints, and accepted writes without
complaint. Then nothing came back:

- `*IDN?` — no response
- `KRDG? 1` — no response
- `SRDG? 1` — no response

This is the worst shape a bug can take. Every layer I could inspect reported
success. The device was plainly there, the transfers plainly completed, and there
was no error anywhere to follow. USB communication was working at the transport
level; the instrument simply never entered its command-response mode.

---

## Attempt 1 — guessing from documentation

The first implementation assembled an initialization sequence out of commonly
documented USBXpress control transfers:

- interface enable
- endpoint reset
- endpoint flush
- alternate configuration attempts
- multiple line terminators (`\r\n`, `\n`, `\r`)
- timeout protection on every USB call
- endpoint stall recovery

This made the code safe to run repeatedly. It did not produce a single reply.

---

## Attempt 2 — making failure survivable

Before trying to be clever I made the failures cheap. A hardened implementation
(`usbx2.py`) added:

- a timeout on every USB call, so nothing could block longer than about a second
- `usb_reset()` before the handshake, clearing state left by a prior crashed run
- wrappers around every transfer so a stall printed a message instead of freezing
- endpoint draining before each query
- automatic retry across candidate terminators
- a hard overall time budget with a guaranteed clean exit

Still no SCPI responses, but this was the turning point even though it produced
no data. It ruled out "the code is hanging" and "the endpoint is stalled,"
which left exactly one hypothesis: **the handshake itself is wrong.**

Worth saying plainly — the instinct is to keep adding candidate transfers and
hope one lands. The search space is far too large for that. Narrowing the
hypothesis was more valuable than expanding the attempts.

---

## Attempt 3 — capturing what actually works

Instead of guessing what the device wanted, I watched something that already
knew. I ran the official Lake Shore Windows software against the same unit and
captured the USB traffic with [USBPcap](https://desowin.org/usbpcap/), then
compared that capture against what my Linux code was sending.

Two differences, both silent.

### The wrong recipient

Mine:

```
bmRequestType = 0x40    # host-to-device | vendor | DEVICE recipient
```

Windows:

```
bmRequestType = 0x41    # host-to-device | vendor | INTERFACE recipient
```

One bit. Control transfers aimed at the device rather than the interface
completed without a USB-level error and never reached the USBXpress interface
that was supposed to act on them. Nothing in the API surface distinguishes "the
transfer succeeded" from "the transfer succeeded and the right thing received
it."

### Four missing steps

The Windows driver also performed vendor-specific configuration I had left out
entirely:

- interface configuration
- line configuration
- modem / handshake configuration
- baud rate (115200)
- transmit buffer purge
- receive buffer purge

Replayed exactly, in order, with the captured payloads, communication worked on
the first attempt.

---

## The sequence

All with `bmRequestType = 0x41`:

| Step | bRequest | wValue | Payload | Purpose |
|---|---|---|---|---|
| 1 | `0x00` | `0x0001` | — | Enable interface |
| 2 | `0x03` | `0x0800` | — | Interface configuration |
| 3 | `0x13` | `0x0000` | `00000000000000000080000000200000` | Line configuration |
| 4 | `0x19` | `0x0000` | `000000001113` | Handshake / modem configuration |
| 5 | `0x1E` | `0x0000` | `00c20100` | Set baud rate 115200 |
| 6 | `0x07` | `0x0200` | — | Purge transmit buffer |
| 7 | `0x07` | `0x0100` | — | Purge receive buffer |

Step 5 is a useful check on whether the capture was read correctly rather than
pattern-matched: `00c20100` interpreted little-endian is `0x0001C200`, which is
115200 exactly. A payload that decodes to a number you expected is a good sign
you understand what you are looking at.

Steps 3 and 4 I cannot decode the same way. They are byte sequences that work.
Changing line settings rather than accepting the captured defaults would mean
going to Silicon Labs' USBXpress documentation for the field layout.

After the handshake the protocol is ordinary ASCII SCPI: commands out on
endpoint `0x01` terminated with `\n`, replies in on `0x81` terminated with
`\r\n`.

---

## What I would do differently

**Capture first.** Four hours went into guessing at control transfers. The
capture took under an hour and gave the answer directly. When a device has a
working driver on another platform, that driver is ground truth and reading it
is faster than reinventing it.

**Separate "it did not error" from "it worked."** The 0x40 versus 0x41 bug
survived as long as it did because every call returned success. Any time a device
accepts everything and answers nothing, suspect the requests are going somewhere
that is not listening.

---

## Applying this to other instruments

Plenty of lab hardware ships Windows-only USBXpress drivers. The method
generalises:

1. Confirm the device enumerates on Linux and note VID/PID from `lsusb`.
2. Run the vendor's Windows software against it with USBPcap capturing.
3. Filter the capture to control transfers on that device, in the first second
   after the software opens the connection.
4. Replay them in order with PyUSB, matching `bmRequestType` exactly.
5. Only then start sending the instrument's own command set.

The payloads will differ. The shape of the problem will not.
