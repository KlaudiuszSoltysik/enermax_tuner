# cooler-driver

Linux userspace driver for USB HID CPU coolers with no native Linux app
(VID `2e3c`, PID `0a12`). Shows CPU temp / GPU temp / fan RPM on the
cooler's display, cycling between them.

## Setup

```bash
sudo apt install lm-sensors          # optional, improves chip detection
sudo sensors-detect --auto           # optional
pip install hidapi psutil

sudo cp 99-cooler.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# unplug/replug the cooler once after this

python3 cooler_driver.py
```

That's it — CPU temp is read via `psutil` (hwmon), falling back to
`sensors -j` and then raw `/sys/class/hwmon` if `psutil` isn't installed.
NVIDIA GPU temp uses `nvidia-smi`. AMD GPU temp reads
`/sys/class/drm/cardN/device/hwmon/*` (untested on real AMD hardware —
please open an issue/PR if it doesn't work for you).

## Notes

- Fan RPM will legitimately read `0` on many AIOs/coolers whose fan/pump
  RPM isn't exposed to the motherboard's hwmon — that's a hardware
  limitation, not a bug in this script.
- To run as a systemd service, create a unit file that runs
  `python3 /path/to/cooler_driver.py` as a user in the appropriate group,
  or run as root if the udev rule doesn't take effect on your distro.
