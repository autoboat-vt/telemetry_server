#!/bin/sh
# cloudflared entrypoint.
#
# Supports two modes:
#
# 1. Dashboard-managed tunnel (default): set TUNNEL_TOKEN in .env to the token
#    from Cloudflare Zero Trust dashboard -> Networks -> Tunnels -> (your
#    tunnel) -> Install. The tunnel's public hostname -> service routing is
#    configured in the dashboard UI. This is the simplest mode.
#
# 2. File-managed tunnel: set USE_CONFIG_FILE=1 and TUNNEL_ID in .env, and
#    place the credentials JSON at server_files/docker/cloudflared/<TUNNEL_ID>.json.
#    Routing uses server_files/docker/cloudflared/config.yml.
#
# In both modes cloudflared dials OUT to Cloudflare's edge, so no inbound
# ports need to be open on the host.
set -eu

if [ "${USE_CONFIG_FILE:-0}" = "1" ]; then
    if [ -z "${TUNNEL_ID:-}" ]; then
        echo "[cloudflared] ERROR: USE_CONFIG_FILE=1 but TUNNEL_ID is not set."
        exit 1
    fi
    if [ ! -f "/etc/cloudflared/${TUNNEL_ID}.json" ]; then
        echo "[cloudflared] ERROR: credentials file /etc/cloudflared/${TUNNEL_ID}.json not found."
        echo "[cloudflared] Run 'cloudflared tunnel create ${TUNNEL_ID}' and copy the JSON here."
        exit 1
    fi
    echo "[cloudflared] Starting in file-managed mode (tunnel: ${TUNNEL_ID})"
    exec cloudflared tunnel --config /etc/cloudflared/config.yml run
else
    if [ -z "${TUNNEL_TOKEN:-}" ]; then
        echo "[cloudflared] ERROR: TUNNEL_TOKEN is not set."
        echo "[cloudflared] Get it from: Cloudflare Zero Trust dashboard ->"
        echo "[cloudflared] Networks -> Tunnels -> (your tunnel) -> Install."
        echo "[cloudflared] Alternatively, set USE_CONFIG_FILE=1 and TUNNEL_ID."
        exit 1
    fi
    echo "[cloudflared] Starting in dashboard-managed mode (token present)"
    exec cloudflared tunnel --no-autoupdate run --token "${TUNNEL_TOKEN}"
fi
