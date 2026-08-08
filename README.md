# Autoboat Telemetry Server

A lightweight Flask-based web server to collect, display, and manage telemetry data from the Virginia Tech Autoboat project.

## Project Structure

```txt
src/autoboat_telemetry_server/    # Flask app (factory, models, types, lock manager, routes/)
src/instance/                     # config.py + SQLite DBs (instances.db, hashes.db)
install.sh                        # One-shot cloud VM installer
docker/                           # app-entrypoint.sh, cloudflared/, cron/, tailscale/
docker-compose.yml                # telemetry-prod, telemetry-test, cloudflared, cron, tailscale
.github/workflows/                # build.yml (test + per-arch build), push.yml (publish), tailscale.yml, citation.yml
```

## Deployment (Docker + Cloudflare Tunnel)

The production stack runs as four Docker Compose services (plus an optional
`tailscale` sidecar):

| Service          | Purpose                                                      |
| ---------------- | ------------------------------------------------------------ |
| `telemetry-prod` | Gunicorn app on `:8000` (production)                         |
| `telemetry-test` | Gunicorn app on `:6001` (testing)                            |
| `cloudflared`    | Outbound tunnel to Cloudflare; routes hostnames → containers |
| `cron`           | Calls `/instance_manager/clean_instances` every 5 min        |
| `tailscale`      | Optional (`--profile tailscale`). Joins your Tailscale tailnet so you can SSH into the container from anywhere on your tailnet. See [.github/instructions/tailscale.instructions.md](.github/instructions/tailscale.instructions.md). |

`cloudflared` dials **out** to Cloudflare's edge, so no inbound ports need to be
open on the host — works behind NAT, CGNAT, or a firewall. Cloudflare terminates
TLS at the edge.

### Prebuilt image

A multi-arch image (`linux/amd64` + `linux/arm64`) is built by GitHub Actions on
every push to `main` and published to **both** registries:

- GHCR: `ghcr.io/autoboat-vt/telemetry_server:latest`
- Docker Hub: `docker.io/vtautoboat/telemetry_server:latest`

Both are public, so `docker compose pull` works without authentication.

### Quick install (cloud VM)

One-liner that installs Docker, clones the repo, configures `.env`, pulls the
prebuilt image, and starts the stack. Works on any Ubuntu/Debian VM:

```bash
curl -fsSL https://raw.githubusercontent.com/autoboat-vt/telemetry_server/main/install.sh \
  | TUNNEL_TOKEN=eyJ... bash
```

Get the tunnel token from
[Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → Networks → Tunnels →
(your tunnel) → Install.

From an existing checkout:

```bash
bash install.sh             # or: TUNNEL_TOKEN=eyJ... bash install.sh
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

   | Hostname                        | Service                      |
   | ------------------------------- | ---------------------------- |
   | `vt-autoboat-telemetry.uk`      | `http://telemetry-prod:8000` |
   | `www.vt-autoboat-telemetry.uk`  | `http://telemetry-prod:8000` |
   | `test.vt-autoboat-telemetry.uk` | `http://telemetry-test:6001` |

4. DNS CNAMEs are added automatically by Cloudflare.

Also store the token as a GitHub **organization variable** named `TUNNEL_TOKEN`
(scoped to this repo) so team members can grab it from the Actions UI when
provisioning a new host. It's plaintext (not masked) — referenced in workflows
as `${{ vars.TUNNEL_TOKEN }}`. When rotating, update **both** the org variable
and `.env` on the host. Full rotation procedure and trade-offs:
`.github/instructions/deployment-docs.instructions.md`.

For file-managed tunnel mode (routing in `docker/cloudflared/config.yml` instead
of the dashboard), see `.env.example`.

### Deploying updates

```bash
git pull
docker compose pull telemetry-prod telemetry-test cloudflared
docker compose up -d
```

### Workflow split

- [build.yml](.github/workflows/build.yml) — lint + pytest gate, then per-arch Docker build (push only).
- [push.yml](.github/workflows/push.yml) — assembles multi-arch manifests and publishes to GHCR + Docker Hub.
- `testing` is the staging branch; `main` is production.

### Useful commands

```bash
docker compose ps                       # status
docker compose logs -f cloudflared      # tunnel logs
docker compose logs -f telemetry-prod   # app logs
```

## Local Development (no Docker)

```bash
pip install -e ".[dev]"          # install with dev extras (ruff, pytest)
gunicorn "autoboat_telemetry_server:create_app()"   # production-like
flask run                       # development (auto-reload)
```

Lint and test:

```bash
ruff check .
ruff format --check .
pytest
```
