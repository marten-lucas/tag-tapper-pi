#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=tag-tapper-pi.service
REPO_DIR=/home/dietpi/tag-tapper-pi
LOG_FILE=${REPO_DIR}/tag-tapper-pi.log

cd "$REPO_DIR"

echo "Pulling latest changes..."
git pull

echo "Updating service unit..."
sudo cp ${SERVICE_NAME} /etc/systemd/system/${SERVICE_NAME}
sudo chmod +x start.sh
sudo systemctl daemon-reload
echo "Installing VLAN sync service and scripts..."
# Copy scripts to system locations and install systemd unit (do not execute repo script directly)
sudo cp "${REPO_DIR}/networking/sync_vlans.py" /usr/local/bin/vlan-sync.py || true
sudo chmod +x /usr/local/bin/vlan-sync.py || true
sudo cp "${REPO_DIR}/networking/vlan-sync.sh" /usr/local/bin/vlan-sync.sh || true
sudo chmod +x /usr/local/bin/vlan-sync.sh || true
sudo cp "${REPO_DIR}/networking/vlan-sync.service" /etc/systemd/system/vlan-sync.service || true
sudo systemctl daemon-reload
# Enable and start the vlan-sync service so it runs at boot and now
sudo systemctl enable --now vlan-sync.service || true

echo "Ensuring log file exists and is owned by 'dietpi'..."
sudo touch "$LOG_FILE" || true
sudo chown dietpi:dietpi "$LOG_FILE" || true

echo "Restarting service $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl restart vlan-sync.service 


echo "Tailing error log: $LOG_FILE"
tail -f "$LOG_FILE"
