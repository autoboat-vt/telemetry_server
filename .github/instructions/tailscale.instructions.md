---
description: "Use when editing tailscale/policy.hujson or anything related to Tailscale ACLs, the tailscale sidecar, OAuth clients, or tailnet access. Covers the GitOps sync workflow, the tagOwners exact-match rule, the ssh vs grants distinction, and the policy file format."
applyTo: "tailscale/**, docker/tailscale/**, .github/workflows/tailscale.yml"
---

# Tailscale — `tailscale/policy.hujson` and sidecar

This file is the deep-dive reference for the tailscale sidecar, the OAuth
client, the GitOps ACL workflow, and the tailnet policy file. The
companion Docker-side notes (compose service config, the custom image
build, the `.dockerignore` exceptions) live in
`.github/instructions/docker.instructions.md` under "tailscale (opt-in
profile)" and "The custom tailscale image".

## Policy file source of truth

Lives in this repo at `tailscale/policy.hujson` (HuJSON format = JSON +
comments + trailing commas). Synced to Tailscale by the
`tailscale/gitops-acl-action@v1` GitHub Action in
`.github/workflows/tailscale.yml`. NOT an admin-console "Manage via GitHub"
UI thing.

Workflow:
- PR targeting main → action runs `test` (validate only, never applies).
- Push to main → action runs `apply` (validate + push to tailnet).
- Triggers only on changes to `tailscale/policy.hujson` or the workflow file
  itself (paths filter).
- Invalid HuJSON or failing `tests` block the merge, so a bad push can never
  break SSH access — the last-known-good policy stays in effect.

Required GitHub configuration (org-level, scoped to selected repos, matches
the `TUNNEL_TOKEN` pattern):
- `TS_TAILNET` → `vars.TS_TAILNET` (ORG VARIABLE, not secret). Tailnet name
  e.g. `beetal-spica.ts.net` from admin/settings/general. Non-sensitive.
- `TS_OAUTH_ID` → `secrets.TS_OAUTH_ID` (ORG SECRET). Client ID, starts with
  `k`.
- `TS_OAUTH_SECRET` → `secrets.TS_OAUTH_SECRET` (ORG SECRET). Client secret,
  starts with `tskey-client-`.

**CRITICAL:** GitHub `secrets.*` and `vars.*` are SEPARATE namespaces.
Reading a var via `secrets.*` resolves to empty string (no error). This
caused a real 404 "tailnet 'acl' not found" because the empty tailnet
collapsed the API URL path. Always use the right namespace.

Org-level (not repo-level) so a future second boat project can reuse the
creds without duplication. The file contains NO secrets (tags, user emails
if added to tagOwners/grants, rules) — Tailscale docs recommend private repo
(policy file = PII). This repo is private.

Validate locally:
```bash
# Strip // comments and trailing commas, then parse as JSON.
python -c "import json; print(json.loads(__import__('re').sub(r',\s*([}\]])', r'\1', __import__('re').sub(r'//.*', '', open('tailscale/policy.hujson').read()))))"
```

## OAuth client, not auth key

Tailscale **auth keys expire after at most 90 days** — hard limit, no setting
to extend. A container using `TS_AUTHKEY` with an auth key would silently
fail to rejoin the tailnet after expiry on the next restart. Forces a
regenerate + redeploy every 90 days. Avoid for unattended servers.

**OAuth client** (`TS_CLIENT_ID` + `TS_CLIENT_SECRET`): client secret does
NOT expire. Runs unattended forever. This is what we use.

Trade-off: OAuth-registered nodes MUST be tagged (Tailscale requirement).
`docker-compose.yml` passes `--advertise-tags=tag:server` via `TS_EXTRA_ARGS`.

Create the OAuth client at
https://login.tailscale.com/admin/settings/trust-credentials → Credentials →
Generate → OAuth. Grant BOTH "Devices - core" (`devices:core`) AND "Policy
File" (`policy_file`) scopes — ONE client reused for both the sidecar and the
GitOps ACL workflow. Assign `tag:server`.

- Client ID is non-secret (starts with `k`).
- Client secret is secret (starts with `tskey-client-`).

GitHub org-level (scoped to this repo only):
- `TS_OAUTH_ID` → ORG VARIABLE (`vars.*`). Must be a VARIABLE, not secret —
  secrets are write-only and can't be read back by `vars.*` or
  `gh variable get`.
- `TS_OAUTH_SECRET` → ORG SECRET (`secrets.*`). Read by both the GitOps ACL
  workflow and the build workflow.
- `TS_TAILNET` → ORG VARIABLE (`vars.*`).

## tagOwners — usually NOT needed

Tailscale rule: an OAuth client can assign a tag if the requested tags
EXACTLY MATCH the client's tags (no tagOwners consultation), OR each
requested tag is owned by one of the client's tags in tagOwners.

Our setup: client has `tag:server`, container advertises `tag:server` →
exact match. **No tagOwners entry needed.**

`tagOwners` only needed if:
- You want regular (non-Admin) users to be able to apply `tag:server`
  (Admins/Owners/Network admins can always apply any tag implicitly).
- You want another tag to grant `tag:server` (e.g. `tag:deployment`
  provisions both `tag:server` and `tag:db`).

`tagOwners` controls who can ASSIGN a tag, NOT what tagged devices can DO.
ACLs/grants control access (SSH etc.).

`"tagOwners": {"tag:server": []}` is fine: empty owner list = only
Admins/Owners/Network admins can assign `tag:server` to devices. Doesn't
affect the OAuth client (uses exact-match rule, not tagOwners).

## grants vs ssh

This setup uses Tailscale's built-in SSH server (`--ssh` in `TS_EXTRA_ARGS`).
So the policy file's `ssh` section DOES govern access to the
`telemetry-tailscale` container.

- New `grants`: `{"src":["..."],"dst":["tag:server:22"],"ip":["*"]}`
- Legacy `acls`: `{"action":"accept","src":["..."],"dst":["tag:server:22"]}`

The default tailnet policy has a wildcard grant
`{"src":["*"],"dst":["*"],"ip":["*"]}` which already permits SSH to
`tag:server` — no extra rule needed if you keep it. To lock down, replace
the wildcard with a tag-scoped grant (see "Locking down the wildcard grant
(optional)" below).

The `ssh` section uses `check` mode (records who logged in via the tailnet's
audit log and re-validates the client's Tailscale identity on each
connection). We allow `autogroup:member` → `tag:server` with
`users: ["autogroup:nonroot", "root"]` because the container runs as root
(`user: "0:0"`) and the upstream image only has `tailscale` and `root`
users — there's no per-user account matching your Tailscale username.

**To SSH into the HOST** (not the container): use regular
`ssh <host-user>@telemetry-server`. Host networking puts the tailnet IP on
the host's sshd. That path requires an SSH key in the host's
`~/.ssh/authorized_keys` and is independent of the `ssh` section in the
policy file.

## CONTAINERBOOT v1.98 BUG — use TS_AUTHKEY, not TS_CLIENT_SECRET

Symptom: with `TS_CLIENT_ID` + `TS_CLIENT_SECRET` baked in, containerboot
calls `tailscale up` which internally invokes `check-prefs` BEFORE the OAuth
client auth completes. tailscaled sees an unauthenticated actor and rejects
with HTTP 403: "calling actor does not have enough permissions to perform
this function".

Fix: bake the OAuth secret into `TS_AUTHKEY` instead of `TS_CLIENT_SECRET`.
Per Tailscale docs (https://tailscale.com/docs/features/containers/docker/docker-params):
> "TS_AUTHKEY: You can also use an OAuth client secret here, but you must
> provide the associated tag using TS_EXTRA_ARGS=--advertise-tags=tag:ci."

With `TS_AUTHKEY`, auth + pref validation happen together in a single
`tailscale up --auth-key=<secret>` call, avoiding the pre-auth check-prefs
rejection.

**CRITICAL:** do NOT also set `TS_CLIENT_ID`. containerboot explicitly
rejects: "TS_AUTHKEY cannot be used with TS_CLIENT_ID, TS_CLIENT_SECRET,
TS_ID_TOKEN, or TS_AUDIENCE". So the Dockerfile sets ONLY `TS_AUTHKEY`, not
`TS_CLIENT_ID`.

`TS_EXTRA_ARGS=--advertise-tags=tag:server` is still required (in
`docker-compose.yml`) because OAuth-registered nodes must be tagged.

## SSH access via the sidecar

The `tailscale` service is **opt-in** via a compose profile, so it does NOT
start with `docker compose up -d`. This keeps the default deployment
unchanged and avoids surprising you with a new node on your tailnet.

It works exactly like `cloudflared`: the container dials **out** to
Tailscale's coordination server, so no inbound ports need to be open on the
host. The container runs Tailscale's built-in SSH server (`--ssh` in
`TS_EXTRA_ARGS`), so `tailscale ssh root@telemetry-server` from anywhere on
your tailnet drops you into a shell **in the container** (not on the host).
Auth is identity-based (Tailscale account, SSO-backed) — no SSH keys to
manage.

**Why `root@`?** Tailscale SSH defaults to your Tailscale account username,
but the upstream `tailscale/tailscale` Alpine image only has `root` and
`tailscale` (nologin) in `/etc/passwd`. Specifying `root@` works for any
tailnet member regardless of their username. The ACL in
`tailscale/policy.hujson` gates access — only authorized tailnet members can
log in.

**Why an OAuth client, not an auth key?** Tailscale **auth keys expire
after at most 90 days** and there is no way to extend that limit — you'd
have to regenerate the key and redeploy every 90 days, or the container
would silently fail to rejoin the tailnet after a restart. To avoid that,
this service uses a Tailscale **OAuth client** instead. OAuth client secrets
**do not expire**, so the container runs unattended indefinitely.

The trade-off: nodes registered via OAuth **must be tagged** (a Tailscale
requirement), so the compose file passes `--advertise-tags=tag:server` via
`TS_EXTRA_ARGS`.

## One-time setup (tailscale sidecar)

1. Create an OAuth client at
   <https://login.tailscale.com/admin/settings/trust-credentials>
   → *Credentials* → *Generate credential* → *OAuth*:
   - Grant **BOTH** the **Devices - core** (`devices:core`) AND **Policy File**
     (`policy_file`) scopes. (The same client is reused by the GitOps ACL
     workflow in `.github/workflows/tailscale.yml` — no need for a second one.)
   - Assign the **`tag:server`** tag (the client will carry this tag; the
     container advertises the same tag, which is an exact match and so
     doesn't require a `tagOwners` entry — see "tagOwners — usually NOT
     needed" above).
2. Copy the **client ID** (non-secret, starts with `k`) and **client secret**
   (secret, starts with `tskey-client-`).
3. Store them as GitHub **org** secrets/variables (org Settings → Secrets and
   variables → Actions), scoped to this repo only:
   - `TS_OAUTH_ID` — org **variable** (`vars.*`). Client ID. Non-secret, so a
     variable lets the build workflow read it via `${{ vars.TS_OAUTH_ID }}`.
   - `TS_OAUTH_SECRET` — org **secret** (`secrets.*`). Client secret. Read by
     both the GitOps ACL workflow and the image build workflow.
4. Make sure your tailnet policy file permits SSH to `tag:server` from your
   user(s). The default policy (with its wildcard grant) already permits SSH,
   and this repo ships a ready-to-use policy file at
   `tailscale/policy.hujson` that you can sync to Tailscale via GitHub — see
   "Managing the tailnet policy via GitHub" below. To restrict access to just
   your user and port 22, replace the wildcard grant with:
   ```json
   {"src": ["your-email@example.com"], "dst": ["tag:server:22"], "ip": ["*"]}
   ```
   > If your tailnet still uses the legacy `acls` array instead of `grants`,
   > the equivalent rule is:
   > `{"action": "accept", "src": ["your-email@example.com"], "dst": ["tag:server:22"]}`
5. On Linux hosts, ensure the `tun` kernel module is loaded:
   ```bash
   sudo modprobe tun
   ```
6. **One-time `docker login` on the host** — the custom tailscale image is
   **private** on GHCR (it has the OAuth client secret baked in, see
   `docker/tailscale/Dockerfile`). Create a classic PAT at
   <https://github.com/settings/tokens> with `read:packages` scope, then:
   ```bash
   echo "<PAT>" | docker login ghcr.io -u <github-username> --password-stdin
   ```
   This caches creds in `~/.docker/config.json` — do it once per host.
7. Start the sidecar:
   ```bash
   docker compose --profile tailscale up -d
   ```
8. SSH in from anywhere on your tailnet (see "Connecting" below).

## Locking down the wildcard grant (optional)

The default Tailscale policy file ships with a wildcard grant:

```json
{"src": ["*"], "dst": ["*"], "ip": ["*"]}
```

This lets **any** node on your tailnet reach **any** port on `tag:server`,
not just SSH. For a single-user tailnet that's usually fine. If you want to
restrict access to just your user and just port 22, replace the wildcard
with:

```json
"grants": [
  {"src": ["your-email@example.com"], "dst": ["tag:server:22"], "ip": ["*"]}
]
```

Keep `"tagOwners": {"tag:server": []}` as-is — the empty owner list means
only Owners/Admins/Network admins (and our OAuth client via the exact-match
rule) can assign the tag, which is what we want.

## Managing the tailnet policy via GitHub

This repo ships a ready-to-use tailnet policy file at
`tailscale/policy.hujson` and a GitHub Actions workflow at
`.github/workflows/tailscale.yml` that syncs it to Tailscale automatically
using the
[`tailscale/gitops-acl-action`](https://github.com/marketplace/actions/sync-tailscale-acls)
action. This gives you version history, PR review, and easy backup/restore
for the entire tailnet policy.

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

1. Create an OAuth client for policy-file management at
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

If the policy file is invalid HuJSON or fails its `tests`, the PR check
fails and the merge is blocked. The last-known-good policy stays in effect
on your tailnet — a bad push can never break SSH access.

**Is it safe to commit?**

Yes — the policy file contains no secrets. It only has tag names, user
emails (only if you add `tagOwners` entries with specific users — the
shipped file uses an empty owner list, so no emails), and grant/SSH rules.
Tailscale's docs recommend a **private** repo since the policy file is
considered PII; this repo is already private.

**Why a separate OAuth client, not an API key?**

Tailscale API access tokens expire after at most 90 days (the same hard
limit as auth keys). OAuth client secrets do not expire, so the workflow
runs unattended indefinitely — same reasoning as the sidecar container's
OAuth client. If you'd rather use an API key, replace
`TS_OAUTH_ID`/`TS_OAUTH_SECRET` with `TS_API_KEY` in the workflow (see the
comments in `.github/workflows/tailscale.yml`).

**Trade-offs:**

| Pros | Cons |
|---|---|
| Versioned, reviewable, auditable policy changes | Requires a separate OAuth client (one-time setup) |
| PR check blocks invalid policies before they reach production | Adds one more GitHub Actions workflow to the repo |
| Easy backup/restore of the entire tailnet policy | Manual edits in the admin console will be overwritten on the next sync |
| OAuth client secret doesn't expire (unlike API keys) | |

## Connecting

Once the container reports `Logged in.` in its logs
(`docker compose logs -f tailscale`), the host is reachable from any device
on your tailnet as `telemetry-server` (the MagicDNS name):

- `tailscale ssh root@telemetry-server` (or `tailscale@telemetry-server`) —
  shell **in the container**. The default (your Tailscale account username)
  won't exist in the container's `/etc/passwd` and will fail with "failed to
  look up local user".
- `ssh <host-user>@telemetry-server` — shell **on the host** (regular SSH,
  requires authorized_keys entry).
- Verify the container is up: `docker compose logs tailscale` — look for
  "Logged in.".

## FAILED APPROACHES (don't retry)

- `TS_DEST_IP` with bridge networking: containerboot parses `TS_DEST_IP` as a
  literal IP, does NOT resolve DNS. `host.docker.internal` is a hostname,
  fails with `ParseAddr("host.docker.internal"): unexpected character`.
- `TS_DEST_IP` with entrypoint to resolve hostname: still hits "IP forwarding
  must be enabled" + eventually the 403 containerboot bug.
- `sysctls: net.ipv4.ip_forward=1` with `network_mode: host`: rejected by
  Docker ("sysctl not allowed in host network namespace"). Host already has
  ip_forward enabled.
- `TS_CLIENT_ID` + `TS_CLIENT_SECRET`: containerboot v1.98 403 bug (see
  above).
- `TS_AUTHKEY` + `TS_CLIENT_ID`: containerboot rejects the combination
  explicitly.
