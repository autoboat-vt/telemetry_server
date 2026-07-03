# Autoboat Telemetry Server

[![Build and Push Image](https://github.com/autoboat-vt/telemetry_server/actions/workflows/build-and-push.yml/badge.svg)](https://github.com/autoboat-vt/telemetry_server/actions/workflows/build-and-push.yml)

A lightweight Flask-based web server to collect, display, and manage telemetry
data from the Virginia Tech Autoboat project. Ships as a multi-arch Docker
image, fronted by a Cloudflare Tunnel — no inbound ports, no nginx, no
certbot.

## Project Structure

```txt
autoboat_telemetry_server/
├── __init__.py                   # App factory
├── models.py                     # Database models
├── types.py                      # Custom types and enums
├── lock_manager.py               # Read-write lock manager
├── routes
    ├── __init__.py               # Routes initialization
    ├── autopilot_parameters.py   # Autopilot parameters routes
    ├── boat_status.py            # Boat status routes
    ├── waypoints.py              # Waypoints management routes
    ├── instance_manager.py       # Instance management routes

instance/
    ├── config.py                 # Configuration file
    ├── app.db                    # Database file

server_files/
├── quick-install.sh              # One-line installer for cloud VMs
├── cloud-init-user-data.sh       # Same, as cloud-init user-data
├── install.sh                    # Legacy bare-metal install (nginx + supervisor)
└── docker/
    ├── app-entrypoint.sh         # Restores config.py into the mounted instance volume
    ├── cloudflared/              # Optional file-managed tunnel config
    └── cron/                     # Cron image (calls /instance_manager/clean_instances)

.github/workflows/
└── build-and-push.yml            # CI: builds & pushes image to GHCR + Docker Hub
```

## Deployment (Docker + Cloudflare Tunnel)

The production stack runs as four Docker Compose services:

| Service          | Purpose                                                      |
| ---------------- | ------------------------------------------------------------ |
| `telemetry-prod` | Gunicorn app on `:8000` (production)                         |
| `telemetry-test` | Gunicorn app on `:6001` (testing)                            |
| `cloudflared`    | Outbound tunnel to Cloudflare; routes hostnames → containers |
| `cron`           | Calls `/instance_manager/clean_instances` every 5 min        |

`cloudflared` dials **out** to Cloudflare's edge, so no inbound ports need to
be open on the host — works behind NAT, CGNAT, or a firewall. Cloudflare
terminates TLS at the edge.

### Prebuilt image

A multi-arch image (`linux/amd64` + `linux/arm64`) is built by GitHub Actions
on every push to `main` and published to **both** registries:

- GHCR: `ghcr.io/autoboat-vt/telemetry_server:latest`
- Docker Hub: `docker.io/vtautoboat/telemetry_server:latest`

Both are public, so `docker compose pull` works without authentication.

### Quick install (cloud VM)

One-liner that installs Docker, clones the repo, configures `.env`, pulls the
prebuilt image, and starts the stack. Works on any Ubuntu/Debian VM (GCP, AWS,
DigitalOcean, etc.):

```bash
curl -fsSL https://raw.githubusercontent.com/autoboat-vt/telemetry_server/main/server_files/quick-install.sh \
  | TUNNEL_TOKEN=eyJ... bash
```

Get the tunnel token from
[Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → Networks →
Tunnels → (your tunnel) → Install.

### Manual install

```bash
git clone https://github.com/autoboat-vt/telemetry_server.git
cd telemetry_server
cp .env.example .env        # set TUNNEL_TOKEN (and DOMAIN, TESTING_DOMAIN)
docker compose pull         # pull prebuilt image (fast)
docker compose up -d        # start the stack
```

To build locally instead of pulling the prebuilt image:

```bash
docker compose up -d --build
```

### First-time Cloudflare setup

Dashboard-managed tunnel (recommended):

1. Go to <https://one.dash.cloudflare.com/> → Networks → Tunnels → Create.
2. Create a tunnel; copy the install token into `.env` as `TUNNEL_TOKEN`.
3. Add public hostnames (Routes) in the dashboard:

   | Hostname                    | Service                    |
   | --------------------------- | -------------------------- |
   | `vt-autoboat-telemetry.uk`  | `http://telemetry-prod:8000`  |
   | `www.vt-autoboat-telemetry.uk` | `http://telemetry-prod:8000` |
   | `test.vt-autoboat-telemetry.uk` | `http://telemetry-test:6001` |

4. DNS CNAMEs are added automatically by Cloudflare.

> **Secret management:** also store the tunnel token as a GitHub
> **organization variable** named `TUNNEL_TOKEN` (org Settings → Actions →
> Variables → New organization variable; set Access to "Selected repositories"
> and pick this repo). Org variables are plaintext, so any team member with
> repo access can read it from the Actions UI when provisioning a new host —
> no need to ping an admin. The trade-off: it is **not** masked, so anyone
> with repo read access can read it; if the repo is ever compromised, rotate
> the token in Cloudflare immediately. In workflows it's referenced as
> `${{ vars.TUNNEL_TOKEN }}` (note: `vars.`, not `secrets.`). When you rotate
> the token in Cloudflare, update **both** the org variable and `.env` on the
> host.

For file-managed mode (manage routing locally instead of in the dashboard),
see `.env.example`.

### Deploying updates

```bash
cd ~/telemetry_server
git pull
docker compose pull telemetry-prod telemetry-test cloudflared
docker compose up -d
```

(The `cron` image is built locally from `server_files/docker/cron/Dockerfile`,
so it isn't pulled from a registry — `docker compose up -d` builds it.)

### Useful commands

```bash
docker compose ps                       # status
docker compose logs -f cloudflared      # tunnel logs
docker compose logs -f telemetry-prod   # app logs
```

## Local Development (no Docker)

### Installation

```bash
pip install -e .
```

### Running the server

1. Production ([Gunicorn](https://gunicorn.org/)):

    ```bash
    gunicorn "autoboat_telemetry_server:create_app()"
    ```

2. Development (Flask):

    ```bash
    flask run
    ```
