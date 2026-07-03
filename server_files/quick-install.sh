#!/bin/bash
#
# quick-install.sh — one-line installer for the Autoboat telemetry server.
#
# Installs Docker (if missing), clones the repo, configures .env, and starts
# the stack. Designed for the Cloudflare Tunnel architecture — works on any
# Ubuntu/Debian VM (Oracle Cloud, AWS EC2, DigitalOcean, etc.).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/autoboat-vt/telemetry_server/main/server_files/quick-install.sh | bash
#
# Or with the token inline (skip the prompt):
#   curl -fsSL https://raw.githubusercontent.com/autoboat-vt/telemetry_server/main/server_files/quick-install.sh | TUNNEL_TOKEN=eyJ... bash
#
# Or clone first and run locally:
#   git clone https://github.com/autoboat-vt/telemetry_server.git
#   cd telemetry_server
#   TUNNEL_TOKEN=eyJ... bash server_files/quick-install.sh

set -euo pipefail

REPO_URL='https://github.com/autoboat-vt/telemetry_server.git'
REPO_BRANCH='main'
INSTALL_DIR="$HOME/telemetry_server"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
info() { echo -e "${BLUE}=== $* ===${NC}"; }
ok() { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}! $*${NC}"; }
err() { echo -e "${RED}✗ $*${NC}" >&2; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
    err "Don't run this as root. Run as your normal user (sudo will be used as needed)."
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    info "Installing git"
    sudo apt-get update -y && sudo apt-get install -y git
fi

# ---------------------------------------------------------------------------
# 1. Get the TUNNEL_TOKEN (from env var, argument, or interactive prompt)
# ---------------------------------------------------------------------------
TUNNEL_TOKEN="${TUNNEL_TOKEN:-}"
if [ -z "$TUNNEL_TOKEN" ]; then
    if [ -t 0 ]; then
        # Interactive shell — prompt the user
        echo
        echo "Cloudflare Tunnel token required."
        echo "Get it from: https://dash.cloudflare.com -> Networking -> Tunnels -> (tunnel) -> Install"
        read -r -p "Paste token: " TUNNEL_TOKEN
    else
        err "TUNNEL_TOKEN not set. Either:"
        err "  1. Pipe with the env var: curl ... | TUNNEL_TOKEN=eyJ... bash"
        err "  2. Run interactively (not piped) to be prompted."
        exit 1
    fi
fi

if [ -z "$TUNNEL_TOKEN" ] || [ "$TUNNEL_TOKEN" = "PASTE-YOUR-TUNNEL-TOKEN-HERE" ]; then
    err "No TUNNEL_TOKEN provided. Aborting."
    exit 1
fi

ok "Tunnel token received (${#TUNNEL_TOKEN} chars)"

# ---------------------------------------------------------------------------
# 2. Install Docker if not present
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    info "Installing Docker"
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    ARCH=$(dpkg --print-architecture)
    CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
    echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${CODENAME} stable" |
        sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update -y
    sudo apt-get install -y \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    ok "Docker installed"
else
    ok "Docker already installed"
fi

sudo systemctl enable --now docker

# Use docker directly if the group is active, else fall back to sudo
if docker ps >/dev/null 2>&1; then
    DOCKER="docker"
else
    warn "Docker group not active in this shell — using sudo docker for now."
    warn "Run 'newgrp docker' or log out and back in to drop the sudo."
    DOCKER="sudo docker"
fi

# ---------------------------------------------------------------------------
# 2b. Add swap (helps on small instances like GCP e2-micro with 1GB RAM)
# ---------------------------------------------------------------------------
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ]; then
    info "Creating 2GB swap file (helps on low-RAM instances)"
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    if ! grep -q '^/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
    fi
    # Be conservative — don't swap unless we're actually low on RAM
    echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf >/dev/null
    sudo sysctl -p /etc/sysctl.d/99-swappiness.conf || true
    ok "Swap enabled"
else
    ok "Swap already present"
fi

# ---------------------------------------------------------------------------
# 3. Clone or update the repo
# ---------------------------------------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing checkout at $INSTALL_DIR"
    cd "$INSTALL_DIR"
    git fetch --quiet origin
    git reset --hard "origin/$REPO_BRANCH"
else
    info "Cloning repo to $INSTALL_DIR"
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
ok "Code is at $(git rev-parse --short HEAD)"

# ---------------------------------------------------------------------------
# 4. Configure .env
# ---------------------------------------------------------------------------
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
fi
# Always update the token (in case it changed)
sed -i "s|^TUNNEL_TOKEN=.*|TUNNEL_TOKEN=${TUNNEL_TOKEN}|" "$INSTALL_DIR/.env"
ok ".env configured"

# ---------------------------------------------------------------------------
# 5. Build and start
# ---------------------------------------------------------------------------
info "Building and starting the stack (this takes a few minutes)"
$DOCKER compose up -d --build
ok "Stack started"

# ---------------------------------------------------------------------------
# 6. Verify
# ---------------------------------------------------------------------------
info "Waiting for cloudflared to connect"
sleep 8

echo
$DOCKER compose ps
echo
echo "--- cloudflared logs (last 15 lines) ---"
$DOCKER compose logs --tail=15 cloudflared || true
echo

if $DOCKER compose logs cloudflared 2>&1 | grep -q "Registered tunnel connection"; then
    ok "Tunnel is connected! https://vt-autoboat-telemetry.uk should now serve from this host."
else
    warn "Tunnel connection not yet visible in logs. Check again in a moment:"
    warn "  cd $INSTALL_DIR && docker compose logs -f cloudflared"
    warn "Look for 'Registered tunnel connection' lines."
fi

echo
echo "Useful commands:"
echo "  cd $INSTALL_DIR"
echo "  docker compose ps                  # status"
echo "  docker compose logs -f cloudflared # tunnel logs"
echo "  docker compose logs -f telemetry-prod  # app logs"
echo "  git pull && docker compose up -d --build  # deploy updates"
echo
warn "IMPORTANT: if you were running this stack elsewhere (e.g. your Mac),"
warn "stop it there so the tunnel connector moves to this host:"
warn "  docker compose down  # on the old host"
