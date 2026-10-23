#!/usr/bin/env python3
"""
Print the temperature from one Lake Shore 240 channel on a fixed interval.

Logs resistance alongside temperature on purpose. Resistance is the instrument's
actual measurement; Kelvin is that resistance pushed through whichever sensor
curve is loaded. If the ohms look reasonable and the Kelvin does not, the curve
is wrong, not the wiring.

    python3 poll_temperature.py
    python3 poll_temperature.py --channel 2 --interval 5 --csv run.csv
"""

import argparse
import csv
import sys
import time
from datetime import datetime

sys.path.insert(0, "..")
from lakeshore240 import LakeShore240


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", type=int, default=1)
    ap.add_argument("--interval", type=float, default=10.0, help="seconds")
    ap.add_argument("--csv", help="also append readings to this file")
    args = ap.parse_args()

    writer = None
    handle = None
    if args.csv:
        handle = open(args.csv, "a", newline="")
        writer = csv.writer(handle)
        if handle.tell() == 0:
            writer.writerow(["timestamp", "channel", "kelvin", "celsius", "ohms"])

    print(f"Polling channel {args.channel} every {args.interval}s. Ctrl-C to stop.\n")
    try:
        with LakeShore240() as ls:
            print(ls.idn() or "<no identification response>", "\n")
            while True:
                k = ls.kelvin(args.channel)
                r = ls.ohms(args.channel)
                stamp = datetime.now()

                if k is None:
                    print(f"{stamp:%H:%M:%S}   <no reading on channel {args.channel}>")
                else:
                    print(f"{stamp:%H:%M:%S}   {k:8.3f} K   {k - 273.15:8.2f} C   "
                          f"{r:9.3f} ohm")
                    if writer:
                        writer.writerow([stamp.isoformat(), args.channel,
                                         f"{k:.4f}", f"{k - 273.15:.4f}", f"{r:.4f}"])
                        handle.flush()

                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if handle:
            handle.close()


if __name__ == "__main__":
    main()
