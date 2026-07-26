# AGENTS.md — Autoboat Telemetry Server

> Always-on guidance for any AI coding agent (Copilot, Claude Code, Codex, etc.)
> working in this repository. Read this before touching code or infra.

This is the **telemetry server** for the Virginia Tech Autoboat project
(`autoboat-vt/telemetry_server`). It is a small Flask app that collects,
stores, and serves telemetry data (boat status, autopilot parameters, waypoints)
from autonomous boats, and is consumed by the Autoboat website
(`https://autoboat.aoe.vt.edu`) and by the boats' telemetry nodes.

---

## 0. Maintaining This File

**This file is the living source of truth for project knowledge.** Update it
frequently and proactively - every time you learn something new, change a
convention, fix a gotcha, bump a version, add a route, or discover a footgun.
A stale `AGENTS.md` is worse than none because it actively misleads the next
agent.

When you CHANGE something (refactor, rename, remove a file, alter a config,
fix a bug that was documented as a workaround), **update the corresponding
entry in the same PR** - don't let the docs drift from the code. Things worth
recording:

- **Conventions & patterns** - route URL conventions, lock decorator usage,
  response type patterns, the route error-code ladder (§3.12).
- **Gotchas** - non-obvious behavior, footguns, environment quirks, the
  `json.loads(request.json)` double-JSON encoding, the ctypes alignment
  branching, the `TS_AUTHKEY` vs `TS_CLIENT_SECRET` workaround.
- **Architecture decisions** - the runtime instance-dir discovery, the
  reader-writer lock asymmetry, SQLite + single worker, the outbound-only
  tunnel model.
- **Build/deploy/CI details** - commands, env vars, secret locations (§10),
  GHCR visibility rules, tag computation.
- **Verified facts** - dependency versions, route tables, secret scopes
  (verify against the actual codebase before recording, don't trust stale
  docs).

When adding to this file:

1. **Find the right section.** Use the existing numbered structure. Add a
   subsection under the most relevant top-level section rather than appending
   to the end.
2. **Be concise.** Bullet points and short prose, not essays. Link to
   files/symbols with backticks.
3. **Don't duplicate.** Search the file first - if it's already covered,
   edit/update rather than adding a parallel entry.
4. **Keep it accurate and in sync.** If you correct a stale claim, update it
   in place. Verify paths/class names against current source via `read_file`
   before editing the doc. When you change code or config that this file
   describes, update the relevant entry in the same PR.
5. **Don't move or rewrite unrelated sections** unless asked - make targeted
   additions/edits.

For deep context on past decisions (docker migration, tailscale OAuth, tunnel
token, GHCR cleanup), see `/memories/repo/*.md` - those were paid for in
debugging hours; don't pay again.

## Writing Style

Write in plain ASCII. Do not use emojis, decorative unicode, or characters/tics
that only an LLM would produce (e.g. `✨`, `🚀`, `👉`, em dashes `—` where a
hyphen suffices, curly quotes `“”` instead of straight `"`, heavy use of
`**bold**` for emphasis). Code, comments, commit messages, PR descriptions,
and documentation should read like they were written by a human teammate, not
an AI.

## Cross-repo contracts

This server is one side of three cross-repo contracts. Wire-format changes
require coordinated updates to all sides.

- **Browser consumer (`autoboat-vt/website`)**: `src/lib/telemetry.ts` is a
  REST client for this API. Route URL changes, response shape changes, or
  status-code changes must be reflected there. The website's
  `telemetry.instructions.md` documents the wire format (BoatStatus /
  Sailboat / Motorboat payloads, GPS sentinel, `BoatWithPosition` type) from
  the client side.
- **Boat telemetry node (`autoboat-vt/autoboat_vt`)**: publishes boat status,
  autopilot parameters, and waypoints to this server. Two invariants the node
  must preserve:
  - JSON bodies are sent as **JSON-encoded strings** (double-encoded). The
    server's `json.loads(request.json)` decode (§5) depends on this. See the
    `autoboat_vt` AGENTS.md "Cross-repo contracts" section.
  - `boat_status` fast-update binary payloads (`/boat_status/set_fast/<id>`,
    §3.4) are positional and MUST match the instance's `boat_status_mapping`
    field order exactly. Field-order changes on the firmware side silently
    decode to garbage here.
- **Enum sync**: `DiagnosticMessageIntensity` (1=INFO, 2=WARNING, 3=ERROR) is
  defined here in `src/autoboat_telemetry_server/types.py` and consumed by both
  the website and the ground station. If the int mapping changes, both
  consumers must be updated.

---

## 1. Project at a glance

| Property | Value |
| --- | --- |
| Language | Python 3.12 (`python:3.12-slim` base image; local pyenv alias `telemetry` in `.python-version`) |
| Framework | Flask 3.x, served by Gunicorn (1 worker, bind `0.0.0.0:8000` prod / `:6001` test) |
| ORM | Flask-SQLAlchemy 3.x on SQLite (two DBs: `instances.db`, `hashes.db`) |
| Concurrency | In-process fair reader-writer lock (`src/autoboat_telemetry_server/lock_manager.py`) wrapping all route handlers |
| Lint/format | Ruff (`ruff.toml`, `select = ["ALL"]` with a long ignore list; numpy-style docstrings; line length 130) |
| Build backend | setuptools (PEP 621 metadata in `pyproject.toml`) |
| Containerization | Docker + Docker Compose (4 services + 1 optional profile) |
| Public ingress | Cloudflare Tunnel (`cloudflared`) — outbound only, edge terminates TLS |
| Optional SSH | Tailscale sidecar (`--profile tailscale`, host networking, OAuth client auth) |
| CI | GitHub Actions: `build.yml` (test job gates per-arch Docker build; no push on PR), `push.yml` (multi-arch manifest publish to GHCR + Docker Hub), `tailscale.yml` (GitOps ACL sync) |
| Registries | GHCR `ghcr.io/autoboat-vt/telemetry_server[:latest|:testing|:vX.Y.Z]` (public); Docker Hub mirror `vtautoboat/telemetry_server` (public); GHCR `ghcr.io/autoboat-vt/telemetry_server-tailscale` (**private** — contains baked-in OAuth secret) |
| Branches | `main` = production, `testing` = staging |
| Domains | `vt-autoboat-telemetry.uk` + `www` → prod; `test.vt-autoboat-telemetry.uk` → test |

---

## 2. Repository layout

```
src/
  app.py                                  # WSGI entrypoint: `app = create_app()`
  autoboat_telemetry_server/
    __init__.py                           # App factory `create_app()`, CORS, blueprint registration, INSTANCE_DIR discovery
    models.py                             # TelemetryTable + HashTable SQLAlchemy models, after_insert hook for instance_identifier
    types.py                              # PEP 695 type aliases + DiagnosticMessageIntensity IntEnum
    lock_manager.py                       # ReaderWriterLock + decorator-based require_read_lock / require_write_lock
    routes/
      __init__.py                         # Re-exports the four endpoint classes + full route map docstring
      autopilot_parameters.py             # CRUD for autopilot params, config hashes, descriptions
      boat_status.py                      # Boat status get/set/set_fast/set_mapping (ctypes-aligned binary fast updates)
      waypoints.py                        # Waypoint sequence get/set
      instance_manager.py                 # Instance lifecycle: create/delete/clean, user/name/diagnostic, get_ids, etc.
  instance/
    config.py                             # SQLAlchemy binds (instances.db + hashes.db), CORS_ORIGINS (the key create_app reads)
    instances.db, hashes.db               # SQLite DBs (gitignored, persisted via named volume in compose)
docker/
  app-entrypoint.sh                       # Restores config.py into the mounted instance volume (no-clobber)
  README.md                               # Full Docker deployment docs (services, routing, tailscale, policy file)
  cloudflared/
    config.yml                            # File-managed tunnel config (only used when USE_CONFIG_FILE=1)
    entrypoint.sh                         # (legacy) shell wrapper — upstream image is distroless, override `command:` instead
  cron/
    Dockerfile                            # Alpine + curl + crond
    cron-entrypoint.sh                    # Hits DELETE /instance_manager/clean_instances every 5 min on prod
  tailscale/
    Dockerfile                            # FROM tailscale/tailscale:latest, bakes OAuth creds as ENV (TS_AUTHKEY, NOT TS_CLIENT_SECRET — see §9)
tailscale/
  policy.hujson                           # Tailnet ACL source of truth (synced by .github/workflows/tailscale.yml)
scripts/                                  # Misc helper scripts
tests/                                    # pytest suite (conftest.py + test_*.py; run with `pytest`)
.github/
  instructions/                           # Per-path agent instruction files (applyTo-gated; see tests.instructions.md)
  workflows/
    build.yml                             # Per-arch build (amd64 on ubuntu-22.04, arm64 on ubuntu-22.04-arm), pushes -arch tags on push only
    push.yml                              # Triggered by build.yml via workflow_run; assembles multi-arch manifests on GHCR, mirrors to Docker Hub
    tailscale.yml                         # tailscale/gitops-acl-action: `test` on PR, `apply` on push to main
  scripts/
    compute-release-tags.sh               # Emits base tags (main -> main+latest; v1.2.3 -> 1.2.3 1.2 1 latest) or arch-suffixed tags
  dependabot.yml                          # Weekly pip + github-actions updates
Dockerfile                                # App image: ubuntu user, venv at /home/ubuntu/telemetry_server/venv, gunicorn CMD
docker-compose.yml                        # telemetry-prod, telemetry-test, cloudflared, cron, tailscale (opt-in profile)
install.sh                                # One-shot cloud VM installer (installs Docker, clones repo, writes .env, brings up stack)
pyproject.toml                            # PEP 621 metadata + deps + optional dev extras
ruff.toml                                 # Ruff config (ALL rules + curated ignore list, numpy docstrings, 130 cols)
TODO.md                                   # Open feature ideas (image storage, version-control node, websockets)
```

---

## 3. Critical invariants — DO NOT BREAK

These are subtle, hard-won facts. Violating them silently breaks production.

### 3.1 The instance directory is *discovered at runtime*, not hardcoded

`create_app()` in `src/autoboat_telemetry_server/__init__.py` scans `/home` for
user directories:

- **Exactly one** user dir in `/home` → use it as `HOME_DIR`.
- **Zero** user dirs → `RuntimeError` (app won't start).
- **Multiple** user dirs → fall back to `Path.home()`.

`INSTANCE_DIR = HOME_DIR / "telemetry_server" / "src" / "instance"`.

**Implication:** the container filesystem MUST contain exactly one user dir at
`/home` matching the deployment layout `/home/ubuntu/telemetry_server/src/instance`.
The Dockerfile creates `ubuntu` and lays the source out under `/home/ubuntu/telemetry_server`.
Do not rename the user, do not move `src/instance`, and do not introduce a
second `/home/*` directory in the image.

### 3.2 `src/instance/` is a named volume; `config.py` is restored on first start

`docker-compose.yml` mounts `prod-instance-data` (and `test-instance-data`)
**over** `/home/ubuntu/telemetry_server/src/instance`. On first start the
mounted dir is empty, which would hide the baked-in `config.py`. The
`docker/app-entrypoint.sh` script copies `/opt/config.py` (backed up during
image build) into the instance dir **only if it doesn't already exist**
(no-clobber). This means:

- Site-specific edits to `config.py` survive image updates.
- You MUST NOT overwrite `config.py` from the entrypoint if it exists.
- If you change `src/instance/config.py` in the repo, existing deployments will
  NOT pick up the change unless the operator manually deletes the file from
  the volume. Document this in the release notes.

### 3.3 The `user` field on a telemetry instance is immutable after first set

`TelemetryTable.validate_user` raises `ValueError` if you try to change `user`
after it's been set to a non-`"unknown"` value. The intended flow is:
telemetry node calls `set_user` once at boot; the field is then locked. Do not
"fix" this by relaxing the validator — it's a safety guarantee that the
instance's owner can't be silently swapped.

### 3.4 Boat status fast updates depend on ctypes alignment + field order

`/boat_status/set_fast/<instance_id>` accepts a binary payload whose decode
path branches on payload byte length to handle ctypes alignment differences.
The decode builds a **dynamic `ctypes.LittleEndianStructure` subclass with
`_pack_ = 1`** from the instance's `boat_status_mapping` (each entry is
`[field_name, field_type]`, e.g. `["heading", "c_float"]`), then calls
`from_buffer_copy(payload)` to materialize the struct and walks the
`_fields_` to extract values by name back into the JSON `boat_status` dict.

Three hard rules:

1. **Payload field order MUST match `boat_status_mapping` for the instance
   exactly.** `from_buffer_copy` is positional — field N in the struct maps to
   bytes `[offset_N, offset_N + sizeof_N)`. If you add a field to the mapping
   or reorder it, fast updates will silently decode to garbage. Coordinate
   with the boat firmware.
2. **Don't "simplify" the length-based branching.** It exists because
   different boat builds emit differently-aligned structs (the length probe
   distinguishes a packed payload from a padded one). Removing it breaks one
   build or the other.
3. **Field types must be valid `ctypes` attribute names.**
   `set_mapping_route` validates each entry with `is_valid_pair` (a list of
   exactly two strings) and `hasattr(ctypes, field_type)` — so `"c_float"`,
   `"c_int"`, `"c_uint8"`, etc. are accepted, but `"float"` or `"int32"` are
   rejected with a 400. Don't invent type names that aren't in the `ctypes`
   module.

See `/memories/repo/telemetry_server_notes.md` for the firmware coordination
history.

### 3.5 `instance_identifier` is auto-set by an `after_insert` event

`models.py:set_instance_identifier` runs an `UPDATE` on the just-inserted row
to set `instance_identifier = f"Unnamed instance #{instance_id}"` if it wasn't
supplied. Don't duplicate this logic in route code, and don't remove the event
listener — the default name depends on it.

### 3.6 All route handlers go through the shared reader-writer lock

`shared_lock_manager` (module-level singleton in `__init__.py`) wraps reads
with `require_read_lock` and writes with `require_write_lock`. New routes must
follow the same pattern — SQLite + Gunicorn with a single worker is safe under
the lock, but adding unlocked handlers risks torn reads / lost updates.

**The two decorators have different failure modes — choose deliberately:**

- `require_read_lock` is **blocking**. A reader waits as long as needed for
  any writer (or other readers) to finish. Readers never fail; they just wait.
- `require_write_lock` is **non-blocking**
  (`acquire_write(blocking=False)`). If a writer can't acquire the lock
  immediately, the handler never runs — the decorator returns
  `jsonify("Write operation in progress. Please try again later."), 429`
  directly. The client sees an HTTP 429, not a server error.

This asymmetry is deliberate: readers (the website polling for boat
positions) are latency-tolerant and can wait; writers (the boat pushing a
status update) should not queue up behind a long-running read and should
retry on 429 instead.

**Critical corollary:** the `get_new/<instance_id>` routes on
`autopilot_parameters`, `boat_status`, and `waypoints` are decorated with
`require_write_lock`, **not** `require_read_lock`, even though they're GETs.
This is because they mutate state — they clear the `*_new_flag` after reading.
If you copy a `get_new` route as a template for a pure read, switch the
decorator to `require_read_lock`.

### 3.7 The Cloudflare Tunnel is outbound-only — do not open inbound ports

The host (originally macOS behind NAT, now typically a cloud VM) does NOT
accept inbound 80/443. `cloudflared` dials out to Cloudflare's edge; the edge
terminates TLS and proxies back over the tunnel. **Never** reintroduce nginx,
certbot, or any inbound-port-based ingress. History lesson in
`/memories/repo/docker_migration.md`: DNS-01 fixed cert issuance but not
serving, because inbound 443 was still blocked. Only a tunnel solves both.

### 3.8 Tunnels route by hostname, not port

That's why `test` lives at `test.vt-autoboat-telemetry.uk` (subdomain) instead
of `:8443`. The three public hostnames map to internal `http://telemetry-*:port`
services:

| Hostname | Service |
| --- | --- |
| `vt-autoboat-telemetry.uk` | `http://telemetry-prod:8000` |
| `www.vt-autoboat-telemetry.uk` | `http://telemetry-prod:8000` |
| `test.vt-autoboat-telemetry.uk` | `http://telemetry-test:6001` |

Routing is configured in the Cloudflare Zero Trust dashboard (dashboard-managed
tunnel, recommended) or in `docker/cloudflared/config.yml` (file-managed,
`USE_CONFIG_FILE=1`).

### 3.9 The Tailscale image uses `TS_AUTHKEY`, NOT `TS_CLIENT_SECRET`

This is a workaround for a **containerboot v1.98 bug** where
`TS_CLIENT_ID` + `TS_CLIENT_SECRET` causes a 403 on `check-prefs` before OAuth
auth completes. The Dockerfile bakes the OAuth secret into `TS_AUTHKEY` (per
Tailscale docs, an OAuth client secret is accepted there) and MUST NOT also set
`TS_CLIENT_ID` (containerboot explicitly rejects that combination).
`TS_EXTRA_ARGS=--advertise-tags=tag:server --ssh` is still required in
`docker-compose.yml` because OAuth-registered nodes must be tagged. See
`/memories/repo/tailscale_oauth.md` before touching the tailscale image.

### 3.10 The tailscale image is PRIVATE on GHCR (contains a secret)

`ghcr.io/autoboat-vt/telemetry_server-tailscale:latest` has the OAuth client
secret baked in. It MUST stay **Internal** visibility (org members only) on
GHCR — never make it Public, never mirror it to Docker Hub (Docker Hub is
public-only for free accounts). Hosts must `docker login ghcr.io` with a PAT
(`read:packages` scope) before `docker compose --profile tailscale pull`.

### 3.11 `TUNNEL_TOKEN` and `TS_OAUTH_*` live in specific GitHub namespaces

- `TUNNEL_TOKEN` → **org variable** `vars.TUNNEL_TOKEN` (plaintext, scoped to
  this repo). Referenced in workflows as `${{ vars.TUNNEL_TOKEN }}`. Host still
  reads it from `.env` at runtime.
- `TS_OAUTH_ID` → org **variable** `vars.TS_OAUTH_ID` (client ID, non-secret).
- `TS_OAUTH_SECRET` → org **secret** `secrets.TS_OAUTH_SECRET` (client secret).
- `TS_TAILNET` → org **variable** `vars.TS_TAILNET` (tailnet name, non-secret).
- `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` → repo secrets (for the mirror push).

`secrets.*` and `vars.*` are SEPARATE namespaces. Reading a var via `secrets.*`
resolves to empty string with no error — this caused a real 404 in the
tailscale workflow. Always use the right namespace.

### 3.12 Route error codes follow a shared convention — don't improvise

Every route handler uses the same try/except ladder, and the exception types
map to fixed status codes. Do not invent new codes or reshuffle the ladder:

| Exception | Status | Meaning |
| --- | --- | --- |
| `TypeError("Instance not found.")` (from `_get_instance`) | 404 | Instance ID doesn't exist. Note: some routes use 400 here for *input* `TypeError`s (see below). |
| `TypeError` (from input validation: bad JSON shape, wrong type) | 400 | Caller sent malformed data. |
| `ValueError` (from input validation: bad enum, dup name, hash mismatch) | 400 | Caller sent well-formed but invalid data. |
| Any other `Exception` | 500 | Unexpected; `db.session.rollback()` is called first on mutating routes. |

**Gotcha:** because `_get_instance` raises `TypeError`, routes that *also*
raise `TypeError` for input validation (e.g. `set_diagnostic_message`,
`set_route` on waypoints/autopilot_parameters) have a single `except TypeError`
clause that returns 404 on the former case and 400 on the latter — but the
status code is the same for both. The existing routes accept this ambiguity
(the message string distinguishes them). If you're adding a route that needs
to differentiate, use a custom exception, don't split the `TypeError` clause.

**`db.session.rollback()` is only called in the catch-all `except Exception`
on mutating routes** (POST/DELETE). Pure GET routes don't touch the session,
so they don't roll back. If you add a GET that reads-then-writes (like
`get_new`), it's decorated with `require_write_lock` and the catch-all should
roll back — copy the `boat_status.get_new_route` pattern.

### 3.13 JSON columns don't track in-place mutations

`TelemetryTable`'s JSON columns (`boat_status`, `boat_status_mapping`,
`autopilot_parameters`, `default_autopilot_parameters`, `waypoints`,
`diagnostic_message`) are plain `mapped_column(JSON, ...)` — **no
`MutableDict` / `MutableList` wrapper**. SQLAlchemy tracks changes to these
columns by identity, so mutating a retrieved dict/list in place and
reassigning the same object is a no-op as far as the ORM is concerned — the
change won't persist on `db.session.commit()`.

This bit the `update_existing_parameter` route (it did
`current = inst.autopilot_parameters; current[key] = val;
inst.autopilot_parameters = current` — same object, no-op). The fix is to
**copy the container before mutating**:

```python
current = dict(telemetry_instance.autopilot_parameters)
current[key] = new_value
telemetry_instance.autopilot_parameters = current  # different object -> dirty
```

If you add a route that mutates a JSON column in place, do the same — or
switch the column to `MutableDict.as_mutable(JSON)` (requires an import and
a migration consideration). The wholesale-replacement routes (`set_route` on
each domain) don't have this problem because they assign a brand-new object.

### 3.14 `config.py` must define `CORS_ORIGINS`, not `DEFAULT_CORS_ORIGINS`

`create_app()` resolves the CORS allowlist from three sources, in fixed
precedence (highest first):

1. `CORS_ORIGINS` env var (comma-separated) — works on existing deployments
   without rebuilding, since `src/instance/config.py` is persisted in a named
   volume and not overwritten on image updates.
2. `app.config["CORS_ORIGINS"]` (set in `src/instance/config.py`) — applies on
   fresh installs where `config.py` is seeded from the image.
3. `DEFAULT_CORS_ORIGINS` (module-level fallback in
   `src/autoboat_telemetry_server/__init__.py`) — the known website +
   telemetry origins.

`create_app()` reads level 2 via `app.config.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)`.
Flask's `from_pyfile` loads config module names **by their own name**, so the
key in `config.py` MUST be `CORS_ORIGINS`. Naming it `DEFAULT_CORS_ORIGINS`
silently breaks level 2: Flask loads it into
`app.config["DEFAULT_CORS_ORIGINS"]` (a key nothing reads) and the override
is dead — the module-level fallback wins instead.

This was a real bug (caught by a CodeQL "unused variable" finding that turned
out to be a live defect). `tests/test_init.py::TestCorsPrecedence` pins all
three levels and the `config.py` key name so the drift can't recur. If you
touch either CORS list, keep them in sync (the `www.autoboat.aoe.vt.edu`
entry once drifted between the two) and update the `TestDefaultCorsOrigins`
tests to match.

---

## 4. Code style

- **Formatter/linter:** Ruff, configured in `ruff.toml`. `select = ["ALL"]`
  with a long curated `ignore` list (notable: `S101` allows `assert` in tests,
  `T201` allows `print`, `D100/D101/D103/D107` disable module/class/method/
  `__init__` docstring requirements, `PTH` disables pathlib suggestions so
  `os.path` is fine, `PLR0913` allows many positional args, `TRY400` lets you
  use `logging.error` instead of `logging.exception`).
- **Line length:** 130. Indent: 4 spaces. Quotes: double. Line ending: native.
- **Docstrings:** numpy convention (`[lint.pydocstyle] convention = "numpy"`).
  All public functions/classes/methods should have them. Parameters and
  returns go in dedicated `Parameters` / `Returns` / `Raises` sections.
- **Type hints:** PEP 695 style is in use (`type X = ...`, `def f[T](...)`).
  `from __future__ import annotations` is NOT used — `ruff.toml` sets
  `future-annotations = true` for analysis purposes but the runtime is 3.12
  which supports the new syntax natively.
- **Imports:** stdlib → third-party → first-party. `noqa: E402` is acceptable
  for imports that must come after runtime path setup (see `__init__.py`).
- **Magic trailing comma:** disabled (`skip-magic-trailing-comma = true`) —
  don't rely on trailing commas to force one-per-line formatting.
- **Tests:** the test suite lives in `tests/` at the repo root and uses
  `pytest` (included in the `dev` extras via `pip install -e ".[dev]"`).
  `pyproject.toml` configures pytest with `testpaths = ["tests"]` and
  `pythonpath = ["src"]`. `tests/conftest.py` bootstraps the package import
  on non-Linux dev machines (the package's `__init__.py` scans `/home` at
  import time, which fails on macOS) and provides `tmp_instance_dir` / `app` /
  `client` / `db_session` fixtures with per-test temp DBs. `assert` is fine
  (`S101` is ignored). Test files have relaxed ruff rules via
  `[lint.per-file-ignores]` in `ruff.toml` (D102, ANN001, ANN201, PLC0415,
  PT018). Run tests with `pytest` and lint them with `ruff check tests/` /
  `ruff format tests/`. See `.github/instructions/tests.instructions.md`
  (auto-attached when editing `tests/**`) for the full conventions: the
  `/home` bootstrap, fixture selection, the deferred-import pattern, route
  testing via the Flask test client, and where to add new tests.

Run linting/formatting before committing:

```bash
ruff check .
ruff format --check .
```

---

## 5. Adding or modifying routes

Routes live in `src/autoboat_telemetry_server/routes/<domain>.py`. Each file
defines an `*Endpoint` class that constructs a `Blueprint` in `__init__` and
registers routes in `_register_routes()`. The blueprint is registered by
`create_app()` in `__init__.py`.

When adding a route:

1. Pick the right file (or create a new one following the existing pattern).
2. Use the `@shared_lock_manager.require_read_lock` decorator for GETs and
   `@shared_lock_manager.require_write_lock` for anything that mutates state.
3. Return `ResponseType` (i.e. `tuple[Response, int]`) for JSON routes, or a
   `Literal[...]` for trivial test routes.
4. Use `self._get_instance(instance_id)` to load the `TelemetryTable` row — it
   raises `TypeError("Instance not found.")` which the existing handlers
   catch and convert to a 404. Don't reinvent this lookup.
5. Update the route map docstring at the top of
   `src/autoboat_telemetry_server/routes/__init__.py` so the surface stays
   discoverable.
6. If the route should be reachable cross-origin from the browser (most should
   be — the website fetches positions from this API), no extra CORS config is
   needed; `CORS(app, origins=...)` in `create_app()` applies globally.

### Route URL conventions

- `/<domain>/test` — a trivial GET that returns a literal string. Used for
  health checks. Keep these. **Not lock-decorated** — it doesn't touch the DB.
- `/<domain>/get/<int:instance_id>` — current value.
  `@require_read_lock`.
- `/<domain>/get_new/<int:instance_id>` — returns the value only if the
  `*_new_flag` is set, then clears the flag. Used by polling consumers that
  only want fresh data. **`@require_write_lock`** (not read!) because it
  mutates the flag. If the flag is `False`, returns `jsonify({}), 200`.
- `/<domain>/set/<int:instance_id>` — replace the stored value from the
  request body. `@require_write_lock`. Sets `*_new_flag = (old != new)` so
  polling consumers see a fresh value only on actual change.
- `/<domain>/set_fast/<int:instance_id>` — binary fast-path
  (`boat_status` only; see §3.4).
- `/<domain>/set_mapping/<int:instance_id>` — define the field order/types
  for the fast path (`boat_status` only; see §3.4).

### Request body parsing — the `json.loads(request.json)` gotcha

Several `autopilot_parameters` routes do `new_parameters = json.loads(request.json)`.
This looks redundant (Flask's `request.json` already parses JSON), but it's
deliberate: the boats' telemetry node sends the JSON body as a **JSON-encoded
string** (i.e. the body is a JSON string whose content is itself JSON), so
`request.json` returns a `str` and `json.loads` unpacks it to a dict. Do not
"simplify" this to `request.json` directly — it will silently break the boat
firmature integration. Routes that follow this pattern: `set_route`,
`set_default_route`, `create_config_route`, `update_existing_parameter_route`.

### Autopilot parameters — config hash lifecycle

`HashTable` stores named autopilot config snapshots. The flow is:

1. **Create a config:** `POST /autopilot_parameters/create_config` with a
   config dict. `HashTable.validate_config` checks it's a dict, non-empty,
   and each value is a dict containing both `"default"` and `"description"`
   keys. `HashTable.compute_hash` returns `sha256(json.dumps(config,
   sort_keys=True, separators=(",", ":")))` (deterministic — key order and
   whitespace don't change the hash). If the hash doesn't already exist, a
   new `HashTable` row is inserted and the hash is returned.
2. **Apply to an instance:** `POST /autopilot_parameters/set_default/<id>`
   validates + hashes the provided config, creates the `HashTable` row if
   new, then sets `default_autopilot_parameters`, `current_config_hash`, and
   resets `autopilot_parameters` to `{key: value["default"] for ...}` (the
   defaults from the config). `set_default_from_hash/<id>/<hash>` does the
   same but loads an existing hash instead of accepting a new config body.
3. **Update runtime params:** `POST /autopilot_parameters/set/<id>` replaces
   `autopilot_parameters` wholesale. If `default_autopilot_parameters` is
   set, the new keys MUST match the default keys exactly (frozenset
   comparison) or it returns 400. Sets `autopilot_parameters_new_flag`
   based on whether the value actually changed.
4. **Update one param:** `POST
   /autopilot_parameters/update_existing_parameter/<id>/<key>` updates a
   single key in `autopilot_parameters`. The key must exist in
   `default_autopilot_parameters` (400 otherwise). The value must be a
   primitive (`str|int|float|bool|list`) — 400 otherwise.
5. **Describe / list:** `get_hash_description`, `set_hash_description`,
   `get_all_hashes`, `get_hash_exists`, `get_config/<hash>`, `get_hash/<id>`
   (current hash for an instance), `get_default/<id>` (default params).
6. **Delete:** `DELETE /autopilot_parameters/delete_config/<hash>` removes a
   `HashTable` row. Does NOT check whether any instance's
   `current_config_hash` points at it — deleting an in-use hash will leave
   dangling references. Don't call this on a hash that's currently applied.

### Instance manager — lifecycle and naming

- `POST /instance_manager/create` — creates a new `TelemetryTable` row. The
  `after_insert` hook (§3.5) sets `instance_identifier` to
  `f"Unnamed instance #{instance_id}"` if not supplied.
- `DELETE /instance_manager/delete/<id>` — single instance.
- `DELETE /instance_manager/delete_all` — all instances (no confirmation;
  destructive).
- `DELETE /instance_manager/clean_instances` — deletes instances whose
  `updated_at` is older than 5 minutes. **Called by the `cron` sidecar every
  5 minutes** (see `docker/cron/cron-entrypoint.sh`). The timeout is
  hardcoded at 5.0 minutes in the route — don't change it without updating
  the cron schedule to match.
- `POST /instance_manager/set_user/<id>/<user_name>` — sets `user`; locked
  after first non-`"unknown"` set (§3.3). Returns 400 on the immutability
  `ValueError`.
- `POST /instance_manager/set_name/<id>/<name>` — sets `instance_identifier`.
  Enforces uniqueness: scans all instances and returns 400 if another
  instance already has that name. (This is a table scan, not a DB constraint
  — don't rely on it being enforced at the DB level.)
- `POST /instance_manager/set_diagnostic_message/<id>` — body must be a
  JSON list of `[intensity, message]` where `intensity` is a
  `DiagnosticMessageIntensity` int (1=INFO, 2=WARNING, 3=ERROR) and
  `message` is a string. 400 on type/enum mismatch.
- `GET /instance_manager/get_id/<name>` — reverse lookup by name (returns
  the `instance_id`).
- `GET /instance_manager/get_instance_info/<id>` and `get_all_instance_info`
  — return `to_dict()` of the row(s).
- `GET /instance_manager/get_ids` — returns `TelemetryTable.get_all_ids()`
  (a classmethod).

### Waypoints

- `GET /waypoints/get/<id>` — current waypoints (a list of `[x, y]` pairs).
- `GET /waypoints/get_new/<id>` — `@require_write_lock`; returns `{}` if
  no new waypoints, else the list and clears the flag.
- `POST /waypoints/set/<id>` — body must be a list of `[x, y]` pairs where
  each coordinate is `int|float`. Validates each point is a list/tuple of
  length 2 with numeric coords; 400 otherwise. Sets
  `waypoints_new_flag = True`.

---

## 6. Database changes

### 6.1 Models and binds

Models live in `src/autoboat_telemetry_server/models.py`. Two tables:

- **`TelemetryTable`** — the live state of every instance. Bound to the
  default bind (`None` key → `instances.db`). Columns include `instance_id`
  (PK, autoincrement), `user` (immutable after first set, §3.3),
  `instance_identifier` (auto-set by `after_insert` hook, §3.5),
  `boat_status` (JSON), `boat_status_mapping` (JSON), `boat_status_new_flag`,
  `autopilot_parameters` (JSON), `default_autopilot_parameters` (JSON),
  `autopilot_parameters_new_flag`, `current_config_hash` (FK-ish to
  `HashTable.config_hash`, but not enforced at the DB level), `waypoints`
  (JSON), `waypoints_new_flag`, `diagnostic_message` (JSON list),
  `created_at`, `updated_at` (timezone-aware UTC).
- **`HashTable`** — named autopilot config snapshots. Bound to the
  `"hashes"` key → `hashes.db` (via `__bind_key__ = "hashes"`). PK is
  `config_hash` (a 64-char SHA-256 hex string). Columns: `config_hash`,
  `data` (the validated config dict), `description` (human-readable).

`HashTable` classmethods you must use (don't reimplement):

- `compute_hash(config)` → `hashlib.sha256(json.dumps(config, sort_keys=True,
  separators=(",", ":")).encode()).hexdigest()`. **Deterministic:** key order
  and whitespace in the input don't affect the hash. Two configs with the
  same keys/values produce the same hash regardless of how they were
  serialized by the client.
- `validate_config(config)` → `(bool, str)`. Returns `(True, "")` if valid,
  `(False, message)` otherwise. Rules: must be a `dict`, non-empty, and each
  value must itself be a `dict` containing both `"default"` and
  `"description"` keys. This is what `set_default` and `create_config`
  call before storing — don't bypass it.
- `check_hash_exists(config_hash)` → `bool`. Used to avoid duplicate
  `HashTable` rows for the same config.

`TelemetryTable` helpers:

- `get_all_ids()` classmethod → list of all `instance_id`s.
- `to_dict()` → serializes the row for `get_instance_info` /
  `get_all_instance_info`.
- `validate_user` validator — enforces §3.3 immutability.

### 6.2 No migration framework

There is **no migration framework** (no Alembic, no Flask-Migrate).
`create_app()` calls `db.create_all()` on startup, which only creates
missing tables — it does NOT alter existing ones. Schema changes to an
existing table require either:
  1. A manual `ALTER TABLE` / data backfill script run against the SQLite file
     in the named volume, OR
  2. Bumping the volume (delete `prod-instance-data` / `test-instance-data`),
     which **destroys all telemetry history**.

Prefer additive changes (new columns with defaults, new tables). Document
any breaking schema change in `README.md` and the release notes.

### 6.3 SQLite + single worker is intentional

SQLite + Gunicorn with `-w 1` is intentional — the in-process
`ReaderWriterLock` serializes access. Do not raise the worker count without
switching to a different DB or a cross-process lock (file lock, Postgres
advisory lock, etc.). If you switch DBs, you can also drop the
reader-writer lock entirely (Postgres handles concurrent writers natively).

### 6.4 The `hashes` bind

The `hashes` bind is configured via `SQLALCHEMY_BINDS` in
`src/instance/config.py` — `None` key maps to `instances.db`, `"hashes"`
key maps to `hashes.db`. Both files live in `src/instance/` and are
gitignored. `HashTable` declares `__bind_key__ = "hashes"` so SQLAlchemy
routes its queries to `hashes.db` automatically; you never need to specify
the bind in query code.

---

## 7. Local development

```bash
# One-time:
pip install -e ".[dev]"          # installs the package + dev extras

# Run the app (development):
flask run --app autoboat_telemetry_server   # default Flask dev server

# Or with gunicorn (closer to prod):
gunicorn "autoboat_telemetry_server:create_app()"

# Lint:
ruff check .
ruff format --check .

# Build the wheel/sdist (for inspection, not for deployment — deployment is via Docker):
python -m build
```

The app expects to find `src/instance/config.py`. If you're running outside
the canonical `/home/ubuntu/telemetry_server/src/instance` layout (e.g. on a
macOS dev machine), `create_app()` will fall back to `Path.home()` and look for
`~/telemetry_server/src/instance/config.py`. The simplest local setup is to
symlink or copy `src/instance/config.py` to wherever it expects, or to run
inside Docker:

```bash
docker compose up -d --build telemetry-prod   # build & start just the prod app
docker compose logs -f telemetry-prod
```

---

## 8. Docker & deployment

### 8.1 The four core services (default profile)

| Service | Image | Container | Notes |
| --- | --- | --- | --- |
| `telemetry-prod` | `ghcr.io/autoboat-vt/telemetry_server:latest` | `telemetry-prod` | Gunicorn on `:8000`. Pulls prebuilt image by default; pass `--build` to build locally. |
| `telemetry-test` | `ghcr.io/autoboat-vt/telemetry_server:testing` | `telemetry-test` | Same image, `:testing` tag (built from `testing` branch), override command binds `:6001`. |
| `cloudflared` | `cloudflare/cloudflared:latest` | `telemetry-cloudflared` | Distroless. Override `command:` with `tunnel run --token $TUNNEL_TOKEN`. |
| `cron` | (built locally from `docker/cron/Dockerfile`) | `telemetry-cron` | Alpine + curl + crond. Hits `DELETE /instance_manager/clean_instances` on prod every 5 min. |

### 8.2 Optional `tailscale` profile

```bash
docker compose --profile tailscale up -d
```

Host networking, root user, `cap_add: [NET_ADMIN, NET_RAW]`, mounts
`/dev/net/tun`. Adds the host to the tailnet as `telemetry-server`. See §3.9
and §3.10 for the auth/visibility constraints.

### 8.3 Common commands

```bash
docker compose up -d                              # start the 4 default services
docker compose up -d --build                      # rebuild the app image from source
docker compose pull                               # pull latest prebuilt images
docker compose ps                                 # status
docker compose logs -f telemetry-prod             # follow app logs
docker compose logs -f cloudflared                # follow tunnel logs (look for "Registered tunnel connection")
docker compose --profile tailscale up -d          # also start tailscale sidecar
docker compose down                               # stop all services (volumes preserved)
docker compose down -v                            # ⚠ DELETES all volumes (DBs gone!)
TUNNEL_TOKEN=dummy docker compose down            # override the ${TUNNEL_TOKEN:?} guard if .env is missing
```

### 8.4 .env / .env.example

`.env` is gitignored (contains the tunnel token). `.env.example` documents
`DOMAIN`, `TESTING_DOMAIN`, `TUNNEL_TOKEN`, `USE_CONFIG_FILE`, `TUNNEL_ID`,
and `CORS_ORIGINS`. Never commit `.env`.

### 8.5 .dockerignore exclusions

`.dockerignore` excludes `.git`, `.github`, `.vscode`, caches, build artifacts,
`venv/`, `/instance/` (repo-root stray), logs, and most of `docker/` (the cron
and cloudflared subdirs aren't needed in the app image). It explicitly keeps
`docker/app-entrypoint.sh` (the Dockerfile `COPY`s it). If you add a new file
to `docker/` that the app image needs, update `.dockerignore`'s `!docker/...`
exception.

---

## 9. CI / release workflow

Two-stage build-and-publish, mirroring the pattern from
`autoboat-vt/autoboat_vt`, with a test gate in front:

1. **`.github/workflows/build.yml`** — runs on push to `main`/`testing`, on
   tags `v*`, on PRs to `main`/`testing`, and on `workflow_dispatch`. Two
   jobs:

   - **`test` job** (non-matrixed, runs first on every trigger including
     PRs): sets up Python 3.12, `pip install -e ".[dev]"`, then runs
     `ruff check .`, `ruff format --check .`, and `pytest`. Gates the `build`
     job via `needs: test` so a failing test fails fast before Docker build
     minutes are spent. **Do not remove `needs: test` from `build`** — the
     whole point is to keep broken code out of images. If you need to force
     a build past a failing test in an emergency, run the `build` job alone
     via `workflow_dispatch` instead of editing out the gate.
   - **`build` job** (matrixed, `needs: test`): `amd64` (ubuntu-22.04) and
     `arm64` (ubuntu-22.04-arm, native runner). Pushes per-arch tags
     (`:main-amd64`, `:main-arm64`, etc.) **only on push** (not PR — fork
     PRs can't access org secrets). Also builds the custom tailscale image
     (with OAuth creds as build-args) on push only.

2. **`.github/workflows/push.yml`** — triggered by `workflow_run` on
   `build.yml` completion. Combines per-arch tags into multi-arch manifests
   via `docker buildx imagetools create`, then mirrors the finished manifest
   to Docker Hub. Tailscale image manifests are assembled on GHCR only (not
   mirrored — the image is private).

3. **`.github/workflows/tailscale.yml`** — runs the
   `tailscale/gitops-acl-action@v1` on changes to `tailscale/policy.hujson`.
   `test` mode on PR (validate only), `apply` mode on push to main (validate +
   push to tailnet).

### Tag computation

`.github/scripts/compute-release-tags.sh` emits the tag list:
- Branch push to `main` → `main latest`
- Branch push to `testing` → `testing`
- Tag `v1.2.3` → `1.2.3 1.2 1 latest`

The build job calls it with `base` mode for the per-arch suffixed tags, the
publish job calls it with `base` mode for the multi-arch manifest tags.

### GHCR cleanup

GHCR has no built-in retention policy. The publish job deletes untagged
versions and versions whose only tags end in `-amd64`/`-arm64` (intermediate
per-arch images) via the Packages API, with `continue-on-error: true` so a
transient API failure doesn't block publishing. The repo's role on the package
must be **Admin** (not Write) for the `GITHUB_TOKEN` to delete versions — set
this in the package settings UI under "Manage Actions access". See
`/memories/repo/ghcr_cleanup.md`.

---

## 10. Secrets & credentials cheat sheet

| Secret | Where it lives | Used by | Notes |
| --- | --- | --- | --- |
| `TUNNEL_TOKEN` | `.env` on host + GitHub org **variable** `vars.TUNNEL_TOKEN` | `docker-compose.yml` (cloudflared `command:`) | Plaintext org var for team self-service. Rotate in both places. |
| `TS_OAUTH_ID` | GitHub org **variable** `vars.TS_OAUTH_ID` | `build.yml` (build-arg for tailscale image) | Client ID, non-secret (starts with `k`). |
| `TS_OAUTH_SECRET` | GitHub org **secret** `secrets.TS_OAUTH_SECRET` | `build.yml` (build-arg) + `tailscale.yml` (action input) | Client secret (starts with `tskey-client-`). Baked into the private tailscale image. |
| `TS_TAILNET` | GitHub org **variable** `vars.TS_TAILNET` | `tailscale.yml` | Tailnet name e.g. `beetal-spica.ts.net`. Non-sensitive. |
| `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | Repo **secrets** | `push.yml` | For the Docker Hub mirror push. |
| Cloudflare OAuth client (policy_file scope) | Tailscale admin console | `tailscale.yml` action | Same client as the sidecar (one client, both `devices:core` and `policy_file` scopes). |

**Never** put any of these in code, in commit messages, or in PR descriptions.
The tailscale image is private specifically because it contains
`TS_OAUTH_SECRET` baked in — if you ever change how the tailscale image is
built, double-check it's still private on GHCR.

---

## 11. Commit message conventions

This repo doesn't enforce conventional commits, but the existing history uses
short lowercase prefixes:

- `ci: ...` — CI/workflow changes
- `docker: ...` — Dockerfile / compose / entrypoint changes
- `tailscale: ...` — tailscale sidecar or policy file changes
- `feat: ...` / `fix: ...` — app code
- `docs: ...` — README/docs only

Keep messages in the imperative mood ("add route", not "added route").

---

## 12. Things that look wrong but aren't

- **`testing` is a branch, not a directory.** The `:testing` image tag is
  built from the `testing` branch; `telemetry-test` in compose uses that tag.
- **`telemetry-test` uses the same image as `telemetry-prod` by default** if
  you build locally without the `:testing` tag. The compose file's
  `image: ghcr.io/.../telemetry_server:testing` only takes effect after a
  `docker compose pull`. To run truly different code in `telemetry-test`,
  point its `build.context` at a separate checkout of the `testing` branch.
- **`TS_AUTHKEY` is set to an OAuth client secret, not an auth key.** Per
  Tailscale docs, an OAuth secret is accepted in `TS_AUTHKEY` as long as you
  also pass `--advertise-tags=tag:<tag>`. This is the workaround for the
  containerboot v1.98 403 bug — see §3.9.
- **The `cron` service is built locally, not pulled.** It has no `image:`
  line pointing at a registry (only `image: telemetry-cron:latest` as a local
  tag). `docker compose pull` skips it. `docker compose up -d` builds it.
- **The cloudflared image has no shell.** It's distroless. Don't try to
  `docker exec` into it or use a shell entrypoint. Override `command:` in
  compose directly.
- **`flask run` works without `FLASK_APP`** because `src/app.py` defines
  `app = create_app()` at module scope and the package is installed
  editable.
- **`ruff.toml` ignores `PTH` (use `os.path` instead of `pathlib`).** This is
  deliberate — the codebase predates the pathlib migration preference. Don't
  mass-rewrite `os.path` calls without checking with the maintainer.

---

## 13. When in doubt

- Read the corresponding route file before changing behavior — the docstring
  at the top of `routes/__init__.py` is the canonical route map.
- Check `/memories/repo/*.md` for the deep context on past decisions (docker
  migration, tailscale OAuth, tunnel token, GHCR cleanup). These were paid
  for in debugging hours; don't pay again.
- For infra changes (compose, Dockerfile, workflows), update `README.md`
  and `docker/README.md` in the same PR.
- For secrets/credential changes, document the rotation procedure in
  `docker/README.md` and the relevant memory file.

## 14. Working Style Notes

- **Terminal output exceeds scrollback** in this environment. Redirect long
  output to `/tmp/*.log` and `read_file` it back rather than reading terminal
  output directly.
- When making multiple independent edits, batch them for efficiency.
- Prefer reading large file chunks over many small reads.
- Don't pass `...existing code...` markers or omitted-line markers to edit
  tools - include exact literal text with 3-5 lines of context before and
  after.
- If a task touches routes, models, and Docker config, update all three in
  the same pass rather than leaving the repo half-finished.
- Use the existing repo commands (`ruff check .`, `ruff format --check .`,
  `docker compose up -d --build`) before reporting success; do not rely on
  assumptions or partial inspection.
- After Python edits, run `ruff check --fix` and `ruff format` on the changed
  files, then run `pytest` to confirm the test suite still passes. Tests live
  in `tests/` at the repo root (see §4).
- For route changes, update the route map docstring at the top of
  `src/autoboat_telemetry_server/routes/__init__.py` so the surface stays
  discoverable.
- For schema changes, remember there is **no migration framework** (§6.2).
  Prefer additive changes (new columns with defaults, new tables). Document
  any breaking schema change in `README.md` and the release notes.
