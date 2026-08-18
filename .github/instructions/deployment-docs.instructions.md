---
description: "Use when editing install.sh, .env, .env.example, README.md, or other deployment docs and scripts. Covers the one-shot cloud installer, the .env file and its secret handling, the Cloudflare Tunnel token rotation procedure, the Docker deployment reference (services, routing, first-run setup, persistence, migrations / the `flask db stamp head` procedure, useful commands, comparison to install.sh), and the documentation structure."
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
serving in one move. Removed nginx + certbot entirely.

### Historical nginx/certbot-era gotchas (reference only)

These are from the pre-tunnel `install.sh` era and are kept for context in
case anyone considers reintroducing nginx + certbot. **Don't** — the tunnel
is strictly better here.

- nginx loads ALL `*.conf` in `/etc/nginx/conf.d` — don't mount both an
  http and an ssl template there. Mount templates to `/opt/nginx` and have
  the entrypoint copy the right one to `default.conf`.
- The `certbot/certbot` base image has `ENTRYPOINT=["certbot"]`. Use
  `--entrypoint sh -c '...'` or the first arg gets duplicated.
- Let's Encrypt rate limit: 5 failed authorizations per identifier per
  hour. Use `--staging` to validate the flow without hitting prod rate
  limits.
- The certbot entrypoint MUST NOT use `set -e` — a failed issuance should
  retry with backoff, not crash-loop (which hammers the rate-limited
  endpoint).

### End-to-end validation (tunnel)

When the tunnel is up, you should see `Registered tunnel connection` lines
in `docker compose logs cloudflared` (usually 4 of them, one per Cloudflare
edge region). All three public hostnames should return HTTP 200:

- `https://vt-autoboat-telemetry.uk` → `telemetry-prod:8000`
- `https://www.vt-autoboat-telemetry.uk` → `telemetry-prod:8000`
- `https://test.vt-autoboat-telemetry.uk` → `telemetry-test:6001`

Debugging routing issues:
- `docker compose logs telemetry-cloudflared | grep "Updated to new
  configuration"` shows the live ingress config the dashboard pushed — use
  it to verify the service URLs (port AND container name) are correct.
  Historical typos: `www -> telemetry-prod:8001` (should be `:8000`),
  `test -> telemetry-prod:6001` (should be `telemetry-test:6001`).
- New DNS records for tunnel subdomains may take a few min to propagate to
  local resolvers. If `curl` fails with "Could not resolve host" but
  `dig @julio.ns.cloudflare.com <host>` returns the Cloudflare proxy IPs,
  it's just propagation — pin with `curl --resolve host:443:<ip>` to verify
  the tunnel itself works.
- The apex domain shows A records (not CNAME) even after tunnel routing is
  configured — Cloudflare uses CNAME flattening for the apex, so it
  appears as A records pointing at Cloudflare's proxy IPs. This is
  expected and correct.

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

## Migrations and the named volumes

Schema migrations are managed with **Flask-Migrate** (Alembic). The
`docker/app-entrypoint.sh` script runs `flask db upgrade` before starting
gunicorn on every container start, so pending migrations apply automatically
on `docker compose up -d` / restarts / image pulls. If the DB is already at
head, `upgrade` is a no-op.

`create_app()` does NOT call `db.create_all()` in production (only the
pytest fixtures use it, for throwaway test DBs). Migrations are the only
path that creates tables in production.

### One-time `stamp head` for volumes that predate Alembic

If a `prod-instance-data` / `test-instance-data` volume was created before
the Flask-Migrate integration shipped, it has the tables (from the old
`db.create_all()` startup path) but NO `alembic_version` row. On the first
deploy with the new image, `flask db upgrade` will try to run the initial
migration and fail with `table telemetry_table already exists`.

The fix is to stamp the DB at the current head once, which tells Alembic
"this DB is already at head, don't run the initial migration":

```bash
docker compose exec telemetry-prod flask db stamp head
docker compose exec telemetry-test  flask db stamp head
```

After stamping, subsequent `docker compose up -d` will see the DB at head
and skip migrations. This is a one-time step per volume.

### Adding a new migration (developer flow)

On a checkout with a local instance dir (or against a throwaway DB):

```bash
flask db migrate -m "add foo column to telemetry_table"
```

This autogenerates a migration file in `migrations/versions/`. **Caveat:**
autogenerate only diffs the **default bind** (None). If the change affects
`HashTable` (the `hashes` bind), add the `op.*` calls for the hashes bind
by hand — see `migrations/versions/0001_initial_schema.py` for the
`_bind_key()` / `_default_bind()` / `_hashes_bind()` pattern (the helpers
are inlined because Alembic's `load_python_file` bypasses the package
import system).

Then inspect the generated file (autogenerate is not perfect, especially
for JSON columns wrapped with `MutableDict.as_mutable`), and apply it:

```bash
flask db upgrade
```

Prefer additive changes (new columns with defaults, new tables, new
indexes) — they're forward-compatible and don't require a downgrade path.

### Destructive reset (loses data)

`docker compose down -v` recreates the volumes from scratch. On the next
`docker compose up -d`, the entrypoint's `flask db upgrade` will run the
initial migration against the empty DBs, creating all tables with current
indexes. Only do this when the data is expendable.

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
When rotating the Cloudflare tunnel token, update BOTH the org variable AND
`.env` on the host. (The `.env.example` `TUNNEL_TOKEN` comment and the
README "First-time Cloudflare setup" section document this.)

### Considered and rejected

- **Repo secret (`secrets.TUNNEL_TOKEN`):** masked, but admin-only
  visibility — bad for team self-service provisioning (any team member
  provisioning a new host needs to grab the token).
- **Moving cloudflared off the boat** (Tailscale + cloud VM + SSH deploy
  workflow): fully decouples the token from the host but adds 2 hosts + a
  VPN mesh + new failure modes. Not worth it for current needs.

### CI: native multi-arch builds (`build.yml`)

The pattern (adapted from `autoboat-vt/autoboat_vt`'s
`build-and-release.yml`) is a 2-job structure:

- `build` job: matrix of `amd64` on `ubuntu-22.04` + `arm64` on
  `ubuntu-22.04-arm` (native ARM runner). Each pushes per-arch suffixed
  tags (`:main-amd64`, `:main-arm64`, `:latest-amd64`, etc.).
- `publish` job: combines per-arch tags into multi-arch manifests via
  `docker buildx imagetools create`. Runs only when not a PR.

Tag logic is computed in bash (NOT `docker/metadata-action`), mirroring
`autoboat_vt`:

- branch push → `:<branch>` (`main` also gets `:latest`)
- `v1.2.3` tag → `:1.2.3`, `:1.2`, `:1`, `:latest`

Per-arch GHA cache uses `scope=amd64` / `scope=arm64`. Push is gated on
`${{ github.event_name != 'pull_request' }}` so PR builds are cache-only.
If `ubuntu-22.04-arm` is unavailable, swap the arm64 runner to
`ubuntu-22.04` and add a `setup-qemu` step (slower but functional).

**BUG FIX — `build-push-action` `tags:` must be FULL image references:**
The `tags:` input to `docker/build-push-action` expects `repo:tag`, not
bare tag names. The bash step that computes tags must emit e.g.
`ghcr.io/owner/repo:main-amd64` and `vtautoboat/repo:main-amd64` on
separate lines — NOT just `main-amd64`. Bare names get interpreted as
`docker.io/library/<name>` → push fails with `insufficient_scope:
authorization failed` / `repository does not exist`.
`docker/metadata-action` does this implicitly via its `images:` list; if
you drop `metadata-action`, you must prepend the repo yourself.

See `.github/instructions/github-actions.instructions.md` for the full
workflow reference (test gate, GHCR cleanup, citation bump).
