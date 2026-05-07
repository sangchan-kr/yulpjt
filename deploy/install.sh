#!/bin/sh
# Install kiosk autostart on a fresh Pi.
# Run as the target user (e.g. yul). Assumes labwc + autologin desktop.
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$HOME/.config/systemd/user"
cp "$PROJECT_DIR/deploy/control-system.service" "$HOME/.config/systemd/user/control-system.service"

mkdir -p "$HOME/.config/labwc"
cp "$PROJECT_DIR/deploy/labwc-autostart" "$HOME/.config/labwc/autostart"
chmod +x "$HOME/.config/labwc/autostart"

systemctl --user daemon-reload
echo "Installed. Reboot to verify, or run:"
echo "  systemctl --user start control-system.service"
