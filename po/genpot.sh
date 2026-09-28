#!/bin/sh
# Stupid workaround for intltools not handling extensionless files
ln -s promptline ../promptline.py
ln -s promptline-remote ../promptline-remote.py

# Make translation files
intltool-update -g promptline -o promptline.pot -p

# Cleanup after stupid workaround
rm ../promptline.py
rm ../promptline-remote.py
