---
description: "Use when editing install.sh, .env, .env.example, README.md, or other deployment docs and scripts. Covers the one-shot cloud installer, the .env file and its secret handling, the Cloudflare Tunnel token rotation procedure, the Docker deployment reference (services, routing, first-run setup, persistence, schema changes, useful commands, comparison to install.sh), and the documentation structure."
applyTo: "install.sh, .env.example, README.md, TODO.md"
---

# Deployment & docs — `install.sh`, `.env*`, `README.md`

## `install.sh` — one-shot cloud VM installer

A bash script that:
1. Installs Docker (if missing) via the official Docker apt repo.
2. Clones the repo (or uses the existing checkout if run from one).
3. Writes `.env` from `.env.example` with `TUNNEL_TOKEN` substituted in.
4. Pulls the prebuilt image from GHCR (public, no login needed for the app
   image; the tailscale image is private and needs `docker login ghcr.io`).
5. Brings up the stack with `docker compose up -d`.

Designed to be piped directly from GitHub:
```bash
curl -fsSL https://raw.githubusercontent.com/autoboat-vt/telemetry_server/main/install.sh \
  | TUNNEL_TOKEN=eyJ... bash
```

Or run from an existing checkout:
```bash
bash install.sh
# or
TUNNEL_TOKEN=eyJ... bash install.sh
```

Conventions:
- `set -euo pipefail` — strict mode.
- Color-coded logging helpers: `info` (blue), `ok` (green), `warn` (yellow),
  `err` (red to stderr).
- `run_as_root` — runs as root directly if EUID==0, else `sudo`.
- `detect_docker_command` — uses `docker` if the docker group is active,
  else falls back to `sudo docker` with a warning to `newgrp docker`.
- `require_repo_root` — fails fast if not run from the repo root (checks for
  `docker-compose.yml` and the `docker/` dir).

When modifying:
- Keep the script idempotent — re-running on an existing install should be
  safe (pull, restart, don't clobber `.env` if it exists).
- Don't add interactive prompts. The script must support the
  `curl | bash` pipe form, where stdin is the script itself.
- Use `run_as_root` for anything that needs root — don't call `sudo`
  directly so the EUID==0 case (running as root user) works without sudo.

## `.env` and `.env.example`

`.env` is gitignored (contains the tunnel token). `.env.example` is the
template — keep it in sync with every var that `docker-compose.yml` reads.

Current vars:
- `DOMAIN` — apex domain (default `vt-autoboat-telemetry.uk`).
- `TESTING_DOMAIN` — testing subdomain (default
  `test.vt-autoboat-telemetry.uk`).
- `TUNNEL_TOKEN` — Cloudflare tunnel install token. **Required.** Get from
  Cloudflare Zero Trust → Networks → Tunnels → (tunnel) → Install.
- `USE_CONFIG_FILE` — set to `1` to use `docker/cloudflared/config.yml`
  instead of dashboard-managed routing.
- `TUNNEL_ID` — tunnel UUID, only used in file-managed mode.
- `CORS_ORIGINS` — comma-separated list of allowed origins. Leave blank to
  use the built-in default in
  `src/autoboat_telemetry_server/__init__.py:DEFAULT_CORS_ORIGINS`.

Rules:
- **Never commit `.env`.** It contains the tunnel token. `.gitignore`
  already excludes it.
- **Never print the tunnel token in CI logs.** It's an org variable
  (`vars.TUNNEL_TOKEN`), so it's NOT masked — but don't echo it.
- **When adding a new compose env var**, add it to `.env.example` with a
  comment, and reference it in `docker-compose.yml` with a default
  (`${VAR:-default}`).

## Cloudflare Tunnel token rotation

When rotating the Cloudflare tunnel token:
1. Update the org variable: org Settings → Actions → Variables →
   `TUNNEL_TOKEN` → edit. (Org variables are plaintext, visible to anyone
   with repo read access — trade-off for team self-service.)
2. Update `.env` on the host: `TUNNEL_TOKEN=eyJ...new...`.
3. `docker compose up -d cloudflared` to restart the tunnel with the new
   token.
4. Verify: `docker compose logs -f cloudflared` — look for "Registered
   tunnel connection" lines (usually 4 of them, one per Cloudflare edge
   datacenter).

If `.env` is missing entirely and you just need to bring the stack down:
```bash
TUNNEL_TOKEN=dummy docker compose down
```
The `${TUNNEL_TOKEN:?...}` guard in `docker-compose.yml` would otherwise
block `down` as well as `up`.

## Why a tunnel (history)

Don't reintroduce nginx + certbot. The original `install.sh` used nginx +
certbot HTTP-01, which needs inbound port 80. The domain is proxied through
Cloudflare → edge answers 80, ACME challenge can't reach origin → 522.

We tried DNS-01 (`certbot-dns-cloudflare`). Cert issuance WORKED. But public
traffic still 522 because serving requires inbound 443, which is blocked by
NAT/ISP.

**Lesson:** DNS-01 fixes CERTIFICATE ISSUANCE, not SERVING TRAFFIC. If
inbound ports are blocked, you need a tunnel or other outbound-only
transport regardless of how the cert was obtained.

Cloudflare Tunnel: outbound-only, edge terminates TLS. Solves both cert and
serving in one move. Removed nginx + certbot entirely. See
`/memories/repo/docker_migration.md` for the full history.

## Documentation structure

- `README.md` (repo root) — project overview, project structure, deployment
  quick start, local development, useful commands. Keep the "Project
  Structure" tree in sync with the actual layout.
- `.env.example` — inline documentation for every env var.
- `TODO.md` — open feature ideas. Don't delete entries without checking with
  the maintainer.
- This instruction file — the deep-dive Docker deployment reference
  (services, routing, first-run setup, persistence, schema changes, useful
  commands, comparison to `install.sh`).
- `.github/instructions/tailscale.instructions.md` — tailscale sidecar
  setup, OAuth client, tailnet policy file management, locking down the
  wildcard grant.

When changing infra:
- Update `README.md` and the relevant `.github/instructions/*.instructions.md`
  files in the same PR.
- Update `.env.example` if any env var changes.
- Update the "Project Structure" tree in `README.md` if files move.

## Docker deployment — services and routing

All services run in containers and are orchestrated by Docker Compose.
Traffic reaches the apps through a **Cloudflare Tunnel** (`cloudflared`),
which dials **out** to Cloudflare's edge over a persistent connection. This
means:

- **No inbound ports** need to be open on the host — works behind NAT,
  CGNAT, carrier-grade firewalls, or any network where public inbound is
  blocked.
- **No nginx** — cloudflared forwards requests directly to the app
  containers on the internal Docker network.
- **No certbot / Let's Encrypt** — Cloudflare terminates TLS at its edge and
  presents its own certificate to visitors. No certificate renewal to
  manage.

Services:

| Service         | Container               | Role                                                              |
| --------------- | ----------------------- | ----------------------------------------------------------------- |
| `telemetry-prod`| `telemetry-prod`        | Gunicorn app on port 8000 (production)                            |
| `telemetry-test`| `telemetry-test`        | Gunicorn app on port 6001 (testing)                               |
| `cloudflared`   | `telemetry-cloudflared` | Outbound tunnel to Cloudflare; routes hostnames -> app containers |
| `cron`          | `telemetry-cron`        | Calls `/instance_manager/clean_instances` on prod every 5 minutes |
| `tailscale`     | `telemetry-tailscale`   | Optional. Joins your Tailscale tailnet so you can SSH into the host from anywhere on your tailnet. Opt in with `--profile tailscale`. |

Cloudflare Tunnel routes by **hostname**, not port. Configure the public
hostnames in the Cloudflare Zero Trust dashboard under *Networks → Tunnels
→ (your tunnel) → Public Hostnames*:

| Public hostname                  | Service                   |
| -------------------------------- | ------------------------- |
| `vt-autoboat-telemetry.uk`       | `http://telemetry-prod:8000` |
| `www.vt-autoboat-telemetry.uk`   | `http://telemetry-prod:8000` |
| `test.vt-autoboat-telemetry.uk`  | `http://telemetry-test:6001` |

The DNS CNAMEs pointing these hostnames at the tunnel are created
automatically by the dashboard.

## Docker deployment — first-run setup

1. **Create a Cloudflare Tunnel** (dashboard-managed, recommended):
   - Go to https://one.dash.cloudflare.com/ → *Networks → Tunnels → Create*
   - Name the tunnel (e.g. `autoboat`) and choose **Docker** as the install
     method.
   - Copy the install token shown.
   - Under **Public Hostnames**, add the three routes from the routing table
     above (`vt-autoboat-telemetry.uk`, `www.vt-autoboat-telemetry.uk`, and
     `test.vt-autoboat-telemetry.uk` → the matching `http://telemetry-*:port`
     services).

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # edit .env: set TUNNEL_TOKEN to the token from step 1.
   # DOMAIN and TESTING_DOMAIN are preset; adjust if your domain differs.
   ```

3. **Build and start**:
   ```bash
   docker compose up -d --build
   ```

4. **Verify the tunnel is connected**:
   ```bash
   docker compose logs -f cloudflared
   ```
   You should see `Registered tunnel connection` lines (usually 4 of them).
   Once connected, visits to `https://vt-autoboat-telemetry.uk` reach the
   production app and `https://test.vt-autoboat-telemetry.uk` reaches the
   testing app.

### Alternative: file-managed tunnel

If you'd rather manage routing in `docker/cloudflared/config.yml` than in
the dashboard:

1. Install `cloudflared` locally and run `cloudflared tunnel create autoboat`.
2. Copy the resulting `<UUID>.json` credentials file to
   `docker/cloudflared/<UUID>.json`.
3. In `.env`, set `USE_CONFIG_FILE=1` and `TUNNEL_ID=<UUID>`, and leave
   `TUNNEL_TOKEN` blank.
4. Add DNS CNAMEs:
   ```bash
   cloudflared tunnel route dns autoboat vt-autoboat-telemetry.uk
   cloudflared tunnel route dns autoboat www.vt-autoboat-telemetry.uk
   cloudflared tunnel route dns autoboat test.vt-autoboat-telemetry.uk
   ```
5. `docker compose up -d --build` — routing is now read from `config.yml`.

## Docker deployment — persistence

Named volumes:
- `prod-instance-data` — production SQLite databases (`instances.db`,
  `hashes.db`) and `config.py`.
- `test-instance-data` — testing SQLite databases and `config.py`.
- `cloudflared-creds` — mount point for file-managed tunnel credentials
  (unused in dashboard-managed mode).
- `cron-logs` — output of the `clean_instances` cron job.
- `tailscale-state` — Tailscale daemon state (machine key, node ID).
  Persisted so the container rejoins your tailnet as the same node after
  restarts instead of generating a new node and orphaning the old one.

`docker/app-entrypoint.sh` restores the default `config.py` (baked into the
image at `/opt/config.py`) into the instance volume on first start, then
never overwrites it — so site-specific edits to `config.py` survive
restarts. See `.github/instructions/docker.instructions.md` for the
no-clobber rule.

## Docker deployment — schema changes and the named volumes

There is **no migration framework**. `db.create_all()` only creates missing
tables and indexes on startup — it does not alter existing ones. So
additive schema changes (new columns, new indexes) land automatically on
fresh volumes but **not** on existing `prod-instance-data` /
`test-instance-data` volumes.

For example, indexes on `telemetry_table.updated_at` (used by the
`clean_instances` cron route) and `telemetry_table.instance_identifier`
(used by `get_id/<name>` and the `set_name` uniqueness check) were added in
a recent release. To apply them to an existing volume without losing data:

```bash
docker compose exec telemetry-prod python -c "
from autoboat_telemetry_server import db
from sqlalchemy import text
with db.engine.connect() as conn:
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_telemetry_table_updated_at ON telemetry_table (updated_at)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_telemetry_table_instance_identifier ON telemetry_table (instance_identifier)'))
    conn.commit()
"
```

`docker compose down -v` recreates the volumes from scratch with all
current indexes, but **deletes the SQLite databases** — only do this when
the data is expendable.

## Docker deployment — running the testing branch

By default `telemetry-test` uses the same image as `telemetry-prod`. To run
the `testing` git branch instead, point the `telemetry-test` service at a
separate build context in `docker-compose.yml`:

```yaml
telemetry-test:
  build:
    context: ../telemetry_server_testing
    dockerfile: Dockerfile
  # ... rest unchanged
```

## Docker deployment — useful commands

```bash
docker compose up -d --build       # build + start everything (NOT tailscale)
docker compose --profile tailscale up -d  # also start the tailscale sidecar
docker compose ps                  # service status
docker compose logs -f cloudflared # follow tunnel connection logs
docker compose logs -f telemetry-prod  # follow prod app logs
docker compose logs -f tailscale   # follow tailscale connection logs
docker compose restart cloudflared # reconnect the tunnel
docker compose down                # stop everything (volumes preserved)
docker compose down -v             # stop and DELETE all volumes (DBs!)
```

## Docker deployment — comparison to `install.sh`

| Original (`install.sh`)                     | Docker equivalent                                   |
| ------------------------------------------- | --------------------------------------------------- |
| `apt install nginx supervisor certbot ...`  | `cloudflared` and `cron` service images (no nginx, no certbot) |
| Two venvs + `pip install` per checkout      | One image built from `Dockerfile`, reused for prod  |
| `supervisor` managing both gunicorn procs   | Two `telemetry-prod` / `telemetry-test` containers  |
| `nginx_autoboat_nossl.conf` then `_ssl.conf`| (removed — cloudflared forwards plain HTTP to the app) |
| `certbot --nginx` (HTTP-01) issuance        | (removed — Cloudflare terminates TLS at the edge)   |
| `crontab auto_clean.txt` (system cron)      | `cron` sidecar container running `crond`            |
| `chown`/`chmod` on `src/instance`           | Named volumes + `app-entrypoint.sh`                 |

## TUNNEL_TOKEN as a GitHub org variable

Stored as an ORGANIZATION VARIABLE named `TUNNEL_TOKEN` (NOT a secret):
org Settings → Actions → Variables → New organization variable. Access
scoped to "Selected repositories" → this repo only.

Org variables are PLAINTEXT (visible in Actions UI to anyone with read
access to a shared repo). Chosen over a secret so any team member can grab
the token when provisioning a new host. Trade-off: NOT masked, so a
compromised repo = compromised token → rotate immediately.

In workflows referenced as `${{ vars.TUNNEL_TOKEN }}` (note: `vars.`, NOT
`secrets.`).

The host still reads the token from `.env` at runtime — the GitHub var does
NOT reach the host automatically (host behind NAT, no SSH from runners).

See `/memories/repo/tunnel_token_secret.md` for the considered-and-rejected
alternatives (repo secret, moving cloudflared off the boat).
