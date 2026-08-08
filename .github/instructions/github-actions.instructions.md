---
description: "Use when editing GitHub Actions workflows under .github/workflows/, the release tag script, or dependabot config. Covers the two-stage build-and-publish pattern, multi-arch manifest assembly, GHCR cleanup, tag computation, and the tailscale GitOps ACL workflow."
applyTo: ".github/workflows/**, .github/scripts/**, .github/dependabot.yml"
---

# GitHub Actions — `.github/workflows/`

## Two-stage build-and-publish

Mirrors the pattern from `autoboat-vt/autoboat_vt`'s `build-and-release.yml`.

### `.github/workflows/build.yml` — test + per-arch build

Triggers: push to `main`/`testing`, tags `v*`, PRs to `main`/`testing`,
`workflow_dispatch`.

Two jobs: `test` (non-matrixed) then `build` (matrixed, `needs: test`).

#### `test` job — lint + pytest gate

Runs on `ubuntu-latest` on every trigger (including PRs). Gates the `build`
job via `needs: test` so a failing test fails fast before Docker build
minutes are spent.

Steps:
1. Checkout.
2. `actions/setup-python@v5` with `python-version: "3.12"`, `cache: pip`,
   `cache-dependency-path: pyproject.toml`.
3. `pip install -e ".[dev]"` — installs the package (editable) plus the
   `dev` extras from `pyproject.toml` (`ruff`, `pytest`, `build`,
   `pyproject_hooks`).
4. `ruff check .` — lint.
5. `ruff format --check .` — format check (non-mutating).
6. `pytest` — runs the suite in `tests/` (configured via
   `pyproject.toml`'s `[tool.pytest.ini_options]`: `testpaths = ["tests"]`,
   `pythonpath = ["src"]`).

**Do not remove the `needs: test` from the `build` job.** The whole point is
to gate image builds on test success. If you need to force a build past a
failing test in an emergency, use `workflow_dispatch` on the `build` job
directly instead of editing out the gate.

**First bug it caught (2026-07-26):**
`tests/test_init.py::TestInstanceDirDiscovery::test_home_dir_is_fake_home`
originally hardcoded `assert HOME_DIR.name == "autoboat"` (the dev's local
repo parent dir). On CI the repo is checked out at
`/home/runner/work/telemetry_server/telemetry_server`, so `HOME_DIR.name`
was `"telemetry_server"` and the test failed. Fix: import `FAKE_HOME` from
`tests/conftest.py` and assert `HOME_DIR == FAKE_HOME` (the conftest sets
`FAKE_HOME = REPO_ROOT.parent` and patches `/home` to return it, so the
invariant holds on every machine). Lesson: tests that depend on the repo's
parent dir name are non-portable. Assert the invariant the conftest
establishes (`HOME_DIR == FAKE_HOME`), not a hardcoded local path
component.

#### `build` job — per-arch Docker image

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

**Commits that established this:** `bd2e3ec` (testing) / `227ea08` (main)
re-added the cleanup step after the repo role was elevated to Admin;
`9eaa723` (testing) had removed it earlier when it was 403'ing with the
Write role. A local one-off cleanup helper (`/tmp/ghcr_cleanup.sh`, using
the `gh` CLI with a `delete:packages`-scoped PAT) can be recreated if a
manual sweep is ever needed outside CI.

### `.github/workflows/citation.yml` — CITATION.cff date-released sync

Triggers: push to `main` + `workflow_dispatch`. Permissions: `contents: write`
(bot needs to push a commit). Job guard: `if: github.actor != 'github-actions[bot]'`
so the bot's own commit doesn't retrigger the workflow (infinite loop).

Steps:
1. `actions/checkout@v4` with `token: ${{ secrets.GITHUB_TOKEN }}` (the default
   `GITHUB_TOKEN` works; no PAT needed for pushes to the same repo).
2. `sed -i -E "s|^date-released: \".*\"$|date-released: \"${TODAY}\"|" CITATION.cff`
   rewrites the `date-released:` line to today's UTC date. The regex requires
   the line to already exist (it doesn't insert one). If `CITATION.cff` is
   missing the `date-released:` field, this step is a silent no-op.
3. `git diff --quiet CITATION.cff` short-circuits if nothing changed.
4. Commits as `github-actions[bot]` (`41898282+github-actions[bot]@users.noreply.github.com`)
   with message `chore: bump CITATION.cff date-released to today`.

Gotchas:
- The `if: github.actor != 'github-actions[bot]'` guard works because the bot's
  push triggers a new workflow run where `github.actor` is `github-actions[bot]`,
  which the guard skips. Verified pattern.
- Every merge to `main` produces a follow-up bot commit bumping `date-released`.
  This is intentional (keeps the citation date current) but it does add noise
  to the commit history. If you only want bumps on actual releases, change the
  trigger from `push: branches: [main]` to `push: tags: ["v*"]`.
- Don't manually edit `date-released` — the next push to `main` will overwrite
  it. Treat it as a derived field.
- If you change the `date-released:` line format in `CITATION.cff`, update the
  `sed` regex here to match (it matches `^date-released: ".*"$`).

## dependabot.yml

Weekly updates for `pip` (root `pyproject.toml`) and `github-actions`. Keep
the schedule weekly — daily updates are noisy for a small project.

## Common workflow pitfalls

- **`docker/build-push-action` `tags:` input expects `repo:tag`, not bare tag
  names.** If you compute tags in bash (without `docker/metadata-action`),
  emit `ghcr.io/owner/repo:tag` per line — NOT just `tag`. Bare names get
  interpreted as `docker.io/library/<name>` -> push fails with
  `insufficient_scope: authorization failed`.
- **`GITHUB_REPOSITORY_OWNER` is mixed-case; GHCR requires lowercase.** Use
  `OWNER_LC=${GITHUB_REPOSITORY_OWNER,,}` (bash 4+ lowercase) in every step
  that constructs an image reference.
- **Per-arch GHA cache scopes.** Use `scope=amd64` / `scope=arm64` so amd64
  and arm64 cache layers don't mix (mixing causes weird "layer not found"
  errors on different arches).
- **`push: ${{ github.event_name != 'pull_request' }}`** so PR builds are
  cache-only — fork PRs can't push to GHCR anyway (no secret access).
- **`test` job's `cache: pip` needs a lockfile or `pyproject.toml` hash.**
  `actions/setup-python@v5`'s pip cache keys on `cache-dependency-path`
  (set to `pyproject.toml`). If you rename `pyproject.toml` or move deps
  into a separate requirements file, update `cache-dependency-path` or the
  cache will never invalidate and stale installs will mask dependency
  changes.
- **PyYAML gotcha (for local validation only):** `on:` parses as boolean
  `True` in YAML 1.1. GitHub Actions handles it correctly, but
  `yaml.safe_load` locally needs `wf[True]` to access the triggers.
