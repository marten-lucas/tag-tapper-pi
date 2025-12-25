#!/usr/bin/env bash
set -euo pipefail

# Wrapper to install and run the vlan sync script
REPO_DIR="/home/dietpi/tag-tapper-pi"
SCRIPT_SRC="$REPO_DIR/networking/sync_vlans.py"
INSTALL_BIN="/usr/local/bin/vlan-sync.py"
WRAPPER="/usr/local/bin/vlan-sync.sh"
SERVICE_DST="/etc/systemd/system/vlan-sync.service"
SERVICE_SRC="$REPO_DIR/networking/vlan-sync.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root to install the service or perform network changes."
  exit 1
fi

# Copy python script
cp "$SCRIPT_SRC" "$INSTALL_BIN"
chmod +x "$INSTALL_BIN"

# Copy wrapper that just executes the python script
cat > "$WRAPPER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
/usr/local/bin/vlan-sync.py
EOF
chmod +x "$WRAPPER"

# Copy systemd unit
cp "$SERVICE_SRC" "$SERVICE_DST"

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable --now vlan-sync.service || true

# Run once now
systemctl start --no-block vlan-sync.service || true

echo "VLAN sync service installed and started."
