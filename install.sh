#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

usage() {
    cat <<'EOF'
Usage:
    bash install.sh
    curl -fsSL https://raw.githubusercontent.com/autoboat-vt/telemetry_server/main/install.sh | TUNNEL_TOKEN=eyJ... bash

Examples:
  TUNNEL_TOKEN=eyJ... bash install.sh
EOF
}

run_as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

require_repo_root() {
    if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ] || [ ! -d "$SCRIPT_DIR/docker" ]; then
        err "Run this from the root of the telemetry_server checkout."
        exit 1
    fi
}

detect_docker_command() {
    if docker ps >/dev/null 2>&1; then
        DOCKER='docker'
    else
        warn "Docker group not active in this shell — using sudo docker for now."
        warn "Run 'newgrp docker' or log out and back in to drop the sudo."
        DOCKER='sudo docker'
    fi
}

install_docker_if_needed() {
    if ! command -v docker >/dev/null 2>&1; then
        info "Installing Docker"
        run_as_root apt-get update -y
        run_as_root apt-get install -y ca-certificates curl
        run_as_root install -m 0755 -d /etc/apt/keyrings
        run_as_root curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            -o /etc/apt/keyrings/docker.asc
        run_as_root chmod a+r /etc/apt/keyrings/docker.asc
        ARCH=$(dpkg --print-architecture)
        CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
        echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${CODENAME} stable" |
            run_as_root tee /etc/apt/sources.list.d/docker.list >/dev/null
        run_as_root apt-get update -y
        run_as_root apt-get install -y \
            docker-ce docker-ce-cli containerd.io \
            docker-buildx-plugin docker-compose-plugin
        if [ "$(id -u)" -ne 0 ]; then
            run_as_root usermod -aG docker "$USER"
        fi
        ok "Docker installed"
    else
        ok "Docker already installed"
    fi

    run_as_root systemctl enable --now docker
    detect_docker_command
}

ensure_tunnel_token() {
    TUNNEL_TOKEN="${TUNNEL_TOKEN:-}"
    if [ -z "$TUNNEL_TOKEN" ]; then
        if [ -t 0 ]; then
            echo
            echo "Cloudflare Tunnel token required."
            echo "Get it from: https://dash.cloudflare.com -> Networking -> Tunnels -> (tunnel) -> Install"
            read -r -p "Paste token: " TUNNEL_TOKEN
        else
            err "TUNNEL_TOKEN not set. Either:"
            err "  1. Pipe with the env var: TUNNEL_TOKEN=eyJ... bash install.sh"
            err "  2. Run interactively to be prompted."
            exit 1
        fi
    fi

    if [ -z "$TUNNEL_TOKEN" ] || [ "$TUNNEL_TOKEN" = "PASTE-YOUR-TUNNEL-TOKEN-HERE" ]; then
        err "No TUNNEL_TOKEN provided. Aborting."
        exit 1
    fi

    ok "Tunnel token received (${#TUNNEL_TOKEN} chars)"
}

configure_env() {
    local env_file="$SCRIPT_DIR/.env"

    if [ ! -f "$env_file" ]; then
        cp "$SCRIPT_DIR/.env.example" "$env_file"
    fi

    sed -i.bak "s|^TUNNEL_TOKEN=.*|TUNNEL_TOKEN=${TUNNEL_TOKEN}|" "$env_file"
    rm -f "$env_file.bak"
    ok ".env configured"
}

bootstrap_repo() {
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
}

bootstrap_and_reexec() {
    install_docker_if_needed
    ensure_tunnel_token
    bootstrap_repo
    exec env TUNNEL_TOKEN="$TUNNEL_TOKEN" bash "$INSTALL_DIR/install.sh"
}

start_cloud_stack() {
    require_repo_root
    install_docker_if_needed
    ensure_tunnel_token
    configure_env

    info "Pulling prebuilt images"
    $DOCKER compose pull telemetry-prod telemetry-test cloudflared
    ok "Images pulled"

    info "Starting the stack"
    $DOCKER compose up -d
    ok "Stack started"

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
        warn "  cd $SCRIPT_DIR && docker compose logs -f cloudflared"
        warn "Look for 'Registered tunnel connection' lines."
    fi

    echo
    echo "Useful commands:"
    echo "  cd $SCRIPT_DIR"
    echo "  docker compose ps                     # status"
    echo "  docker compose logs -f cloudflared    # tunnel logs"
    echo "  docker compose logs -f telemetry-prod # app logs"
    echo "  git pull && docker compose pull && docker compose up -d  # deploy updates"
    echo
    warn "IMPORTANT: if you were running this stack elsewhere (e.g. your Mac),"
    warn "stop it there so the tunnel connector moves to this host:"
    warn "  docker compose down  # on the old host"
}

main() {
    case "${1:-}" in
    -h | --help | help)
        usage
        ;;
    "")
        if [ -f "$SCRIPT_DIR/docker-compose.yml" ] && [ -d "$SCRIPT_DIR/docker" ]; then
            start_cloud_stack
        else
            bootstrap_and_reexec
        fi
        ;;
    *)
        err "Unknown argument: $1"
        usage
        exit 1
        ;;
    esac
}

main "$@"
