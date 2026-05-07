# Setup Log — 2026-05-07

Initial bring-up of the yulpjt industrial control HMI on Raspberry Pi 5.
Hardware (Waveshare 7" LCD) connected; ADAM modules and HX711 not yet wired.

## Hardware

| Component | Model | Connection |
|---|---|---|
| SBC | Raspberry Pi 5 (2GB) | — |
| Display | Waveshare 7" HDMI LCD (H), 1024×600, capacitive touch | micro-HDMI + USB (touch) + 5V/2A external power |
| RS-485 converter | Advantech ADAM-4561 | USB → `/dev/ttyUSB0` (planned) |
| Digital input | Advantech ADAM-4055 (16ch isolated DI) | RS-485 bus, Modbus RTU planned |
| Relay output | Advantech ADAM-4068 (8ch relay) | RS-485 bus, Modbus RTU planned |
| Load cell ADC | HX711 + load cell | GPIO bit-bang (planned) |

## OS

- Raspberry Pi OS 64-bit (Debian 13 trixie, kernel 6.12)
- Hostname: `yulpjt`
- Compositor: labwc (Wayland), seat0 autologin as `yul`

### cloud-init disabled

Pi Imager's new setup uses cloud-init nocloud, which re-applied `hostname: rasberrypi-local` from `/boot/firmware/user-data` on every boot. Disabled by:

```sh
sudo touch /etc/cloud/cloud-init.disabled
sudo systemctl mask cloud-init.service cloud-init-local.service cloud-config.service cloud-final.service
sudo sed -i 's| ds=nocloud[^ ]*||g' /boot/firmware/cmdline.txt   # backed up to .bak
sudo raspi-config nonint do_hostname yulpjt
```

## Network

- **Pi internet**: Wi-Fi (`wlan0`) connected to corporate SSID `TOMO-BIZ`, IP `172.16.2.x`.
- **Pi management/SSH from PC**: PC↔Pi direct ethernet cable + Windows Internet Connection Sharing on PC. Pi's `eth0` gets `192.168.137.140` from ICS DHCP.
- **Default route stays on Wi-Fi**: netplan `90-NM-…yaml` for eth0 has `passthrough.ipv4.never-default: true`. Without this, ICS captured the default route and broke internet.
- **Corporate network quirk**: `TOMO-BIZ` blocks subnet-to-subnet (PC `172.16.3.x` cannot SSH directly to Pi `172.16.2.x`). The ICS direct cable is the SSH path.
- SSH alias on PC (`~/.ssh/config`): `Host yulpjt → 192.168.137.140` with key auth (`id_ed25519`).

## Python environment

`python3 -m venv .venv` at `~/control-system/.venv`, then via pip:

- `PySide6==6.8.*` (with `Essentials`, `Addons`)
- `gpiozero` + `lgpio` (Pi 5's only working GPIO backend)
- `rpi-lgpio` — `RPi.GPIO` API shim that proxies to `lgpio`. Needed because `hx711-multi` imports `RPi.GPIO`, which itself doesn't work on Pi 5.
- `pymodbus>=3.7,<4` + `pyserial`
- `hx711-multi`
- `pyyaml`

System-side packages installed via `apt`: `git build-essential pkg-config python3-pip python3-venv python3-dev python3-lgpio libgpiod-dev i2c-tools libxcb-cursor0 libxkbcommon-x11-0 libgl1 swig liblgpio-dev qt6-wayland`.

## Project layout

```
~/control-system/
├── deploy/
│   ├── control-system.service     # systemd user service
│   ├── labwc-autostart            # labwc hook that starts the service
│   └── install.sh                 # one-line installer for a new Pi
├── pyproject.toml                 # editable install target
├── requirements.txt
├── src/control_system/
│   ├── __init__.py
│   ├── __main__.py                # `python -m control_system` entry
│   ├── main.py                    # QApplication + showFullScreen
│   ├── config.py                  # MOCK_HW env flag + serial/GPIO config
│   ├── core/                      # (placeholder — state/controller TBD)
│   ├── hardware/
│   │   ├── loadcell.py            # HX711 wrapper (mock; real impl TBD)
│   │   ├── adam_di.py             # ADAM-4055 DI (mock; real impl TBD)
│   │   └── adam_relay.py          # ADAM-4068 DO (mock; real impl TBD)
│   └── ui/
│       └── main_window.py         # full-screen kiosk window
└── tests/
```

## Mock hardware design

Each hardware class takes `mock: bool` in its constructor:

- `mock=True` → returns synthetic data (sinusoid for load cell, randomized DI toggles, in-memory relay state)
- `mock=False` → currently `raise NotImplementedError`; real driver to be added when hardware arrives

Mode is selected by `Config.mock_hardware`, which reads `MOCK_HW` env var (default `1`). To run against real hardware later, launch with `MOCK_HW=0`.

## Kiosk mode

- `main.py` calls `window.showFullScreen()`.
- `MainWindow` calls `setCursor(QCursor(Qt.BlankCursor))` to hide the pointer.
- `keyPressEvent` exits on Esc (development convenience).
- Relay buttons get `setMinimumHeight(60)` for finger-sized touch targets.

### Autostart (systemd user service + labwc hook)

`~/.config/systemd/user/control-system.service` defines the unit (Restart=on-failure, RestartSec=3, env vars for Wayland).

`graphical-session.target` is **not** active on this labwc session, so the service is not enabled by systemd directly. Instead, `~/.config/labwc/autostart` runs at compositor start:

```sh
systemctl --user import-environment WAYLAND_DISPLAY XDG_RUNTIME_DIR
systemctl --user start control-system.service
```

Verified: after a fresh `sudo reboot`, the app reaches "active (running)" within ~20 seconds.

To install on a new Pi (assumes labwc + autologin):

```sh
~/control-system/deploy/install.sh
sudo reboot
```

## Common commands

```sh
# Manage the kiosk service
systemctl --user status control-system.service
systemctl --user restart control-system.service
systemctl --user stop control-system.service
journalctl --user -u control-system.service -f

# Run the app manually (in a logged-in Wayland session)
cd ~/control-system && source .venv/bin/activate
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) \
QT_QPA_PLATFORM=wayland python -m control_system

# Headless smoke test (no display required)
QT_QPA_PLATFORM=offscreen timeout 3 python -m control_system; echo exit=$?
```

## Open items (next sessions)

- **ADAM Modbus RTU client** — pymodbus-based driver to replace the mock for `AdamDigitalInput` / `AdamRelay`. Requires modules to be flashed to Modbus RTU mode via Adam/Apax utility on Windows first.
- **HX711 driver** — write a small lgpio-based bit-bang driver, drop the `hx711-multi` + `rpi-lgpio` dependency.
- **Calibration flow** — tare + scale factor for the load cell, persisted to disk.
- **Unit tests** — pytest harness over the mock modules.
- **UI polish** — Korean labels, alarm pane, larger typography, dark theme.
- **Screen blanking off** — labwc/wlroots DPMS configuration for 24/7 displays.
- **Sudoers `NOPASSWD` for `reboot`/`systemctl`** — to allow remote restart automation without interactive password.
- **Industrial-grade considerations** — hardware watchdog (`dtparam=watchdog=on`), read-only rootfs or industrial SD card, hardwired E-stop separate from the Pi.
