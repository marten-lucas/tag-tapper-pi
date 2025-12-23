#!/bin/bash
# Display mappen
/usr/bin/con2fbmap 1 1
clear

# Wichtig: Keine GPM Variablen mehr!
export TERM=linux
export LANG=de_DE.UTF-8
export TEXTUAL_DRIVER=linux
export TEXTUAL_COLOR_SYSTEM=truecolor

/usr/bin/python3 /home/dietpi/tag-tapper-pi/app.py