#!/usr/bin/env python3
"""
Diagnostic tool: dumps raw HID input reports coming FROM the cooler.

Many of these display coolers measure fan RPM themselves and report it
back to the host over HID (that's how the Windows app shows it) rather
than exposing it to the motherboard's fan headers. If that's the case
here, the RPM value will show up as changing bytes in this dump.

Usage:
    python3 hid_sniffer.py

Then, while it's running:
    - Note the "baseline" bytes.
    - Change fan speed (BIOS fan curve, or briefly slow the fan with a
      finger - carefully) and see which byte position changes value in
      a way that correlates with RPM (e.g. goes from ~0x2C to ~0x1A as
      RPM increases, or read as a 16-bit value across two bytes).
    - If NOTHING changes at all when RPM changes, the device likely
      doesn't report RPM back over HID either, and the Windows app may
      be reading it from a different source (e.g. a fan splitter/hub
      with its own controller chip, a separate HID device/interface, or
      polling a different USB endpoint). Run `lsusb -v` and check if the
      cooler exposes multiple HID interfaces - try opening each.
"""

import sys
import time

import hid

VENDOR_ID = 0x2E3C
PRODUCT_ID = 0x0A12


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def main():
    print(f"Looking for {VENDOR_ID:04x}:{PRODUCT_ID:04x} ...")
    for info in hid.enumerate(VENDOR_ID, PRODUCT_ID):
        print(
            f"  interface {info['interface_number']}: "
            f"usage_page={info.get('usage_page')} usage={info.get('usage')} "
            f"path={info['path']}"
        )

    device = hid.device()
    device.open(VENDOR_ID, PRODUCT_ID)
    device.set_nonblocking(1)
    print("\nOpened device. Listening for input reports (Ctrl+C to stop)...\n")

    last = None
    try:
        while True:
            data = device.read(65, timeout_ms=200)
            if data:
                b = bytes(data)
                if b != last:
                    print(f"{time.strftime('%H:%M:%S')}  {hexdump(b)}")
                    last = b
            else:
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        device.close()


if __name__ == "__main__":
    sys.exit(main())
