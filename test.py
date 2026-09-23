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
