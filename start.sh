#!/bin/bash
# Display mappen
/usr/bin/con2fbmap 1 1
clear

# Wichtig: Keine GPM Variablen mehr!
# Textual erkennt das Device nun über TEXTUAL_EVDEV_PATH
export TERM=linux
export LANG=de_DE.UTF-8

/usr/bin/python3 /home/dietpi/tag-tapper-pi/app.py