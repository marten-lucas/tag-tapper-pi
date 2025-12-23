#!/bin/bash
# Start-Skript (foreground) für Tag Tapper auf dem Raspberry Pi LCD-Display

cd /home/dietpi/tag-tapper-pi || exit 1

# Terminal + Textual settings for framebuffer LCD
export TERM=linux
export COLORTERM=truecolor
export TEXTUAL_DRIVER=linux
export TEXTUAL_COLOR_SYSTEM=truecolor

ERROR_LOG=/home/dietpi/error.log
mkdir -p "$(dirname "$ERROR_LOG")"

# Starte die App und ersetze die Shell (sichtbar auf TTY)
exec sudo -E /usr/bin/python3 /home/dietpi/tag-tapper-pi/app.py >> "$ERROR_LOG" 2>&1
