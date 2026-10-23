# Troubleshooting

## The device is not found

```
LakeShore240Error: No device with VID 0x1FB9 PID 0x0205
```

Check `lsusb` first. If it is not listed, it is a cable or power problem, not a
software one.

If it is listed but the driver still cannot open it, you need either the udev
rule from the README or `sudo`. Permissions on `/dev/bus/usb/...` default to
root-only.

## Pipe error / endpoint stall on every run after a crash

A script that dies mid-transfer leaves the endpoint stalled. Restarting the
script does not clear it. **Unplug the instrument and plug it back in.**

The driver calls `usb.reset()` when it opens, which recovers most cases, but a
hard stall needs device power to cycle.

## It opens and initializes, but every query returns None

The handshake completed but the device is not in command-response mode. In
practice this has meant one of:

- A stale reply sitting in the IN buffer from a previous session. The driver
  drains the endpoint after init; if you have modified that path, check it still
  does.
- The kernel's CDC driver reclaimed the interface between init and query. Confirm
  `detach_kernel_driver` is still being called.
- A genuinely different USBXpress variant. Capture the Windows traffic for your
  specific unit and compare against the table in the README.

## Kelvin reads nonsense but ohms look fine

The sensor curve loaded in the instrument does not match the sensor attached. The
240 converts resistance to temperature internally using whichever curve is
assigned to that channel, and it will happily apply a Cernox curve to a PT100.

Check the curve assignment on the instrument front panel. This is why both
examples log resistance next to temperature.

## Readings are correct but stop updating

The 240 updates its own channels on an internal cycle. Polling faster than that
returns the same value repeatedly, which looks like a frozen reading. Slow the
poll interval before suspecting the driver.
