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

# Install web config service
echo "Installing web config service..."
sudo cp "${REPO_DIR}/web_gui/web-config.service" /etc/systemd/system/web-config.service || true

sudo systemctl daemon-reload
# Enable and start the web-config service
sudo systemctl enable --now web-config.service || true

echo "Ensuring log file exists and is owned by 'dietpi'..."
sudo touch "$LOG_FILE" || true
sudo chown dietpi:dietpi "$LOG_FILE" || true

echo "Restarting services..."
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl restart web-config.service || true 


echo "Tailing error log: $LOG_FILE"
tail -f "$LOG_FILE"
