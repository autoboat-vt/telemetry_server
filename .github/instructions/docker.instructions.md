---
description: "Use when editing Dockerfiles, docker-compose.yml, or scripts under docker/. Covers the app image layout, the named-volume config.py restore dance, the cloudflared distroless constraint, the cron image, and the tailscale OAuth-baked image."
applyTo: "Dockerfile, docker-compose.yml, docker/**, .dockerignore"
---

# Docker — `Dockerfile`, `docker-compose.yml`, `docker/`

## The app image (`Dockerfile` at repo root)

Base: `python:3.12-slim`. Creates an `ubuntu` user (matching the original
supervisor-based deployment) and lays the source out under
`/home/ubuntu/telemetry_server` because `create_app()` discovers the instance
dir by scanning `/home` for a single user dir.

Key steps:
1. `useradd -m ubuntu`, install `curl` (used by healthchecks / cron).
2. `WORKDIR /home/ubuntu/telemetry_server` — created as root, so `chown -R
   ubuntu:ubuntu` BEFORE `USER ubuntu` or venv creation fails with EACCES.
3. `COPY pyproject.toml README.md ./` and `COPY src/ ./src/`.
4. `COPY migrations/ ./migrations/` — the Alembic env + versions, so the
   entrypoint can run `flask db upgrade`.
5. Back up `src/instance/config.py` to `/opt/config.py` — the entrypoint
   restores it into the named volume on first start.
6. `USER ubuntu`, build venv at `/home/ubuntu/telemetry_server/venv`, `pip
   install .`.
7. `USER root`, copy `docker/app-entrypoint.sh` to `/opt/`, `chmod +x`.
8. `USER ubuntu`, `EXPOSE 8000`, `ENTRYPOINT ["/opt/app-entrypoint.sh"]`,
   `CMD [...gunicorn -w 1 --bind 0.0.0.0:8000 "autoboat_telemetry_server:create_app()"]`.

Rules:
- **Don't rename `ubuntu`** or add a second `/home/*` user — breaks
  `INSTANCE_DIR` discovery.
- **Don't switch to multi-stage builds** that drop the `ubuntu` user — same
  reason.
- **Keep `gunicorn -w 1`** — the in-process `ReaderWriterLock` doesn't
  serialize across workers. Raising the worker count on SQLite will cause
  torn reads / lost updates.
- **`/opt/config.py` is the only thing the entrypoint reads from the image.**
  Don't add other runtime files to `/opt` without updating the entrypoint.

## The entrypoint (`docker/app-entrypoint.sh`)

```bash
# A named volume is mounted over the instance directory to persist the SQLite
# databases across restarts. On first start the mounted directory is empty, so
# restore the default config.py baked into the image (no-clobber: never
# overwrite an existing user-configured config.py).
if [ ! -f "$INSTANCE_DIR/config.py" ]; then
    cp /opt/config.py "$INSTANCE_DIR/config.py"
fi
export PATH="/home/ubuntu/telemetry_server/venv/bin:$PATH"
export FLASK_APP="autoboat_telemetry_server:create_app()"
# Apply pending Alembic migrations before starting gunicorn. No-op if the DB
# is already at head. (Existing volumes that predate Alembic need a one-time
# `flask db stamp head` first — see deployment-docs.instructions.md.)
flask db upgrade
exec "$@"
```

**No-clobber is critical.** Site-specific edits to `config.py` must survive
image updates. Never change this to an unconditional `cp`.

**`flask db upgrade` runs on every start.** If the DB is already at head,
Alembic detects the `alembic_version` row and the call is a no-op. If a
volume predates Alembic (no `alembic_version` row), the initial migration
will fail with `table already exists` — the operator must run
`docker compose exec telemetry-prod flask db stamp head` once first. See
`.github/instructions/deployment-docs.instructions.md` → "Migrations and
the named volumes".

## docker-compose.yml services

| Service | Image | Container | Notes |
| --- | --- | --- | --- |
| `telemetry-prod` | `ghcr.io/autoboat-vt/telemetry_server:latest` | `telemetry-prod` | Gunicorn `:8000`. `prod-instance-data` volume over `src/instance`. |
| `telemetry-test` | `ghcr.io/autoboat-vt/telemetry_server:testing` | `telemetry-test` | Override `command:` binds `:6001`. `test-instance-data` volume. |
| `cloudflared` | `cloudflare/cloudflared:latest` | `telemetry-cloudflared` | Distroless. Override `command:` only. |
| `cron` | built locally from `docker/cron/Dockerfile` | `telemetry-cron` | No registry image. `docker compose pull` skips it; `up -d` builds it. |
| `tailscale` | `ghcr.io/autoboat-vt/telemetry_server-tailscale:latest` | `telemetry-tailscale` | `profiles: [tailscale]` — opt-in. Host networking, root user. **Image is private on GHCR.** |

Both app services set `PATH` and `VIRTUAL_ENV` env vars explicitly so the
override `command:` (which uses the absolute venv path) resolves gunicorn.

## cloudflared

The `cloudflare/cloudflared:latest` image is **distroless** (no `/bin/sh`).
- Don't try to `docker exec` into it.
- Don't write a shell entrypoint wrapper (the legacy
  `docker/cloudflared/entrypoint.sh` is unused for this reason).
- Override `command:` in compose directly. Default:
  `tunnel run --token ${TUNNEL_TOKEN:?TUNNEL_TOKEN is required. See .env.example}`.
- The `${TUNNEL_TOKEN:?...}` guard fails fast if `.env` is missing — but it
  also blocks `docker compose down`. Override with
  `TUNNEL_TOKEN=dummy docker compose down`.

Routing is configured in the Cloudflare Zero Trust dashboard (recommended,
dashboard-managed) or in `docker/cloudflared/config.yml` (file-managed,
`USE_CONFIG_FILE=1` + `TUNNEL_ID`). The three public hostnames:

| Hostname | Service |
| --- | --- |
| `vt-autoboat-telemetry.uk` | `http://telemetry-prod:8000` |
| `www.vt-autoboat-telemetry.uk` | `http://telemetry-prod:8000` |
| `test.vt-autoboat-telemetry.uk` | `http://telemetry-test:6001` |

Tunnels route by **hostname**, not port — that's why `test` is a subdomain
instead of `:8443`.

## cron

`docker/cron/Dockerfile`: Alpine + curl + crond.
`docker/cron/cron-entrypoint.sh`: every 5 min, `curl -X DELETE
http://telemetry-prod:8000/instance_manager/clean_instances`. The route
deletes instances older than 5 min (i.e. not marked for keeping). Don't
shorten the interval without checking the route's age cutoff.

## tailscale (opt-in profile)

Key points (full deep-dive in `.github/instructions/tailscale.instructions.md`):

- `profiles: [tailscale]` — does NOT start with `docker compose up -d`.
  Enable with `docker compose --profile tailscale up -d`.
- `network_mode: host` — the tailscale interface lives on the host directly,
  so SSH to the tailnet IP routes to the host's sshd. This sidesteps the
  entire `TS_DEST_IP` + "IP forwarding must be enabled" error chain. Do NOT
  switch back to bridge networking for this service.
- `user: "0:0"` — run as root. The upstream image defaults to non-root
  `tailscale`, which auto-enables userspace networking (conflicts with host
  networking).
- `TS_USERSPACE: "false"` — explicitly disable userspace networking.
- `TS_EXTRA_ARGS: --advertise-tags=tag:server --ssh` — OAuth-registered nodes
  must be tagged; `--ssh` enables Tailscale's built-in SSH server in the
  container.
- Mounts `/dev/net/tun`, needs `cap_add: [NET_ADMIN, NET_RAW]`.
- DO NOT use `sysctls: net.ipv4.ip_forward=1` with `network_mode: host` —
  Docker rejects it ("sysctl not allowed in host network namespace"). The
  host already has ip_forward enabled.
- `tailscale-state` named volume persists daemon state so the container
  rejoins as the same node after restarts.

## The custom tailscale image (`docker/tailscale/Dockerfile`)

`FROM tailscale/tailscale:latest`, takes `TS_CLIENT_ID` and `TS_OAUTH_SECRET`
as build ARGs, and **bakes the OAuth secret into `TS_AUTHKEY` as an ENV** —
NOT `TS_CLIENT_SECRET`. This is a workaround for a containerboot v1.98 bug
where `TS_CLIENT_ID` + `TS_CLIENT_SECRET` causes a 403 on `check-prefs`
before OAuth auth completes. Per Tailscale docs, an OAuth client secret is
accepted in `TS_AUTHKEY` as long as you also pass `--advertise-tags=tag:<tag>`.

**CRITICAL:** do NOT also set `TS_CLIENT_ID` in the image. containerboot
explicitly rejects: "TS_AUTHKEY cannot be used with TS_CLIENT_ID,
TS_CLIENT_SECRET, TS_ID_TOKEN, or TS_AUDIENCE".

**SECURITY:** the resulting image contains the OAuth client secret baked in.
It MUST stay **Internal** visibility on GHCR (org members only). Never make
it Public, never mirror it to Docker Hub. Hosts must `docker login ghcr.io`
with a PAT (`read:packages` scope) before
`docker compose --profile tailscale pull`.

Hadolint/Docker linter will warn "Sensitive data should not be used in
ARG/ENV" — expected and accepted here, mitigated by the private image.

## .dockerignore

Excludes `.git`, `.github`, `.vscode`, caches, build artifacts, `venv/`,
`/instance/` (repo-root stray), logs, and most of `docker/`. Keeps
`docker/app-entrypoint.sh` (the Dockerfile `COPY`s it) via a `!` exception.
If you add a new file under `docker/` that the app image needs, update
`.dockerignore`'s `!docker/...` line.

The `cron/`, `cloudflared/`, and `tailscale/` subpaths are excluded
from the app image (they have their own contexts or aren't needed).
