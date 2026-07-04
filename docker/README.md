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
| `tailscale`     | `telemetry-tailscale`   | Optional. Joins your Tailscale tailnet so you can SSH into the host from anywhere on your tailnet. Opt in with `--profile tailscale`. |

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
- `tailscale-state` — Tailscale daemon state (machine key, node ID). Persisted
  so the container rejoins your tailnet as the same node after restarts
  instead of generating a new node and orphaning the old one.

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

## SSH access via Tailscale (optional)

The `tailscale` service is **opt-in** via a compose profile, so it does NOT
start with `docker compose up -d`. This keeps the default deployment unchanged
and avoids surprising you with a new node on your tailnet.

It works exactly like `cloudflared`: the container dials **out** to Tailscale's
coordination server, so no inbound ports need to be open on the host. Traffic
arriving at the Tailscale node is forwarded to the host's SSH daemon via the
Docker bridge gateway (`host.docker.internal`).

### Why an OAuth client, not an auth key

Tailscale **auth keys expire after at most 90 days** and there is no way to
extend that limit — you'd have to regenerate the key and redeploy every 90
days, or the container would silently fail to rejoin the tailnet after a
restart. To avoid that, this service uses a Tailscale **OAuth client** instead.
OAuth client secrets **do not expire**, so the container runs unattended
indefinitely.

The trade-off: nodes registered via OAuth **must be tagged** (a Tailscale
requirement), so the compose file passes `--advertise-tags=tag:server` via
`TS_EXTRA_ARGS`.

### About `tagOwners` (you probably don't need to touch it)

Tailscale's rule for assigning tags: an OAuth client can assign a tag if the
requested tags **exactly match** the client's tags (no `tagOwners` consultation),
**or** each requested tag is owned by one of the client's tags in `tagOwners`.

Since the OAuth client has `tag:server` and the container advertises
`tag:server`, it's an exact match — **no `tagOwners` entry is needed**.

You only need to add `tag:server` to `tagOwners` in your tailnet policy file if:

- You want **regular (non-Admin) users** to be able to apply `tag:server` to
  devices they log into (Admins/Owners/Network admins can always apply any tag
  implicitly — they don't need to be tag owners).
- You want **another tag** to be able to grant `tag:server` (e.g. a
  `tag:deployment` OAuth client that provisions both `tag:server` and
  `tag:db` nodes).

For reference, a `tagOwners` entry looks like:

```json
{
  "tagOwners": {
    "tag:server": ["your-email@example.com"]
  }
}
```

You'll still need a **grant** (or legacy `acls` entry) to actually permit SSH
to `tag:server` — `tagOwners` only controls who can *assign* the tag, not what
tagged devices can *do*. See step 5 below.

> **Note: Tailscale SSH vs. host sshd.** This setup uses `TS_DEST_IP` to forward
> tailnet traffic to the **host's regular sshd** (port 22). It does **not** use
> Tailscale's built-in SSH server (we don't set `TS_ENABLE_SSH` or pass
> `--ssh`). As a result, the `ssh` section of your tailnet policy file does not
> govern access to this host — the `grants` (or `acls`) section does.

### One-time setup

1. Create an OAuth client at
   <https://login.tailscale.com/admin/settings/trust-credentials>
   → *Credentials* → *Generate credential* → *OAuth*:
   - Grant **BOTH** the **Devices - core** (`devices:core`) AND **Policy File**
     (`policy_file`) scopes. (The same client is reused by the GitOps ACL
     workflow in `.github/workflows/tailscale.yml` — no need for a second one.)
   - Assign the **`tag:server`** tag (the client will carry this tag; the
     container advertises the same tag, which is an exact match and so doesn't
     require a `tagOwners` entry — see "About `tagOwners`" above).
2. Copy the **client ID** (non-secret, starts with `k`) and **client secret**
   (secret, starts with `tskey-client-`).
3. Store them as GitHub **org** secrets/variables (org Settings → Secrets and
   variables → Actions), scoped to this repo only:
   - `TS_OAUTH_ID` — org **variable** (`vars.*`). Client ID. Non-secret, so a
     variable lets the build workflow read it via `${{ vars.TS_OAUTH_ID }}`.
   - `TS_OAUTH_SECRET` — org **secret** (`secrets.*`). Client secret. Read by
     both the GitOps ACL workflow and the image build workflow.
4. Make sure your tailnet policy file permits SSH to `tag:server` from your
   user(s). The default policy (with its wildcard
   `"src": ["*"], "dst": ["*"]` grant) already permits SSH, and this repo
   ships a ready-to-use policy file at
   [`tailscale/policy.hujson`](../tailscale/policy.hujson) that you can sync
   to Tailscale via GitHub — see
   [Managing the tailnet policy via GitHub](#managing-the-tailnet-policy-via-github)
   below. To restrict access to just your user and port 22, replace the
   wildcard grant in that file with:
   ```json
   {"src": ["your-email@example.com"], "dst": ["tag:server:22"], "ip": ["*"]}
   ```
   > If your tailnet still uses the legacy `acls` array instead of `grants`,
   > the equivalent rule is:
   > `{"action": "accept", "src": ["your-email@example.com"], "dst": ["tag:server:22"]}`
5. Ensure the host's SSH daemon is listening on `0.0.0.0:22` (default on most
   Linux distros; on Ubuntu verify with `sudo ss -tlnp | grep :22`).
6. On Linux hosts, ensure the `tun` kernel module is loaded:
   ```bash
   sudo modprobe tun
   ```
7. **One-time `docker login` on the host** — the custom tailscale image is
   **private** on GHCR (it has the OAuth client secret baked in, see
   [`docker/tailscale/Dockerfile`](tailscale/Dockerfile)). Create a classic PAT
   at <https://github.com/settings/tokens> with `read:packages` scope, then:
   ```bash
   echo "<PAT>" | docker login ghcr.io -u <github-username> --password-stdin
   ```
   This caches creds in `~/.docker/config.json` — do it once per host.
8. Start the sidecar:
   ```bash
   docker compose --profile tailscale up -d
   ```

### Locking down the wildcard grant (optional)

The default Tailscale policy file ships with a wildcard grant:

```json
{"src": ["*"], "dst": ["*"], "ip": ["*"]}
```

This lets **any** node on your tailnet reach **any** port on `tag:server`, not
just SSH. For a single-user tailnet that's usually fine. If you want to
restrict access to just your user and just port 22, replace the wildcard with:

```json
"grants": [
  {"src": ["your-email@example.com"], "dst": ["tag:server:22"], "ip": ["*"]}
]
```

Keep `"tagOwners": {"tag:server": []}` as-is — the empty owner list means only
Owners/Admins/Network admins (and our OAuth client via the exact-match rule)
can assign the tag, which is what we want.

### Managing the tailnet policy via GitHub

This repo ships a ready-to-use tailnet policy file at
[`tailscale/policy.hujson`](../tailscale/policy.hujson) and a GitHub Actions
workflow at [`.github/workflows/tailscale.yml`](../.github/workflows/tailscale.yml)
that syncs it to Tailscale automatically using the
[`tailscale/gitops-acl-action`](https://github.com/marketplace/actions/sync-tailscale-acls)
action. This gives you version history, PR review, and easy backup/restore for
the entire tailnet policy.

The workflow:

- On **pull request** targeting `main`: runs the action with `action: test`,
  which sends the policy file to Tailscale for validation (and runs any
  [`tests`](https://tailscale.com/docs/reference/syntax/policy-file#tests)
  defined in the file) **without applying it**. The PR check fails if the
  policy is invalid.
- On **push** (merge) to `main`: runs the action with `action: apply`, which
  validates and then **applies** the policy to your tailnet.

It only triggers on changes to `tailscale/policy.hujson` or the workflow file
itself (see `paths:` in the workflow), so unrelated pushes don't waste CI
minutes.

**One-time setup:**

1. Create a **separate** OAuth client for policy-file management at
   <https://login.tailscale.com/admin/settings/trust-credentials>
   → *Credentials* → *Generate credential* → *OAuth*:
   - Grant the **Policy File** (`policy_file`) scope — this is read+write, so
     the action can both test and apply.
   - This is a **different** OAuth client from the one used by the `tailscale`
     sidecar service (which only needs `devices:core`). Don't reuse it.
   - Copy the **client ID** (starts with `k`) and **client secret** (starts
     with `tskey-client-`).
2. Find your **tailnet ID** at
   <https://login.tailscale.com/admin/settings/general> (it looks like
   `example.com` or a hashed string — *not* your tailnet name).
3. Add the credentials to the `autoboat-vt` org as **org secrets** (org
   Settings → Secrets and variables → Actions → *New organization secret*),
   scoped to selected repositories (this repo only). This matches the
   existing `TUNNEL_TOKEN` pattern, so a future second boat project can
   reuse them without duplication:

   - `TS_TAILNET` — your tailnet ID (find it at
     <https://login.tailscale.com/admin/settings/general>)
   - `TS_OAUTH_ID` — the policy-file OAuth client ID
   - `TS_OAUTH_SECRET` — the policy-file OAuth client secret

   All three are stored as secrets (even the non-secret tailnet ID and
   client ID) for simplicity — one place to look, one permission model.
   The workflow references them as `${{ secrets.TS_TAILNET }}`,
   `${{ secrets.TS_OAUTH_ID }}`, and `${{ secrets.TS_OAUTH_SECRET }}`.
4. (Optional) Lock the policy file editor in the Tailscale admin console so
   other admins don't accidentally edit it directly: open
   <https://login.tailscale.com/admin/settings/policy-file-management>,
   enable *Prevent edits in the admin console*, and set *External reference*
   to this repo's URL.

**Editing the policy:**

```bash
$EDITOR tailscale/policy.hujson   # edit the file
git checkout -b tailscale/my-change
git add tailscale/policy.hujson
git commit -m "tailscale: <describe change>"
git push -u origin tailscale/my-change
# open a PR -> the Test ACL check runs -> merge -> the Deploy ACL step applies
```

If the policy file is invalid HuJSON or fails its `tests`, the PR check fails
and the merge is blocked. The last-known-good policy stays in effect on your
tailnet — a bad push can never break SSH access.

**Is it safe to commit?**

Yes — the policy file contains no secrets. It only has tag names, user emails
(only if you add `tagOwners` entries with specific users — the shipped file
uses an empty owner list, so no emails), and grant/SSH rules. Tailscale's docs
recommend a **private** repo since the policy file is considered PII; this
repo is already private.

**Why a separate OAuth client, not an API key?**

Tailscale API access tokens expire after at most 90 days (the same hard limit
as auth keys). OAuth client secrets do not expire, so the workflow runs
unattended indefinitely — same reasoning as the sidecar container's OAuth
client. If you'd rather use an API key, replace `TS_OAUTH_ID`/`TS_OAUTH_SECRET`
with `TS_API_KEY` in the workflow (see the comments in
`.github/workflows/tailscale.yml`).

**Trade-offs:**

| ✅ Pros | ⚠️ Cons |
|---|---|
| Versioned, reviewable, auditable policy changes | Requires a separate OAuth client (one-time setup) |
| PR check blocks invalid policies before they reach production | Adds one more GitHub Actions workflow to the repo |
| Easy backup/restore of the entire tailnet policy | Manual edits in the admin console will be overwritten on the next sync |
| OAuth client secret doesn't expire (unlike API keys) | |

### Connecting

Once the container reports `Logged in.` in its logs (`docker compose logs -f
tailscale`), the host is reachable from any device on your tailnet as
`telemetry-server` (the MagicDNS name):

```bash
ssh <your-host-username>@telemetry-server
```

> **Note on `host.docker.internal`:** the `extra_hosts` mapping
> (`host.docker.internal:host-gateway`) makes the Docker bridge gateway
> reachable by that name inside the container. `TS_DEST_IP` then tells
> Tailscale to forward traffic to that address, which is the host. This is
> what makes `ssh <user>@telemetry-server` land on the host's sshd rather
> than inside the container.

## Useful commands

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
