#!/bin/sh

cd /home/rasbian/app/stats
sudo python3.6 -m http.server -b 0.0.0.0 80

