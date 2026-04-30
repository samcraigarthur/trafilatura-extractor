# Google Cloud Deployment Guide

This guide explains how to set up your Trafilatura Extractor app to run persistently on a Google Cloud Compute Engine instance.

## Prerequisites

- Google Cloud Compute Engine VM running Linux (Ubuntu 20.04+ recommended)
- SSH access to your instance
- `git` installed on the instance

## Setup Steps

### 1. Clone the Repository

```bash
cd ~
git clone https://github.com/samcraigarthur/trafilatura-extractor.git
cd trafilatura-extractor
```

### 2. Set Up Python Environment

```bash
# Install Python and pip if not already present
sudo apt update
sudo apt install python3 python3-pip python3-venv -y

# Create virtual environment
python3 -m venv venv

# Activate and install dependencies
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Create your .env file with any required settings
nano .env
```

Add your configuration (e.g., `AUTH_TOKEN` if you want one):
```
AUTH_TOKEN=your_secret_token_here
```

### 4. Set Up Systemd Service

**Option A: Using the provided service file**

```bash
# Copy service file to systemd directory (MUST use sudo)
sudo cp trafilatura-extractor.service /etc/systemd/system/

# Replace placeholder with your username (e.g., if your user is 'ubuntu', replace _SERVICE_USER_ with ubuntu)
# Note: Replace 'ubuntu' with your actual GCP instance username if different
sudo sed -i 's/_SERVICE_USER_/ubuntu/g' /etc/systemd/system/trafilatura-extractor.service

# Create log directory
sudo mkdir -p /var/log/trafilatura-extractor
sudo chown ubuntu:ubuntu /var/log/trafilatura-extractor

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable trafilatura-extractor

# Start the service
sudo systemctl start trafilatura-extractor

# Check status
sudo systemctl status trafilatura-extractor
```

**Option B: Manual systemd setup**

If you prefer to create the service file manually:

```bash
sudo tee /etc/systemd/system/trafilatura-extractor.service > /dev/null <<EOF
[Unit]
Description=Trafilatura Extractor FastAPI Application
After=network.target

[Service]
Type=simple
User=\$USER
WorkingDirectory=\$HOME/trafilatura-extractor
ExecStart=\$HOME/trafilatura-extractor/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/trafilatura-extractor/app.log
StandardError=append:/var/log/trafilatura-extractor/error.log
EnvironmentFile=-\$HOME/trafilatura-extractor/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable trafilatura-extractor
sudo systemctl start trafilatura-extractor
```

### 5. Configure Firewall (If Needed)

If your GCP instance has a firewall, ensure port 8000 is open:

```bash
# On the instance, check if UFW is active
sudo ufw status

# If active, allow port 8000
sudo ufw allow 8000/tcp
```

Also check GCP Console > VPC Network > Firewall rules to allow traffic on port 8000.

### 6. Verify It's Running

```bash
# Check service status
sudo systemctl status trafilatura-extractor

# View logs
sudo journalctl -u trafilatura-extractor -f

# Alternative: view app logs directly
tail -f /var/log/trafilatura-extractor/app.log
```

## Management Commands

```bash
# Start the service
sudo systemctl start trafilatura-extractor

# Stop the service
sudo systemctl stop trafilatura-extractor

# Restart the service
sudo systemctl restart trafilatura-extractor

# View real-time logs
sudo journalctl -u trafilatura-extractor -f

# View last 50 lines of logs
sudo journalctl -u trafilatura-extractor -n 50

# Check if service is enabled on boot
sudo systemctl is-enabled trafilatura-extractor

# Disable from auto-start
sudo systemctl disable trafilatura-extractor

# Re-enable auto-start
sudo systemctl enable trafilatura-extractor
```

## Updating the App

When you push updates to the repository:

```bash
cd ~/trafilatura-extractor
git pull origin main
source venv/bin/activate
pip install -r requirements.txt  # In case dependencies changed

# Restart the service
sudo systemctl restart trafilatura-extractor
```

## Alternative: Docker Deployment

For even more robustness, you can containerize your app:

1. Create a `Dockerfile` in your repo
2. Build and push to GCP Artifact Registry or Docker Hub
3. Use Google Cloud Run or deploy the container on Compute Engine

This is recommended for production environments.

## Troubleshooting

**Service won't start:**
```bash
sudo journalctl -u trafilatura-extractor -n 100
sudo systemctl status trafilatura-extractor
```

**Permission denied:**
- Ensure the service user matches your actual username
- Check directory ownership: `ls -la ~/trafilatura-extractor`

**Port already in use:**
```bash
# Find what's using port 8000
sudo lsof -i :8000
# Kill if needed
sudo kill <PID>
```

**Need different port:**
Edit `/etc/systemd/system/trafilatura-extractor.service` and change the port in ExecStart, then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart trafilatura-extractor
```
