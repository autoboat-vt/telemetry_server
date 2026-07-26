---
description: "Use when editing tailscale/policy.hujson or anything related to Tailscale ACLs, the tailscale sidecar, OAuth clients, or tailnet access. Covers the GitOps sync workflow, the tagOwners exact-match rule, the ssh vs grants distinction, and the policy file format."
applyTo: "tailscale/**, docker/tailscale/**, .github/workflows/tailscale.yml"
---

# Tailscale — `tailscale/policy.hujson` and sidecar

**Read `/memories/repo/tailscale_oauth.md` for the full deep context.** This
file is a quick reference.

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
the wildcard with a tag-scoped grant (see `docker/README.md` → "Locking down
the wildcard grant").

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

## Connecting

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
