# Docker Deployment

This directory contains a Docker-based deployment that replaces the original
host-installed stack in `install.sh` (nginx + supervisor + certbot
+ cron). All services run in containers and are orchestrated by Docker Compose.

Traffic reaches the apps through a **Cloudflare Tunnel** (`cloudflared`), which
dials **out** to Cloudflare's edge over a persistent connection. This means:

- **No inbound ports** need to be open on the host — works behind NAT, CGNAT,
  carrier-grade firewalls, or any network where public inbound is blocked.
- **No nginx** — cloudflared forwards requests directly to the app containers
  on the internal Docker network.
- **No certbot / Let's Encrypt** — Cloudflare terminates TLS at its edge and
  presents its own certificate to visitors. No certificate renewal to manage.

## Services

| Service         | Container               | Role                                                              |
| --------------- | ----------------------- | ----------------------------------------------------------------- |
| `telemetry-prod`| `telemetry-prod`        | Gunicorn app on port 8000 (production)                            |
| `telemetry-test`| `telemetry-test`        | Gunicorn app on port 6001 (testing)                               |
| `cloudflared`   | `telemetry-cloudflared` | Outbound tunnel to Cloudflare; routes hostnames -> app containers |
| `cron`          | `telemetry-cron`        | Calls `/instance_manager/clean_instances` on prod every 5 minutes |

## Routing (configured in the Cloudflare dashboard)

Cloudflare Tunnel routes by **hostname**, not port. Configure the public
hostnames in the Cloudflare Zero Trust dashboard under
*Networks → Tunnels → (your tunnel) → Public Hostnames*:

| Public hostname                  | Service                   |
| -------------------------------- | ------------------------- |
| `vt-autoboat-telemetry.uk`       | `http://telemetry-prod:8000` |
| `www.vt-autoboat-telemetry.uk`   | `http://telemetry-prod:8000` |
| `test.vt-autoboat-telemetry.uk`  | `http://telemetry-test:6001` |

The DNS CNAMEs pointing these hostnames at the tunnel are created
automatically by the dashboard.

> **Why a tunnel instead of nginx + certbot?** The original `install.sh`
> (and an earlier iteration of this Docker setup) used nginx + certbot with
> Let's Encrypt. That requires inbound port 443 (or 80 for HTTP-01) to be
> reachable from the internet. When the host is behind NAT / a firewall that
> blocks inbound, Cloudflare's edge gets a 522 trying to reach the origin.
> DNS-01 fixes *certificate issuance* but not *serving traffic*. A Cloudflare
> Tunnel fixes both: the tunnel is a single outbound connection, and
> Cloudflare terminates TLS at the edge.

## Files

```
Dockerfile                        # Python app image (gunicorn)
docker-compose.yml                # Orchestrates all 4 services
.env.example                      # DOMAIN / TESTING_DOMAIN / TUNNEL_TOKEN defaults
.dockerignore                     # Excludes build artifacts from image context
docker/
  app-entrypoint.sh               # Restores config.py into the mounted instance volume
  cloudflared/
    entrypoint.sh                 # Runs cloudflared in dashboard- or file-managed mode
    config.yml                    # Used only in file-managed mode (USE_CONFIG_FILE=1)
  cron/
    Dockerfile                    # Alpine + curl
    cron-entrypoint.sh            # crond hitting the prod app every 5 min
```

## First-run setup

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

If you'd rather manage routing in `docker/cloudflared/config.yml`
than in the dashboard:

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

## Persistence

- `prod-instance-data` — production SQLite databases (`instances.db`,
  `hashes.db`) and `config.py`
- `test-instance-data` — testing SQLite databases and `config.py`
- `cloudflared-creds` — mount point for file-managed tunnel credentials
  (unused in dashboard-managed mode)
- `cron-logs` — output of the `clean_instances` cron job

The `app-entrypoint.sh` script restores the default `config.py` (baked into
the image at `/opt/config.py`) into the instance volume on first start, then
never overwrites it — so site-specific edits to `config.py` survive restarts.

## Running the testing branch

By default `telemetry-test` uses the same image as `telemetry-prod`. To run the
`testing` git branch instead, point the `telemetry-test` service at a separate
build context in `docker-compose.yml`:

```yaml
telemetry-test:
  build:
    context: ../telemetry_server_testing
    dockerfile: Dockerfile
  # ... rest unchanged
```

## Useful commands

```bash
docker compose up -d --build       # build + start everything
docker compose ps                  # service status
docker compose logs -f cloudflared # follow tunnel connection logs
docker compose logs -f telemetry-prod  # follow prod app logs
docker compose restart cloudflared # reconnect the tunnel
docker compose down                # stop everything (volumes preserved)
docker compose down -v             # stop and DELETE all volumes (DBs!)
```

## Comparison to `install.sh`

| Original (`install.sh`)                     | Docker equivalent                                   |
| ------------------------------------------- | --------------------------------------------------- |
| `apt install nginx supervisor certbot ...`  | `cloudflared` and `cron` service images (no nginx, no certbot) |
| Two venvs + `pip install` per checkout      | One image built from `Dockerfile`, reused for prod  |
| `supervisor` managing both gunicorn procs   | Two `telemetry-prod` / `telemetry-test` containers  |
| `nginx_autoboat_nossl.conf` then `_ssl.conf`| (removed — cloudflared forwards plain HTTP to the app) |
| `certbot --nginx` (HTTP-01) issuance        | (removed — Cloudflare terminates TLS at the edge)   |
| `crontab auto_clean.txt` (system cron)      | `cron` sidecar container running `crond`            |
| `chown`/`chmod` on `src/instance`           | Named volumes + `app-entrypoint.sh`                 |
