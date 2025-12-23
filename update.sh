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
sudo systemctl daemon-reload

echo "Ensuring log file exists and is owned by 'dietpi'..."
sudo touch "$LOG_FILE" || true
sudo chown dietpi:dietpi "$LOG_FILE" || true

echo "Restarting service $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "Tailing error log: $LOG_FILE"
tail -f "$LOG_FILE"
