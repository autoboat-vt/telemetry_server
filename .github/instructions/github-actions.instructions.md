---
description: "Use when editing GitHub Actions workflows under .github/workflows/, the release tag script, or dependabot config. Covers the two-stage build-and-publish pattern, multi-arch manifest assembly, GHCR cleanup, tag computation, and the tailscale GitOps ACL workflow."
applyTo: ".github/workflows/**, .github/scripts/**, .github/dependabot.yml"
---

# GitHub Actions — `.github/workflows/`

## Two-stage build-and-publish

Mirrors the pattern from `autoboat-vt/autoboat_vt`'s `build-and-release.yml`.

### `.github/workflows/build.yml` — per-arch build

Triggers: push to `main`/`testing`, tags `v*`, PRs to `main`/`testing`,
`workflow_dispatch`.

Matrix: `amd64` on `ubuntu-22.04`, `arm64` on `ubuntu-22.04-arm` (native ARM
runner — faster than QEMU. If unavailable, swap arm64 to `ubuntu-22.04` and
add a `setup-qemu` step).

Steps:
1. Checkout.
2. `docker/setup-buildx-action@v4`.
3. Log in to GHCR **only on push** (PR runs from forks can't access secrets).
4. Compute per-arch tags via `.github/scripts/compute-release-tags.sh`:
   - Calls `compute-release-tags.sh base` to get the list of base tags.
   - Appends `-amd64` / `-arm64` suffix to each.
   - Emits `ghcr.io/${OWNER_LC}/telemetry_server:${tag}-${arch}` per line.
5. `docker/build-push-action@v7`:
   - `push: ${{ github.event_name == 'push' }}` — PR builds are cache-only.
   - `cache-from: type=gha,scope=${{ matrix.architecture }}` and
     `cache-to: type=gha,mode=max,scope=${{ matrix.architecture }}` — per-arch
     GHA cache scopes (don't mix amd64 and arm64 cache layers).
6. Then computes tailscale image tags (same script, different GHCR repo:
   `telemetry_server-tailscale`) and builds the tailscale image **on push
   only** with build-args `TS_CLIENT_ID=${{ vars.TS_OAUTH_ID }}` and
   `TS_CLIENT_SECRET=${{ secrets.TS_OAUTH_SECRET }}`.

### `.github/workflows/push.yml` — multi-arch manifest publish

Triggered by `workflow_run` on `build.yml` completion. Guards:
`if: github.event.workflow_run.conclusion == 'success' && (event == 'push' || event == 'workflow_dispatch')`.

Steps:
1. Checkout, lowercase the owner name (`GITHUB_REPOSITORY_OWNER,,` — bash 4+
   case modification; works on `ubuntu-latest`).
2. Log in to Docker Hub (`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` repo
   secrets) and GHCR (`GITHUB_TOKEN`).
3. For each base tag from `compute-release-tags.sh base`:
   - `docker buildx imagetools create -t ghcr.io/.../telemetry_server:${tag}
     ghcr.io/.../telemetry_server:${tag}-amd64
     ghcr.io/.../telemetry_server:${tag}-arm64` — assembles the multi-arch
     manifest on GHCR.
   - `docker buildx imagetools create -t vtautoboat/telemetry_server:${tag}
     ghcr.io/.../telemetry_server:${tag}` — mirrors the finished manifest to
     Docker Hub. This copies the manifest AND all arch blobs in one step, so
     Docker Hub never holds intermediate `-arch` tags.
4. Same for the tailscale image, GHCR only (NOT mirrored — image is private).

### `.github/workflows/tailscale.yml` — GitOps ACL sync

Triggers on changes to `tailscale/policy.hujson` or the workflow file itself
(`paths:` filter — unrelated pushes don't waste CI minutes).

- On PR to main: `tailscale/gitops-acl-action@v1` with `action: test`
  (validate only — never applies).
- On push to main: same action with `action: apply` (validate + push to
  tailnet).

Inputs: `oauth-client-id: ${{ secrets.TS_OAUTH_ID }}`,
`oauth-secret: ${{ secrets.TS_OAUTH_SECRET }}`,
`tailnet: ${{ vars.TS_TAILNET }}`,
`policy-file: tailscale/policy.hujson`.

**Namespace gotcha:** `TS_OAUTH_ID` and `TS_OAUTH_SECRET` are org SECRETS
(`secrets.*`), but `TS_TAILNET` is an org VARIABLE (`vars.*`). Reading a var
via `secrets.*` resolves to empty string with no error — this once caused a
404 "tailnet 'acl' not found" because the empty tailnet collapsed the API URL
path. Always use the right namespace.

## Tag computation (`.github/scripts/compute-release-tags.sh`)

Usage:
- `compute-release-tags.sh base` — emit base tags, one per line.
- `compute-release-tags.sh suffix amd64` — emit `${tag}-amd64` per line.

Logic (uses `SOURCE_REF_NAME` / `GITHUB_REF_NAME`):
- Branch push: emit the branch name. If branch is `main`, also emit `latest`.
- Tag push (`v1.2.3`): emit `1.2.3`, `1.2`, `1`, `latest`.
- Otherwise: emit nothing.

The `SOURCE_REF_NAME` env var is set explicitly in `push.yml`'s `env:` block
to `${{ github.event.workflow_run.head_branch }}` because `workflow_run`
events don't populate `GITHUB_REF_NAME` with the source branch the way push
events do.

## GHCR cleanup

GHCR has **no built-in retention policy**. Orphaned versions accumulate
forever unless deleted via API. The publish job deletes any GHCR package
version where:
1. It's untagged (orphans from tag-name rewrites), OR
2. ALL its tags end in `-amd64` or `-arm64` (intermediate per-arch images).

Uses `continue-on-error: true` so transient API failures don't break the
publish job.

**Role requirement:** the `GITHUB_TOKEN` in Actions has `packages: write`
scope (can push) but CANNOT delete package versions unless the source repo
has the **Admin** role (not Write) on the package. Set this in the package
settings UI under "Manage Actions access" — there is NO REST API to set it.
If `GITHUB_TOKEN` still 403s with Admin role, fallback is a PAT with
`delete:packages` scope stored as a repo secret.

API endpoints (org-scoped):
- List versions: `GET /orgs/{org}/packages/container/{name}/versions?per_page=100&page={n}`
- Delete version: `DELETE /orgs/{org}/packages/container/{name}/versions/{id}`
- Response shape: `[{id, metadata: {container: {tags: [...]}}}]`
- `/orgs/{org}/packages/container/{name}/repositories` does NOT exist (404) —
  repo access is web-UI-only.

Docker Hub has no public API for deleting tags on public repos, so DH
intermediate tags would accumulate — except we never push per-arch tags to
DH in the first place (only finished manifests). DH stays clean automatically.

## dependabot.yml

Weekly updates for `pip` (root `pyproject.toml`) and `github-actions`. Keep
the schedule weekly — daily updates are noisy for a small project.

## Common workflow pitfalls

- **`docker/build-push-action` `tags:` input expects `repo:tag`, not bare tag
  names.** If you compute tags in bash (without `docker/metadata-action`),
  emit `ghcr.io/owner/repo:tag` per line — NOT just `tag`. Bare names get
  interpreted as `docker.io/library/<name>` → push fails with
  `insufficient_scope: authorization failed`.
- **`GITHUB_REPOSITORY_OWNER` is mixed-case; GHCR requires lowercase.** Use
  `OWNER_LC=${GITHUB_REPOSITORY_OWNER,,}` (bash 4+ lowercase) in every step
  that constructs an image reference.
- **Per-arch GHA cache scopes.** Use `scope=amd64` / `scope=arm64` so amd64
  and arm64 cache layers don't mix (mixing causes weird "layer not found"
  errors on different arches).
- **`push: ${{ github.event_name != 'pull_request' }}`** so PR builds are
  cache-only — fork PRs can't push to GHCR anyway (no secret access).
- **PyYAML gotcha (for local validation only):** `on:` parses as boolean
  `True` in YAML 1.1. GitHub Actions handles it correctly, but
  `yaml.safe_load` locally needs `wf[True]` to access the triggers.
