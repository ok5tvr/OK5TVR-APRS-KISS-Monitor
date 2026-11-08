#!/bin/sh
# OK5TVR APRS v1.9: install unified web headless service on Raspberry Pi OS/Debian.
# Run as the normal account: sh install_raspberry.sh [--lan].
set -eu

case "${1:-}" in
  "") ENABLE_LAN=0 ;;
  --lan) ENABLE_LAN=1 ;;
  *) echo 'Pouziti: sh install_raspberry.sh [--lan]' >&2; exit 2 ;;
esac

if [ "$(id -u)" -eq 0 ]; then
  echo 'Spust skript jako bezny uzivatel (ne sudo). Skript zavola sudo jen pro instalaci.' >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  echo 'Chybi sudo.' >&2; exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo 'Neni dostupny systemd.' >&2; exit 1
fi

SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVICE_USER=$(id -un)
USER_HOME=$HOME
INSTALL_DIR=/opt/ok5tvr-aprs
CONFIG_PATH=$USER_HOME/.config/ok5tvr-aprs/config.json
UNIT_FILE=/etc/systemd/system/ok5tvr-aprs.service

printf 'Instaluji pro uzivatele %s do %s\n' "$SERVICE_USER" "$INSTALL_DIR"
sudo apt-get update
sudo apt-get install -y python3 python3-serial
sudo install -d -m 755 "$INSTALL_DIR"
# Only runtime files, no tests or credentials in /opt.
for f in aprs_service.py service_config.py aprs_protocol.py aprs_serial.py \
         aprs_digi.py aprs_features.py aprs_station.py aprs_messages.py aprs_operations.py aprs_telemetry.py web_panel.py \
         web_dashboard.html web_control.html web_messages.html web_operations.html web_unified.html web_locale.js offline_geography.json; do
  sudo install -m 644 "$SRC_DIR/$f" "$INSTALL_DIR/$f"
done
sudo chmod 755 "$INSTALL_DIR/aprs_service.py"
python3 "$INSTALL_DIR/aprs_service.py" --config "$CONFIG_PATH" --init
if [ "$ENABLE_LAN" -eq 1 ]; then
  PYTHONPATH="$SRC_DIR" CONFIG_PATH="$CONFIG_PATH" python3 - <<'PY'
import os
from service_config import ServiceConfig
cfg=ServiceConfig(os.environ['CONFIG_PATH']).load_or_create()
cfg.update({'web':{'lan':True}})
print('LAN web: povoleno (pristup jen s dlouhym tajnym tokenem).')
PY
fi
# User owns USB CDC ttyACM devices via dialout, service gets this group even
# before the next interactive login.
sudo usermod -a -G dialout "$SERVICE_USER"

TMP_UNIT=$(mktemp)
trap 'rm -f "$TMP_UNIT"' EXIT HUP INT TERM
cat > "$TMP_UNIT" <<EOF
[Unit]
Description=OK5TVR APRS USB KISS iGate/DIGI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
SupplementaryGroups=dialout
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/aprs_service.py --config $CONFIG_PATH
Restart=always
RestartSec=8
TimeoutStopSec=15
Environment=PYTHONUNBUFFERED=1
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 "$TMP_UNIT" "$UNIT_FILE"
sudo systemctl daemon-reload
sudo systemctl enable --now ok5tvr-aprs.service
sudo systemctl restart ok5tvr-aprs.service
printf '\nSluzba: sudo systemctl status ok5tvr-aprs\n'
printf 'Log: sudo journalctl -u ok5tvr-aprs -f\n'
printf 'Soukrome URL: python3 %s/aprs_service.py --config %s --links\n' "$INSTALL_DIR" "$CONFIG_PATH"
printf 'Unified web: use private ADMIN URL with path /unified?admin=YOUR_TOKEN.\n'
printf 'Auto iGate i auto RF DIGI jsou vychozim stavem VYPNUTY.\n'
