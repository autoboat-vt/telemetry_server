#!/bin/bash
#
# Oracle Cloud (or any Ubuntu VM) — first-boot user-data script.
#
# Installs Docker, clones the telemetry_server repo, configures .env, and
# starts the stack via docker compose. Designed for the Cloudflare Tunnel
# architecture (outbound-only — no inbound ports needed beyond SSH).
#
# ---- USAGE ----
# 1. Launch an Oracle Cloud Always Free ARM instance (Ubuntu 22.04 or 24.04,
#    shape VM.Standard.A1.Flex, 1+ OCPU / 2+ GB).
# 2. In the "Launch instance" wizard, scroll to "Advanced options" -> paste
#    this entire file into the "User data" field (or upload it as a file).
# 3. Paste your TUNNEL_TOKEN below in the CONFIG section.
# 4. Launch the instance. Wait ~3-5 min for the script to finish, then:
#      ssh ubuntu@<instance-public-IP>
#      docker compose -f ~/telemetry_server/docker-compose.yml ps
#      docker compose -f ~/telemetry_server/docker-compose.yml logs cloudflared
# 5. IMPORTANT: stop your local stack first (`docker compose down` on your Mac)
#    so the tunnel connector moves to this instance instead of round-robining.
#
# This script is idempotent — re-running it won't break anything.

set -euo pipefail

# ========== CONFIG ==========
# Cloudflare Tunnel token from:
#   https://dash.cloudflare.com/ -> Networking -> Tunnels -> (tunnel) -> Install
# Paste your real token between the single quotes on the next line.
TUNNEL_TOKEN='PASTE-YOUR-TUNNEL-TOKEN-HERE'

# Repo URL (public GitHub repo — no auth needed)
REPO_URL='https://github.com/autoboat-vt/telemetry_server.git'
REPO_BRANCH='main'

# Where to put the project
INSTALL_DIR="$HOME/telemetry_server"
# =============================

# Oracle runs user-data as root by default. Re-run as the ubuntu user.
if [ "$(id -u)" -eq 0 ]; then
    exec sudo -u ubuntu bash "$0" "$@"
fi

echo "=== [1/5] Installing Docker ==="
if ! command -v docker >/dev/null 2>&1; then
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
    echo "Docker installed."
else
    echo "Docker already installed, skipping."
fi

# Make sure docker runs on boot
sudo systemctl enable --now docker

# Apply the docker group to the current session without needing to re-login
# (so we can run docker in this same script run).
if ! docker ps >/dev/null 2>&1; then
    echo "(docker group not applied yet — using sudo for the rest of this script)"
    DOCKER="sudo docker"
else
    DOCKER="docker"
fi

echo "=== [2/5] Cloning repo ==="
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Repo already present at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git fetch --quiet origin
    git reset --hard "origin/$REPO_BRANCH"
else
    git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo "=== [3/5] Configuring .env ==="
if [ -f "$INSTALL_DIR/.env" ]; then
    echo ".env already exists, leaving it in place."
else
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    # Set the TUNNEL_TOKEN (replace the placeholder)
    sed -i "s|^TUNNEL_TOKEN=.*|TUNNEL_TOKEN=${TUNNEL_TOKEN}|" "$INSTALL_DIR/.env"
    echo ".env created with TUNNEL_TOKEN set."
fi

# Fail fast if the user forgot to replace the placeholder
if grep -q 'PASTE-YOUR-TUNNEL-TOKEN-HERE' "$INSTALL_DIR/.env"; then
    echo "ERROR: TUNNEL_TOKEN is still the placeholder."
    echo "Edit $INSTALL_DIR/.env and paste your real token, then run:"
    echo "  cd $INSTALL_DIR && docker compose up -d --build"
    exit 1
fi

echo "=== [4/5] Building and starting the stack ==="
$DOCKER compose up -d --build

echo "=== [5/5] Waiting for cloudflared to register tunnel connections ==="
sleep 10
$DOCKER compose logs --tail=20 cloudflared || true

echo
echo "========================================"
echo "Done! Stack is running."
echo "========================================"
echo
echo "Check status:"
echo "  cd $INSTALL_DIR"
echo "  docker compose ps"
echo "  docker compose logs -f cloudflared"
echo
echo "Look for 'Registered tunnel connection' lines (usually 4)."
echo "Once connected, https://vt-autoboat-telemetry.uk should serve from this instance."
echo
echo "To deploy updates later:"
echo "  cd $INSTALL_DIR && git pull && docker compose up -d --build"
