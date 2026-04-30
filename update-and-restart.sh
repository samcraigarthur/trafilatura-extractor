#!/bin/bash
# Quick update and restart script for GCP deployment
# Run this after SSH-ing into your instance

cd ~/trafilatura-extractor
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart trafilatura-extractor

echo "✓ Update complete and service restarted!"
echo "Check status with: sudo systemctl status trafilatura-extractor"
