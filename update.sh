#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=tag-tapper-pi.service
REPO_DIR=/home/dietpi/tag-tapper-pi
LOG_FILE=${REPO_DIR}/tag-tapper-pi.log
ERR_LOG=${REPO_DIR}/error.log

cd "$REPO_DIR"

echo "Pulling latest changes..."
git pull

echo "Updating service unit..."
sudo cp ${SERVICE_NAME} /etc/systemd/system/${SERVICE_NAME}
sudo systemctl daemon-reload

echo "Ensuring log file exists and is owned by 'dietpi'..."
sudo touch "$LOG_FILE" || true
sudo chown dietpi:dietpi "$LOG_FILE" || true

echo "Ensuring error log file exists and is owned by 'dietpi'..."
sudo touch "$ERR_LOG" || true
sudo chown dietpi:dietpi "$ERR_LOG" || true

echo "Restarting service $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "Tailing error log: $ERR_LOG"
tail -f "$ERR_LOG"
