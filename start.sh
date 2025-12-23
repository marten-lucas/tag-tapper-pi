#!/bin/bash
# Start-Skript (foreground) für Tag Tapper auf dem Raspberry Pi LCD-Display

cd /home/dietpi/tag-tapper-pi || exit 1

# Map console to framebuffer 1 (same as the working example)
/usr/bin/con2fbmap 1 1 || true
clear

# Wichtig: Keine GPM Variablen mehr!
# Textual erkennt das Device nun über TEXTUAL_EVDEV_PATH
export TERM=linux
export LANG=de_DE.UTF-8
export COLORTERM=truecolor
export TEXTUAL_DRIVER=linux
export TEXTUAL_COLOR_SYSTEM=truecolor

ERROR_LOG=/home/dietpi/error.log
mkdir -p "$(dirname "$ERROR_LOG")"

# Starte die App und ersetze die Shell (sichtbar auf TTY)
# Run directly as root (systemd runs the service as root); do not use sudo here.
exec /usr/bin/python3 /home/dietpi/tag-tapper-pi/app.py >> "$ERROR_LOG" 2>&1
