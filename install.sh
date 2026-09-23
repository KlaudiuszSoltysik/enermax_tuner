#!/usr/bin/env bash
# Installs cooler-driver as a systemd service that starts at boot.
# - Creates an isolated venv in /opt/cooler-driver (doesn't touch system python)
# - Installs a udev rule so the service can talk to the USB device as a
#   normal (non-root) user
# - Runs as the user who invoked this script, not as root
#
# Usage:
#   sudo ./install.sh                      # default metrics: cpu,gpu,fan
#   sudo ./install.sh --interval 5 --metrics cpu,fan
#
# Uninstall:
#   sudo systemctl disable --now cooler-driver
#   sudo rm /etc/systemd/system/cooler-driver.service
#   sudo rm /etc/udev/rules.d/99-cooler.rules
#   sudo rm -rf /opt/cooler-driver

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this with sudo (it needs to write to /opt, /etc/udev, /etc/systemd)." >&2
    exit 1
fi

RUN_AS_USER="${SUDO_USER:-$USER}"
INSTALL_DIR="/opt/cooler-driver"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRA_ARGS=("$@")

echo "==> Installing to $INSTALL_DIR (service will run as user: $RUN_AS_USER)"
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/cooler_driver.py" "$INSTALL_DIR/"

echo "==> Creating isolated venv"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet hidapi psutil

echo "==> Installing udev rule (lets non-root users access the device)"
cp "$SCRIPT_DIR/99-cooler.rules" /etc/udev/rules.d/99-cooler.rules
udevadm control --reload-rules
udevadm trigger

echo "==> Installing systemd service"
EXEC_ARGS="${EXTRA_ARGS[*]:-}"
cat > /etc/systemd/system/cooler-driver.service <<EOF
[Unit]
Description=ETS-TD60 cooler display driver
After=multi-user.target

[Service]
Type=simple
User=${RUN_AS_USER}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/cooler_driver.py ${EXEC_ARGS}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cooler-driver

echo "==> Done. Status:"
systemctl --no-pager status cooler-driver || true
echo
echo "Logs:   journalctl -u cooler-driver -f"
echo "Change options later: edit ExecStart in /etc/systemd/system/cooler-driver.service,"
echo "then: sudo systemctl daemon-reload && sudo systemctl restart cooler-driver"