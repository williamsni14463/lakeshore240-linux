#!/usr/bin/env python3
"""
temp_coil.py — MAMBA bench proof-of-concept.
Reads the Cernox (Lake Shore 240) and drives a PLC digital output ("coil") TRUE
when temperature crosses the threshold. Real sensor input -> real PLC output.

  temp > TRIP_C   -> coil TRUE   (warm the sensor with your fingers)
  temp < RESET_C  -> coil FALSE  (2 C hysteresis so it doesn't chatter)

Needs ls240_driver.py in the same folder. Ctrl-C stops and leaves the coil OFF.
"""

import time
from datetime import datetime
from ls240_driver import LakeShore240

# ===== config =====
CHANNEL   = 1
COIL_PIN  = "Q0.0"      # <-- set to the digital output you wired (or a relay)
TRIP_C    = 30.0        # coil goes TRUE above this
RESET_C   = 28.0        # coil goes FALSE below this (hysteresis)
POLL_S    = 1.0
PLC_VER   = "RPIPLC_V6"
PLC_MODEL = "RPIPLC_57AAR"
# ==================


def open_plc():
    from rpiplc_lib import rpiplc
    try:
        rpiplc.init(PLC_VER, PLC_MODEL)
    except TypeError:
        rpiplc.init()
    rpiplc.pin_mode(COIL_PIN, rpiplc.OUTPUT)
    rpiplc.digital_write(COIL_PIN, rpiplc.LOW)
    return rpiplc


def main():
    ls = LakeShore240()
    plc = open_plc()
    coil = False
    print(f"MAMBA bench test — coil {COIL_PIN}: TRUE >{TRIP_C}C, FALSE <{RESET_C}C")
    print(f"{'time':>8}  {'K':>8}  {'C':>7}   coil")
    print("-" * 34)
    try:
        while True:
            k = ls.kelvin(CHANNEL)
            if k is not None:
                c = k - 273.15
                # threshold logic with hysteresis
                if not coil and c > TRIP_C:
                    coil = True
                    plc.digital_write(COIL_PIN, plc.HIGH)
                elif coil and c < RESET_C:
                    coil = False
                    plc.digital_write(COIL_PIN, plc.LOW)
                stamp = datetime.now().strftime("%H:%M:%S")
                print(f"{stamp}  {k:8.3f}  {c:7.2f}   {'TRUE ' if coil else 'false'}")
            else:
                print("  <no reading>")
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            plc.digital_write(COIL_PIN, plc.LOW)  # leave output safe/off
        except Exception:
            pass
        ls.close()
        print("\nstopped — coil set FALSE")


if __name__ == "__main__":
    main()