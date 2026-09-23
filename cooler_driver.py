#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import struct
import subprocess
import time

import hid

try:
    import psutil
except ImportError:
    psutil = None

VENDOR_ID = 0x2E3C
PRODUCT_ID = 0x0A12

MODE_BLANK = 0x00
MODE_CPU = 0x01
MODE_GPU = 0x04
MODE_RPM = 0x10

FLAG_CELSIUS = 0x00
FLAG_FAHRENHEIT = 0x01


_CPU_CHIP_HINTS = ("k10temp", "zenpower", "coretemp", "cpu_thermal", "cpu-thermal")
_CPU_LABEL_HINTS = ("tctl", "tdie", "package id 0", "core 0", "cpu")


def _cpu_temp_psutil() -> int | None:
    if psutil is None:
        return None
    try:
        temps = psutil.sensors_temperatures()
    except Exception:  # noqa: BLE001
        return None
    if not temps:
        return None

    for chip in _CPU_CHIP_HINTS:
        for chip_name, entries in temps.items():
            if chip not in chip_name.lower():
                continue
            for e in entries:
                if e.label and e.label.lower() in (
                    "tctl",
                    "tdie",
                    "package id 0",
                    "core 0",
                ):
                    return round(e.current)
            if entries:
                return round(entries[0].current)

    for chip_name, entries in temps.items():
        for e in entries:
            label = (e.label or "").lower()
            if any(h in label for h in _CPU_LABEL_HINTS) or any(
                h in chip_name.lower() for h in _CPU_CHIP_HINTS
            ):
                return round(e.current)

    return None


def _cpu_temp_sensors_json() -> int | None:
    try:
        output = subprocess.check_output(["sensors", "-j"], text=True, timeout=1.5)
        data = json.loads(output)
    except Exception:  # noqa: BLE001
        return None

    for chip, features in data.items():
        if not any(h in chip.lower() for h in _CPU_CHIP_HINTS):
            continue
        for feat_name, vals in features.items():
            if not isinstance(vals, dict):
                continue
            label = feat_name.lower()
            for key, val in vals.items():
                if (
                    key.endswith("_input")
                    and isinstance(val, (int, float))
                    and any(
                        h in label for h in ("tctl", "tdie", "package id 0", "core 0")
                    )
                ):
                    return round(val)

    for chip, features in data.items():
        if not any(h in chip.lower() for h in _CPU_CHIP_HINTS):
            continue
        for feat_name, vals in features.items():
            if not isinstance(vals, dict):
                continue
            for key, val in vals.items():
                if key.endswith("_input") and isinstance(val, (int, float)):
                    return round(val)
    return None


def _cpu_temp_hwmon_sysfs() -> int | None:
    try:
        for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
            name_path = f"{hwmon}/name"
            try:
                with open(name_path) as f:
                    name = f.read().strip().lower()
            except OSError:
                continue
            if not any(h in name for h in _CPU_CHIP_HINTS):
                continue
            for temp_input in sorted(glob.glob(f"{hwmon}/temp*_input")):
                label_path = temp_input.replace("_input", "_label")
                label = ""
                if os.path.exists(label_path):
                    with open(label_path) as f:
                        label = f.read().strip().lower()
                try:
                    with open(temp_input) as f:
                        milli = int(f.read().strip())
                except (OSError, ValueError):
                    continue
                if (
                    any(h in label for h in ("tctl", "tdie", "package id 0", "core 0"))
                    or not label
                ):
                    return round(milli / 1000)
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def get_cpu_temp() -> int:
    for fn in (_cpu_temp_psutil, _cpu_temp_sensors_json, _cpu_temp_hwmon_sysfs):
        result = fn()
        if result is not None:
            return result
    print("Failed to read CPU temperature from any source")
    return 0


def _fan_rpm_psutil() -> int | None:
    if psutil is None:
        return None
    try:
        fans = psutil.sensors_fans()
    except Exception:  # noqa: BLE001
        return None
    for entries in fans.values():
        for e in entries:
            if e.current and e.current > 0:
                return int(e.current)
    return None


def _fan_rpm_sensors_json() -> int | None:
    try:
        output = subprocess.check_output(["sensors", "-j"], text=True, timeout=1.5)
        data = json.loads(output)
    except Exception:  # noqa: BLE001
        return None
    for features in data.values():
        for feat_name, vals in features.items():
            if not isinstance(vals, dict):
                continue
            for key, val in vals.items():
                if (
                    key.endswith("_input")
                    and "fan" in feat_name.lower()
                    and isinstance(val, (int, float))
                    and val > 0
                ):
                    return int(val)
    return None


def _fan_rpm_hwmon_sysfs() -> int | None:
    try:
        for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
            for fan_input in sorted(glob.glob(f"{hwmon}/fan*_input")):
                try:
                    with open(fan_input) as f:
                        rpm = int(f.read().strip())
                except (OSError, ValueError):
                    continue
                if rpm > 0:
                    return rpm
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def get_fan_rpm() -> int:
    for fn in (_fan_rpm_psutil, _fan_rpm_sensors_json, _fan_rpm_hwmon_sysfs):
        result = fn()
        if result is not None:
            return result
    # Not necessarily a failure - many CPU fans (esp. AIO pump/fan combos
    # controlled by the cooler itself) simply don't expose an RPM sensor
    # to the motherboard/hwmon. This is expected on some setups.
    return 0


def _gpu_temp_nvidia() -> int | None:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            text=True,
            timeout=1.5,
        )
        return int(output.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def _gpu_temp_amd() -> int | None:
    try:
        for hwmon in glob.glob("/sys/class/drm/card*/device/hwmon/hwmon*"):
            name_path = f"{hwmon}/name"
            try:
                with open(name_path) as f:
                    name = f.read().strip().lower()
            except OSError:
                continue
            if "amdgpu" not in name:
                continue

            best = None
            for temp_input in sorted(glob.glob(f"{hwmon}/temp*_input")):
                label_path = temp_input.replace("_input", "_label")
                label = ""
                if os.path.exists(label_path):
                    with open(label_path) as f:
                        label = f.read().strip().lower()
                try:
                    with open(temp_input) as f:
                        milli = int(f.read().strip())
                except (OSError, ValueError):
                    continue
                if label == "junction":
                    return round(milli / 1000)
                if best is None:
                    best = round(milli / 1000)
            if best is not None:
                return best
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def get_gpu_temp() -> int:
    for fn in (_gpu_temp_nvidia, _gpu_temp_amd):
        result = fn()
        if result is not None:
            return result
    return 0


def update_cooler_display(
    device,
    display_mode: int,
    cpu_temp: int,
    gpu_temp: int,
    rpm: int,
    is_fahrenheit: bool = False,
):
    payload = [0x00] * 65
    payload[0] = 0x20
    payload[1] = display_mode
    payload[2] = FLAG_FAHRENHEIT if is_fahrenheit else FLAG_CELSIUS
    payload[6] = max(0, min(cpu_temp, 255))
    payload[9] = max(0, min(gpu_temp, 255))

    rpm_bytes = struct.pack(">H", max(0, min(rpm, 65535)))
    payload[11] = rpm_bytes[0]
    payload[12] = rpm_bytes[1]

    try:
        device.write(payload)
    except Exception as e:  # noqa: BLE001
        print(f"Failed to write payload: {e}")


def main(
    mode_switch_interval: float = 3.0,
    show_metrics: list[str] | None = None,
    cpu_override: int | None = None,
    gpu_override: int | None = None,
    rpm_override: int | None = None,
    is_fahrenheit: bool = False,
):
    if not show_metrics:
        show_metrics = ["cpu", "gpu", "fan"]

    mode_mapping = {"cpu": MODE_CPU, "gpu": MODE_GPU, "fan": MODE_RPM, "rpm": MODE_RPM}
    cycle_modes = [
        mode_mapping[m.lower()] for m in show_metrics if m.lower() in mode_mapping
    ]
    if not cycle_modes:
        cycle_modes = [MODE_CPU]

    cooler = None
    try:
        cooler = hid.device()
        cooler.open(VENDOR_ID, PRODUCT_ID)
        cooler.set_nonblocking(1)

        cycle_index = 0
        last_switch = time.time()
        current_mode = cycle_modes[cycle_index]

        while True:
            cpu_t = cpu_override if cpu_override is not None else get_cpu_temp()
            gpu_t = gpu_override if gpu_override is not None else get_gpu_temp()
            fan_rpm = rpm_override if rpm_override is not None else get_fan_rpm()

            now = time.time()
            if now - last_switch >= mode_switch_interval:
                cycle_index = (cycle_index + 1) % len(cycle_modes)
                current_mode = cycle_modes[cycle_index]
                last_switch = now

            update_cooler_display(
                device=cooler,
                display_mode=current_mode,
                cpu_temp=cpu_t,
                gpu_temp=gpu_t,
                rpm=fan_rpm,
                is_fahrenheit=is_fahrenheit,
            )
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nShutting down driver...")
        if cooler is not None:
            update_cooler_display(cooler, MODE_BLANK, 0, 0, 0)
    except Exception as e:  # noqa: BLE001
        print(f"Hardware Error: {e}")
    finally:
        if cooler is not None:
            cooler.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="USB HID display driver for ETS-TD60 Digital ARGB CPU Air Cooler."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
        metavar="SECONDS",
        help="how long to show each metric before cycling to the next (default: 3.0)",
    )
    parser.add_argument(
        "--metrics",
        type=str,
        default="cpu,gpu,fan",
        metavar="LIST",
        help="comma-separated metrics to cycle through: cpu,gpu,fan (default: cpu,gpu,fan)",
    )
    parser.add_argument(
        "--fahrenheit",
        action="store_true",
        help="display temperatures in Fahrenheit instead of Celsius",
    )
    parser.add_argument(
        "--cpu-override",
        type=int,
        default=None,
        metavar="DEGREES",
        help="show this fixed value instead of the real CPU temp (for testing)",
    )
    parser.add_argument(
        "--gpu-override",
        type=int,
        default=None,
        metavar="DEGREES",
        help="show this fixed value instead of the real GPU temp (for testing)",
    )
    parser.add_argument(
        "--rpm-override",
        type=int,
        default=None,
        metavar="RPM",
        help="show this fixed value instead of the real fan RPM (for testing)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        mode_switch_interval=args.interval,
        show_metrics=[m.strip() for m in args.metrics.split(",") if m.strip()],
        is_fahrenheit=args.fahrenheit,
    )
