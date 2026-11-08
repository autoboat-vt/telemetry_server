# Telemetry Server

A lightweight Flask-based web server to collect, display, and manage telemetry data.

## Project Structure

```txt
src/autoboat_telemetry_server/    # Flask app (factory, models, types, lock manager, routes/)
src/instance/                     # config.py + SQLite DBs (instances.db, hashes.db)
install.sh                        # One-shot cloud VM installer
docker/                           # app-entrypoint.sh, cron/, prometheus/, tailscale/
docker-compose.yml                # telemetry-prod, telemetry-test, cloudflared, cron, prometheus, tailscale
.github/workflows/                # build.yml (test + per-arch build), push.yml (publish), tailscale.yml, citation.yml
```

## Deployment (Docker + Cloudflare Tunnel)

The production stack runs as five Docker Compose services (plus an optional `tailscale` sidecar):

| Service          | Purpose                                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `telemetry-prod` | Gunicorn app on `:8000` (production)                                                                                            |
| `telemetry-test` | Gunicorn app on `:6001` (testing)                                                                                               |
| `cloudflared`    | Outbound tunnel to Cloudflare; routes hostnames → containers                                                                    |
| `cron`           | Calls `/instance_manager/clean_instances` every 5 min                                                                           |
| `prometheus`     | Scrapes `/metrics` from both apps (no published host port)                                                                      |
| `tailscale`      | Optional (`--profile tailscale`). Joins your Tailscale tailnet so you can SSH into the container from anywhere on your tailnet. |

`cloudflared` is used to expose the internal services to the public Internet via a [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel). The tunnel is managed via the Cloudflare dashboard, so you can add/remove public hostnames (routes) without touching the container.

### Prebuilt image

A multi-arch image (`linux/amd64` + `linux/arm64`) is built by GitHub Actions on
every push to `main` and published to both registries:

- GHCR: `ghcr.io/autoboat-vt/telemetry_server:latest`
- Docker Hub: `docker.io/vtautoboat/telemetry_server:latest`

Both are public, so `docker compose pull` works without authentication.

### Quick Install

One-liner that installs Docker, clones the repo, configures `.env`, pulls the
prebuilt image, and starts the stack. Works on any Ubuntu/Debian VM:

```bash
curl -fsSL https://raw.githubusercontent.com/autoboat-vt/telemetry_server/main/install.sh | bash
```

Get the tunnel token from
[Cloudflare Zero Trust](https://one.dash.cloudflare.com/) -> Networks -> Tunnels -> (your tunnel) -> Install.

To build locally instead of pulling the prebuilt image:

```bash
git clone https://github.com/autoboat-vt/telemetry_server.git
cd telemetry_server && docker compose up -d --build
```

### First-time Cloudflare setup

Dashboard-managed tunnel (recommended):

1. Go to <https://one.dash.cloudflare.com/> -> Networks -> Tunnels -> Create.
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
and `.env` on the host.

### Deploying updates

```bash
git pull
docker compose pull telemetry-prod telemetry-test cloudflared prometheus
docker compose up -d
```

Images are pinned to a service list on purpose: `cron` is built locally from
`docker/cron/Dockerfile` and has no registry image, so a bare
`docker compose pull` fails with `pull access denied for telemetry-cron`.
Use `docker compose pull --ignore-buildable` if you'd rather not enumerate.

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

### Metrics (Prometheus + Grafana Cloud)

The `prometheus` service scrapes `/metrics` from both app containers every 60s
and `remote_write`s everything to Grafana Cloud. It publishes **no host port**
and has no cloudflared route, so its UI is not publicly reachable.

**The Grafana token is a secret and is not in git.** `prometheus.yml` is a
tracked file, so the token lives in a separate gitignored file that the config
reads via `password_file`:

```bash
# on the host, once:
printf '%s' 'glc_...' > docker/prometheus/grafana_token
chmod 600 docker/prometheus/grafana_token
```

`docker-compose.yml` binds that file to `/etc/prometheus/grafana_token` inside
the container. Rotate the token in Grafana Cloud -> Access Policies, then update
the file and `docker compose restart prometheus`.

Verify scraping and remote write:

```bash
docker compose exec prometheus wget -qO- localhost:9090/-/healthy
docker compose exec prometheus wget -qO- 'localhost:9090/api/v1/targets?state=active'
# remote write should show samples sent, 0 failed, 0 pending:
docker compose exec prometheus wget -qO- localhost:9090/metrics |
  grep 'prometheus_remote_storage_samples_\(total\|failed\|pending\)'
```

`telemetry-test` may report `health=down`: the `:testing` image is built from
the `testing` branch and can lag `main`. If it predates `observability.py` it has
no `/metrics` route and returns 404 — a stale image, not a config bug. Rebuild
with `docker compose up -d --build telemetry-test`.

Note that the `prometheus` job scrapes Prometheus itself, not a node exporter.
For host CPU/RAM/disk you'd need a `node-exporter` service plus a job targeting
`node-exporter:9100`.

#### Exposed metrics

HTTP (all label `path` with the Flask rule, never the raw URL, to keep
cardinality bounded):

| Metric                          | Type      | Labels                        | Meaning                          |
| ------------------------------- | --------- | ----------------------------- | -------------------------------- |
| `http_requests_total`           | counter   | `method`, `path`, `status`    | Requests by outcome              |
| `http_request_duration_seconds` | histogram | `method`, `path`              | Request latency                  |
| `http_request_bytes_total`      | counter   | `method`, `path`              | Inbound body bytes               |
| `http_response_bytes_total`     | counter   | `method`, `path`              | Outbound body bytes              |
| `http_exceptions_total`         | counter   | `method`, `path`, `exception` | Unhandled exceptions             |
| `http_429_total`                | counter   | —                             | Write-lock contention rejections |

Database (fed by SQLAlchemy `before/after_cursor_execute` hooks on every bind):

| Metric                      | Type      | Labels      | Meaning                                    |
| --------------------------- | --------- | ----------- | ------------------------------------------ |
| `db_queries_total`          | counter   | `operation` | Statements by verb (`SELECT`, `INSERT`, …) |
| `db_query_duration_seconds` | histogram | `operation` | Statement latency                          |

Domain:

| Metric                          | Type      | Labels     | Meaning                                          |
| ------------------------------- | --------- | ---------- | ------------------------------------------------ |
| `boat_status_payload_bytes`     | histogram | `encoding` | Decoded payload size (`json` / `binary`)         |
| `images_uploaded_total`         | counter   | —          | Images received (includes de-duplicated uploads) |
| `image_bytes_received_total`    | counter   | —          | Raw image payload bytes received                 |
| `clean_instances_deleted_total` | counter   | —          | Instances reaped by the cron route               |

State gauges (re-read from the DB on every scrape, so they never go stale):

| Metric                  | Meaning                                  |
| ----------------------- | ---------------------------------------- |
| `instances_total`       | Live telemetry instances                 |
| `config_hashes_total`   | Stored autopilot-parameter config hashes |
| `images_stored_total`   | Distinct images stored                   |
| `image_storage_bytes`   | Total stored image payload bytes         |
| `telemetry_server_info` | Constant `1`, labeled with `version`     |

Gauges refresh inside a per-gauge try/except: if the DB is unavailable the
endpoint still returns 200 with the counters intact, rather than 500-ing the one
endpoint meant to report ill health.

## Local Development (no Docker)

```bash
pip install -e ".[dev]"
gunicorn "autoboat_telemetry_server:create_app()"
flask run
```

Lint and test:

```bash
ruff check .
ruff format --check .
pytest
```
