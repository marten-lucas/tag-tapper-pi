#!/bin/bash
# Stop the service, run calibration, then restart

echo "Stopping tag-tapper-pi service..."
sudo systemctl stop tag-tapper-pi.service

echo "Removing old calibration data..."
# Remove old touch_calibration section from config.yaml
if grep -q "touch_calibration:" /home/dietpi/tag-tapper-pi/config.yaml 2>/dev/null; then
    # Create backup
    cp /home/dietpi/tag-tapper-pi/config.yaml /home/dietpi/tag-tapper-pi/config.yaml.bak
    # Remove touch_calibration section using sed
    sed -i '/^touch_calibration:/,/^[a-z]/ { /^touch_calibration:/d; /^[a-z]/!d; }' /home/dietpi/tag-tapper-pi/config.yaml
    echo "✓ Old calibration removed"
fi

echo "Starting touch calibration on LCD..."
echo "Please touch the 5 targets that appear on the LCD screen"
echo "Press Ctrl+C when done (after touching all 5 targets)"
echo ""

# Map console to framebuffer 1
sudo /usr/bin/con2fbmap 1 1 || true

# Run calibration directly on tty1 (the LCD) with proper permissions
cd /home/dietpi/tag-tapper-pi
sudo sh -c 'TERM=linux LANG=de_DE.UTF-8 /usr/bin/python3 /home/dietpi/tag-tapper-pi/calibrate_touch.py < /dev/tty1 > /dev/tty1 2>&1'

echo ""
echo "Calibration complete!"
echo "Restarting tag-tapper-pi service..."
sudo systemctl start tag-tapper-pi.service

echo ""
echo "Done. Check calibration results:"
if grep -q "touch_calibration:" /home/dietpi/tag-tapper-pi/config.yaml 2>/dev/null; then
    echo "✓ Calibration saved to config.yaml"
    echo ""
    grep -A 8 "touch_calibration:" /home/dietpi/tag-tapper-pi/config.yaml
else
    echo "⚠ Warning: Calibration not found in config.yaml"
fi
