#!/usr/bin/env bash
# Research Analyst - OCI ARM Instance Deployment
# Run this ON the OCI instance after SSH-ing in.
#
# Prerequisites:
#   - OCI VM.Standard.A1.Flex (ARM, 4 OCPU, 24GB RAM)
#   - Ubuntu 22.04+ or Oracle Linux 8+
#   - SSH access configured
#
# This script:
#   1. Installs Docker (if not present)
#   2. Clones the repo
#   3. Builds and runs the container
#   4. Sets up systemd service for auto-restart
#   5. Configures firewall for port 8700
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/nrupala/research-analyst/main/deploy/oci/setup.sh | bash
#   -- OR --
#   chmod +x setup.sh && ./setup.sh

set -euo pipefail

APP_NAME="research-analyst"
APP_PORT=8700
REPO_URL="https://github.com/nrupala/research-analyst.git"
INSTALL_DIR="/opt/$APP_NAME"

echo "============================================"
echo "Research Analyst - OCI ARM Deployment"
echo "============================================"
echo ""

# --- Step 1: Install Docker ---
echo "[1/6] Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "  Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "  Docker installed."
else
    echo "  Docker already installed: $(docker --version)"
fi

# --- Step 2: Install Docker Compose plugin ---
echo "[2/6] Checking Docker Compose..."
if ! docker compose version &> /dev/null; then
    echo "  Installing Docker Compose plugin..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-compose-plugin 2>/dev/null || {
        # Fallback for Oracle Linux
        COMPOSE_VERSION="v2.27.0"
        sudo curl -SL "https://github.com/docker/compose/releases/download/$COMPOSE_VERSION/docker-compose-linux-aarch64" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    }
    echo "  Docker Compose installed."
else
    echo "  Docker Compose already installed."
fi

# --- Step 3: Clone or update repo ---
echo "[3/6] Setting up application..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$USER:$USER" "$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Updating existing repo..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "  Cloning repo..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# --- Step 4: Build and run ---
echo "[4/6] Building and starting container..."
docker compose down 2>/dev/null || true
docker compose up -d --build

echo "  Waiting for health check..."
sleep 10

if curl -sf "http://localhost:$APP_PORT/api/health" > /dev/null 2>&1; then
    echo "  Health check PASSED."
else
    echo "  WARNING: Health check failed. Check logs: docker compose logs"
fi

# --- Step 5: Create systemd service ---
echo "[5/6] Setting up auto-restart service..."
sudo tee /etc/systemd/system/$APP_NAME.service > /dev/null << UNIT
[Unit]
Description=Research Analyst
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=$USER

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable "$APP_NAME"
echo "  Systemd service created and enabled."

# --- Step 6: Open firewall ---
echo "[6/6] Configuring firewall..."

# iptables (works on both Ubuntu and Oracle Linux)
sudo iptables -I INPUT -p tcp --dport $APP_PORT -j ACCEPT 2>/dev/null || true

# Persist iptables rules
if command -v netfilter-persistent &> /dev/null; then
    sudo netfilter-persistent save 2>/dev/null || true
elif command -v firewall-cmd &> /dev/null; then
    # Oracle Linux with firewalld
    sudo firewall-cmd --permanent --add-port=$APP_PORT/tcp 2>/dev/null || true
    sudo firewall-cmd --reload 2>/dev/null || true
fi

echo ""
echo "============================================"
echo "Deployment Complete"
echo "============================================"
echo ""
echo "  Local:    http://localhost:$APP_PORT"
echo "  Public:   http://$(curl -s ifconfig.me):$APP_PORT"
echo "  Health:   http://localhost:$APP_PORT/api/health"
echo ""
echo "  Logs:     cd $INSTALL_DIR && docker compose logs -f"
echo "  Restart:  cd $INSTALL_DIR && docker compose restart"
echo "  Update:   cd $INSTALL_DIR && git pull && docker compose up -d --build"
echo ""
echo "  IMPORTANT: In OCI Console, add an Ingress Rule to your"
echo "  subnet's Security List allowing TCP port $APP_PORT from 0.0.0.0/0"
echo "  (or restrict to Cloudflare IPs for security)."
echo ""
echo "  Once running, update the Cloudflare Worker env:"
echo "    BACKEND_PRIMARY = http://<OCI_PUBLIC_IP>:$APP_PORT"
echo "============================================"
