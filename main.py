import re
import struct
import subprocess
import time

import hid

VENDOR_ID = 0x2E3C
PRODUCT_ID = 0x0A12

MODE_BLANK = 0x00
MODE_CPU = 0x01
MODE_GPU = 0x04
MODE_RPM = 0x10

FLAG_CELSIUS = 0x00
FLAG_FAHRENHEIT = 0x01


def get_cpu_temp() -> int:
    """Reads CPU temperature by parsing 'sensors' output (lm-sensors)."""
    try:
        output = subprocess.check_output(["sensors"], text=True, timeout=1.0)
        for line in output.splitlines():
            # Look for common CPU temperature identifiers in sensors output
            line_lower = line.lower()
            if any(
                keyword in line_lower
                for keyword in ["package id", "core 0", "tdie", "cpu temp"]
            ):
                match = re.search(r"\+?([0-9]+\.[0-9]+)°C", line)
                if match:
                    return int(float(match.group(1)))
    except Exception as e:
        print(f"Failed to read CPU temperature from sensors: {e}")

    return 0


def get_gpu_temp() -> int:
    """Reads GPU temperature via nvidia-smi."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            text=True,
            timeout=1.0,
        )
        return int(output.strip())
    except Exception as e:
        print(f"Failed to read GPU temperature: {e}")

    return 0


def get_fan_rpm() -> int:
    """Reads fan RPM by parsing 'sensors' output (lm-sensors)."""
    try:
        output = subprocess.check_output(["sensors"], text=True, timeout=1.0)
        for line in output.splitlines():
            if "fan" in line.lower() or "rpm" in line.lower():
                match = re.search(r"(\d+)\s*RPM", line, re.IGNORECASE)
                if match:
                    rpm = int(match.group(1))
                    if rpm > 0:
                        return rpm
    except Exception as e:
        print(f"Failed to read fan speed from sensors: {e}")

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

    if is_fahrenheit:
        payload[2] = FLAG_FAHRENHEIT
    else:
        payload[2] = FLAG_CELSIUS

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
    if show_metrics is None or show_metrics == []:
        show_metrics = ["cpu", "gpu", "fan"]

    mode_mapping = {
        "cpu": MODE_CPU,
        "gpu": MODE_GPU,
        "fan": MODE_RPM,
        "rpm": MODE_RPM,
    }

    cycle_modes = []
    for metric in show_metrics:
        metric_lower = metric.lower()
        if metric_lower in mode_mapping:
            cycle_modes.append(mode_mapping[metric_lower])

    cooler = None

    try:
        cooler = hid.device()
        cooler.open(VENDOR_ID, PRODUCT_ID)
        cooler.set_nonblocking(1)

        cycle_index = 0
        last_mode_switch_time = time.time()
        current_mode = cycle_modes[cycle_index]

        while True:
            cpu_t = cpu_override if cpu_override is not None else get_cpu_temp()
            gpu_t = gpu_override if gpu_override is not None else get_gpu_temp()
            fan_rpm = rpm_override if rpm_override is not None else get_fan_rpm()

            current_time = time.time()

            if current_time - last_mode_switch_time >= mode_switch_interval:
                cycle_index = (cycle_index + 1) % len(cycle_modes)
                current_mode = cycle_modes[cycle_index]
                last_mode_switch_time = current_time

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


if __name__ == "__main__":
    main(
        mode_switch_interval=0.5,
        show_metrics=[],
        is_fahrenheit=False,
    )
