#!/usr/bin/env python3
"""
Drive an Industrial Shields Raspberry Pi PLC digital output from a Lake Shore 240
reading, with hysteresis.

    temperature above TRIP_C   -> output TRUE
    temperature below RESET_C  -> output FALSE

The gap between the two thresholds is what stops the output chattering when the
temperature sits right on the boundary and the reading dithers by a few
hundredths of a degree. Two degrees is generous for a Cernox but costs nothing.

Warming the sensor with your fingers is enough to trip it on the bench, which is
the quickest way to confirm the whole chain works before anything is cold.

Needs librpiplc from Industrial Shields. Ctrl-C leaves the output OFF.
"""

import sys
import time
from datetime import datetime

sys.path.insert(0, "..")
from lakeshore240 import LakeShore240

CHANNEL = 1
OUTPUT_PIN = "Q0.0"      # digital output terminal on the PLC
TRIP_C = 30.0            # output goes TRUE above this
RESET_C = 28.0           # output goes FALSE below this
POLL_S = 1.0

PLC_VERSION = "RPIPLC_V6"      # board hardware revision, from the unit label
PLC_MODEL = "RPIPLC_57AAR"     # the trailing "+" on the label is not part of this


def open_plc():
    """Return an initialized librpiplc handle, or None to run in dry-run mode."""
    try:
        from librpiplc import rpiplc
    except ImportError:
        print("librpiplc not installed — running without touching hardware.\n")
        return None

    rpiplc.init(PLC_VERSION, PLC_MODEL)
    rpiplc.pin_mode(OUTPUT_PIN, rpiplc.OUTPUT)
    return rpiplc


def main():
    plc = open_plc()
    state = False

    def set_output(value):
        if plc is not None:
            plc.digital_write(OUTPUT_PIN, plc.HIGH if value else plc.LOW)

    print(f"Channel {CHANNEL}: TRUE above {TRIP_C} C, FALSE below {RESET_C} C.")
    print("Ctrl-C to stop.\n")

    try:
        with LakeShore240() as ls:
            while True:
                k = ls.kelvin(CHANNEL)
                if k is None:
                    print(f"{datetime.now():%H:%M:%S}   <no reading>")
                    time.sleep(POLL_S)
                    continue

                c = k - 273.15
                if not state and c > TRIP_C:
                    state = True
                    set_output(True)
                    print(f"{datetime.now():%H:%M:%S}   {c:7.2f} C   -> OUTPUT ON")
                elif state and c < RESET_C:
                    state = False
                    set_output(False)
                    print(f"{datetime.now():%H:%M:%S}   {c:7.2f} C   -> OUTPUT OFF")
                else:
                    print(f"{datetime.now():%H:%M:%S}   {c:7.2f} C   "
                          f"[{'ON' if state else 'OFF'}]", end="\r")

                time.sleep(POLL_S)
    except KeyboardInterrupt:
        print("\nStopping, leaving the output OFF.")
    finally:
        set_output(False)


if __name__ == "__main__":
    main()
