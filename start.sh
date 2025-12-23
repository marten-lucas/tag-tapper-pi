#!/bin/bash
cd /home/dietpi/tag-tapper-pi || exit 1

# Map console to framebuffer 1
/usr/bin/con2fbmap 1 1 || true
clear

# Nur die absolut notwendigen Variablen
export TERM=linux
export LANG=de_DE.UTF-8

/usr/bin/python3 /home/dietpi/tag-tapper-pi/app.py