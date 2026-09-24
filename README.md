# cooler-driver

Linux userspace driver for ETS-TD60 Digital ARGB CPU Air Cooler.

## Setup

1. `git clone <this repo>` and `cd` into it
2. `sudo apt install lm-sensors` (optional, improves chip detection)
3. `sudo sensors-detect --auto` (optional)
4. `sudo ./install.sh` — installs into an isolated venv under `/opt/cooler-driver`,
   sets up the udev rule, and starts a systemd service that runs at boot

That's it — the driver is now running as a background service under your
user account (no root needed at runtime, only during install).

Want different options (interval, which metrics to cycle, °F)? Pass them
to the installer, they get baked into the service:

```
sudo ./install.sh --interval 5 --metrics cpu,fan --fahrenheit
```

### Manual run (no service, for testing)

```
pip install hidapi psutil
python3 cooler_driver.py --interval 5 --metrics cpu,gpu,fan
```

### Available options

| Flag             | Default       | Description                                                 |
| ---------------- | ------------- | ----------------------------------------------------------- |
| `--interval`     | `3.0`         | Seconds to show each metric before cycling to the next      |
| `--metrics`      | `cpu,gpu,fan` | Comma-separated list of metrics to cycle through            |
| `--fahrenheit`   | off           | Display temperatures in °F instead of °C                    |
| `--cpu-override` | none          | Show a fixed CPU temp instead of the real reading (testing) |
| `--gpu-override` | none          | Show a fixed GPU temp instead of the real reading (testing) |
| `--rpm-override` | none          | Show a fixed fan RPM instead of the real reading (testing)  |

Same table applies whether you run the script directly or pass the flags
to `install.sh` (they get baked into the systemd service's `ExecStart`).

## How temp/RPM are read

CPU temp is read via `psutil` (hwmon), falling back to `sensors -j` and
then raw `/sys/class/hwmon` if `psutil` isn't installed. NVIDIA GPU temp
uses `nvidia-smi`. AMD GPU temp reads `/sys/class/drm/cardN/device/hwmon/*`
(untested on real AMD hardware — please open an issue/PR if it doesn't
work for you).

## Notes

- Fan RPM currently always reports `0`. This cooler appears to measure
  RPM itself and report it back over HID rather than exposing it to the
  motherboard's fan headers, so the usual OS sensor sources never see
  it — this needs the HID protocol reverse-engineered before it can be
  added (see `hid_sniffer.py`, contributions welcome).
- To change options after install: edit `ExecStart` in
  `/etc/systemd/system/cooler-driver.service`, then
  `sudo systemctl daemon-reload && sudo systemctl restart cooler-driver`.
- To uninstall:
  ```
  sudo systemctl disable --now cooler-driver
  sudo rm /etc/systemd/system/cooler-driver.service
  sudo rm /etc/udev/rules.d/99-cooler.rules
  sudo rm -rf /opt/cooler-driver
  ```
