---
description: "Use when editing install.sh, .env, .env.example, README.md, docker/README.md, or other deployment docs and scripts. Covers the one-shot cloud installer, the .env file and its secret handling, the Cloudflare Tunnel token rotation procedure, and the documentation structure."
applyTo: "install.sh, .env.example, README.md, docker/README.md, TODO.md"
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
- `docker/README.md` — full Docker deployment docs: services table, routing
  table, file structure, first-run setup, file-managed tunnel mode,
  tailscale sidecar, tailnet policy file management, useful commands,
  locking down the wildcard grant. This is the deep-dive doc.
- `.env.example` — inline documentation for every env var.
- `TODO.md` — open feature ideas. Don't delete entries without checking with
  the maintainer.

When changing infra:
- Update `README.md` AND `docker/README.md` in the same PR.
- Update `.env.example` if any env var changes.
- Update the "Project Structure" tree in `README.md` if files move.

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
