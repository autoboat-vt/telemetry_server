---
description: "Use when editing Python source files in src/autoboat_telemetry_server/, including the Flask app factory, models, types, lock manager, and route handlers. Covers code style, route conventions, lock usage, and the instance-directory invariant."
applyTo: "src/autoboat_telemetry_server/**/*.py, src/app.py, src/instance/config.py"
---

# Python source — `src/autoboat_telemetry_server/`

## App factory & instance directory

`create_app()` in `src/autoboat_telemetry_server/__init__.py` is the only entry
point. It discovers the instance directory at runtime by scanning `/home`:

- Exactly one user dir in `/home` → use it as `HOME_DIR`.
- Zero user dirs → `RuntimeError`.
- Multiple user dirs → fall back to `Path.home()`.

`INSTANCE_DIR = HOME_DIR / "telemetry_server" / "src" / "instance"`.

**Do not** hardcode `/home/ubuntu` in app code — the discovery logic exists so
the same code runs in the container (one user, `ubuntu`) and on a developer
machine. If you need the instance dir, import `INSTANCE_DIR` from the package
root.

`create_app()`:
1. Loads `config.py` from `INSTANCE_DIR`.
2. Resolves CORS origins (env `CORS_ORIGINS` > `app.config["CORS_ORIGINS"]` > `DEFAULT_CORS_ORIGINS`).
3. Initializes SQLAlchemy and runs `db.create_all()` (creates missing tables
   only — no migrations).
4. Registers the four blueprints: `InstanceManagerEndpoint`,
   `AutopilotParametersEndpoint`, `BoatStatusEndpoint`, `WaypointEndpoint`.
5. Adds a trivial `/` index route.

## Route handler pattern

Routes are organized into `*Endpoint` classes in
`src/autoboat_telemetry_server/routes/<domain>.py`. Each class:
- Constructs a `Blueprint` in `__init__` with `url_prefix="/<domain>"`.
- Registers routes inside `_register_routes()` (decorator style, closures over
  `self`).
- Exposes the blueprint via a `blueprint` property.

When adding a route:

1. Pick the right file. If creating a new domain, follow the existing class
   pattern and register it in `create_app()` and in `routes/__init__.py`.
2. **Always** wrap the handler:
   - `@shared_lock_manager.require_read_lock` for GETs.
   - `@shared_lock_manager.require_write_lock` for POST/PUT/DELETE or anything
     that mutates `TelemetryTable` / `HashTable`.
   This is non-negotiable — SQLite + a single Gunicorn worker relies on the
   in-process reader-writer lock for correctness.
3. Return type:
   - `ResponseType` (`tuple[Response, int]`) for JSON handlers — use
     `jsonify(...)` and an HTTP status code.
   - `Literal["..."]` for trivial test routes (`/<domain>/test`).
4. Use `self._get_instance(instance_id)` to look up a `TelemetryTable`. It
   raises `TypeError("Instance not found.")`; the existing handlers catch this
   and return `jsonify(str(e)), 404`. Don't reinvent the lookup.
5. Update the route map docstring at the top of `routes/__init__.py`.

### Lock decorators: blocking vs non-blocking

The two decorators have **different failure modes** — choose deliberately:

- `@require_read_lock` is **blocking**. A reader waits as long as needed for
  any writer (or other readers) to finish. Readers never fail; they just wait.
  Use this for pure GETs that don't mutate state.
- `@require_write_lock` is **non-blocking**
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
`@require_write_lock`, **not** `@require_read_lock`, even though they're GETs.
This is because they mutate state — they clear the `*_new_flag` after reading.
If you copy a `get_new` route as a template for a pure read, switch the
decorator to `@require_read_lock`.

### Error code convention

Every route handler uses the same try/except ladder. Don't improvise new
codes:

| Exception | Status | When |
| --- | --- | --- |
| `TypeError("Instance not found.")` (from `_get_instance`) | 404 | Instance ID doesn't exist. |
| `TypeError` (from input validation: bad JSON shape, wrong type) | 400 | Caller sent malformed data. |
| `ValueError` (from input validation: bad enum, dup name, hash mismatch) | 400 | Caller sent well-formed but invalid data. |
| Any other `Exception` | 500 | Unexpected; call `db.session.rollback()` first on mutating routes. |

**Gotcha:** because `_get_instance` raises `TypeError`, routes that *also*
raise `TypeError` for input validation (e.g. `set_diagnostic_message`,
`set_route` on waypoints/autopilot_parameters) have a single
`except TypeError` clause that returns 404 on the former case and 400 on the
latter — but the status code is the same for both. The existing routes accept
this ambiguity (the message string distinguishes them). If you need to
differentiate, use a custom exception, don't split the `TypeError` clause.

**`db.session.rollback()` is only called in the catch-all `except Exception`
on mutating routes** (POST/DELETE). Pure GET routes don't touch the session,
so they don't roll back. If you add a GET that reads-then-writes (like
`get_new`), it's decorated with `@require_write_lock` and the catch-all
should roll back — copy the `boat_status.get_new_route` pattern.

### URL conventions

- `/<domain>/test` — trivial GET, returns a literal string. Keep these.
  **Not lock-decorated** — it doesn't touch the DB.
- `/<domain>/get/<int:instance_id>` — current value.
  `@require_read_lock`.
- `/<domain>/get_new/<int:instance_id>` — returns the value only if
  `*_new_flag` is set, then clears the flag. Used by polling consumers.
  **`@require_write_lock`** (not read!) because it mutates the flag. If the
  flag is `False`, returns `jsonify({}), 200`.
- `/<domain>/set/<int:instance_id>` — replace the stored value from the
  request body. `@require_write_lock`. Sets `*_new_flag = (old != new)` so
  polling consumers see a fresh value only on actual change.
- `/<domain>/set_fast/<int:instance_id>` — binary fast-path
  (`boat_status` only; see "Boat status fast updates" below).
- `/<domain>/set_mapping/<int:instance_id>` — define the field order/types
  for the fast path (`boat_status` only; see "Boat status fast updates").

### Request body parsing — the `json.loads(request.json)` gotcha

Several `autopilot_parameters` routes do `new_parameters = json.loads(request.json)`.
This looks redundant (Flask's `request.json` already parses JSON), but it's
deliberate: the boats' telemetry node sends the JSON body as a **JSON-encoded
string** (i.e. the body is a JSON string whose content is itself JSON), so
`request.json` returns a `str` and `json.loads` unpacks it to a dict. Do not
"simplify" this to `request.json` directly — it will silently break the boat
firmware integration. Routes that follow this pattern: `set_route`,
`set_default_route`, `create_config_route`, `update_existing_parameter_route`.

Routes that take a raw JSON body directly (no double-encoding):
`boat_status.set_route`, `waypoints.set_route`,
`instance_manager.set_diagnostic_message`.

## Boat status fast updates

`/boat_status/set_fast/<instance_id>` accepts a binary payload. The decode
path branches on payload byte length to handle `ctypes` alignment differences
(packed vs aligned structs). The decode builds a **dynamic
`ctypes.LittleEndianStructure` subclass with `_pack_ = 1`** from the
instance's `boat_status_mapping` (each entry is `[field_name, field_type]`,
e.g. `["heading", "c_float"]`), then calls `from_buffer_copy(payload)` to
materialize the struct and walks the `_fields_` to extract values by name
back into the JSON `boat_status` dict.

Three hard rules:

1. **Payload field order MUST match `boat_status_mapping` for the instance
   exactly.** `from_buffer_copy` is positional — field N in the struct maps to
   bytes `[offset_N, offset_N + sizeof_N)`. If you add a field to the mapping
   or reorder it, the fast path will silently decode to garbage. Coordinate
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

`set_mapping_route` stores the validated mapping as JSON on the instance's
`boat_status_mapping` column. `set_fast_route` reads it back and rebuilds the
`ctypes` struct on every request — there's no caching.

## Models

`models.py` defines `TelemetryTable` (live state of every instance) and
`HashTable` (named autopilot config snapshots, keyed by SHA-256 hash).

### `HashTable` — config snapshots and hashing

`HashTable` is bound to `hashes.db` via `__bind_key__ = "hashes"`. PK is
`config_hash` (a 64-char SHA-256 hex string). Columns: `config_hash`,
`data` (the validated config dict), `description` (human-readable).

Classmethods you must use (don't reimplement):

- `compute_hash(config)` → `hashlib.sha256(json.dumps(config, sort_keys=True,
  separators=(",", ":")).encode()).hexdigest()`. **Deterministic:** key order
  and whitespace in the input don't affect the hash. Two configs with the
  same keys/values produce the same hash regardless of how they were
  serialized by the client. Always use this method — never hand-roll a hash.
- `validate_config(config)` → `(bool, str)`. Returns `(True, "")` if valid,
  `(False, message)` otherwise. Rules: must be a `dict`, non-empty, and each
  value must itself be a `dict` containing both `"default"` and
  `"description"` keys. This is what `set_default` and `create_config` call
  before storing — don't bypass it.
- `check_hash_exists(config_hash)` → `bool`. Used to avoid duplicate
  `HashTable` rows for the same config.

### `TelemetryTable` — live instance state

Bound to the default bind (`None` key → `instances.db`). Columns include
`instance_id` (PK, autoincrement), `user` (immutable after first set),
`instance_identifier` (auto-set by `after_insert` hook), `boat_status` (JSON),
`boat_status_mapping` (JSON), `boat_status_new_flag`, `autopilot_parameters`
(JSON), `default_autopilot_parameters` (JSON),
`autopilot_parameters_new_flag`, `current_config_hash` (FK-ish to
`HashTable.config_hash`, but not enforced at the DB level), `waypoints`
(JSON), `waypoints_new_flag`, `diagnostic_message` (JSON list),
`created_at`, `updated_at` (timezone-aware UTC).

Helpers:
- `get_all_ids()` classmethod → list of all `instance_id`s.
- `to_dict()` → serializes the row for `get_instance_info` /
  `get_all_instance_info`.
- `validate_user` validator — enforces the `user` immutability (see below).

### Invariants

- The `user` field on `TelemetryTable` is **immutable after first set**.
  `validate_user` raises `ValueError` if you try to change it away from a
  non-`"unknown"` value. Don't relax this — it's a safety guarantee that the
  instance's owner can't be silently swapped.
- `instance_identifier` is auto-set by an `after_insert` event listener
  (`set_instance_identifier`) to `f"Unnamed instance #{instance_id}"` if not
  supplied. Don't duplicate this logic in route code; don't remove the
  listener — the default name depends on it.
- `db.create_all()` only creates missing tables — it does NOT alter existing
  ones. There is no migration framework. Prefer additive schema changes
  (new columns with defaults, new tables). Breaking changes require a manual
  `ALTER TABLE` script or deleting the named volume (data loss).
- `current_config_hash` is **not a real FK**. Deleting a `HashTable` row that
  an instance points at will leave a dangling reference. The
  `delete_config_route` doesn't check — don't call it on an in-use hash.

### `SQLALCHEMY_BINDS`

`SQLALCHEMY_BINDS` in `src/instance/config.py`:
- `None` key → `instances.db` (the default bind, used by `TelemetryTable`).
- `"hashes"` key → `hashes.db` (used by `HashTable`, which declares
  `__bind_key__ = "hashes"`). You never need to specify the bind in query
code — SQLAlchemy routes based on the model's `__bind_key__`.

## Types

`types.py` uses PEP 695 type aliases (`type X = ...`). When adding a new
domain type, export it from `__all__` and prefer a `type` alias over a
`TypedDict` unless you actually need runtime validation. `DiagnosticMessageIntensity`
is an `IntEnum` (INFO=1, WARNING=2, ERROR=3) — the integer values are part of
the wire format, don't renumber them.

`ResponseType` is the standard return type for JSON route handlers
(`tuple[Response, int]`). Use it on every handler that returns
`jsonify(...), <status>`.

## Autopilot parameters — config hash lifecycle

`HashTable` stores named autopilot config snapshots. The flow is:

1. **Create a config:** `POST /autopilot_parameters/create_config` with a
   config dict. `HashTable.validate_config` checks it's a dict, non-empty,
   and each value is a dict containing both `"default"` and `"description"`
   keys. `HashTable.compute_hash` returns the SHA-256 (deterministic — key
   order and whitespace don't change the hash). If the hash doesn't already
   exist, a new `HashTable` row is inserted and the hash is returned.
2. **Apply to an instance:** `POST /autopilot_parameters/set_default/<id>`
   validates + hashes the provided config, creates the `HashTable` row if
   new, then sets `default_autopilot_parameters`, `current_config_hash`, and
   resets `autopilot_parameters` to `{key: value["default"] for ...}` (the
   defaults from the config). `set_default_from_hash/<id>/<hash>` does the
   same but loads an existing hash instead of accepting a new config body.
3. **Update runtime params:** `POST /autopilot_parameters/set/<id>` replaces
   `autopilot_parameters` wholesale. If `default_autopilot_parameters` is
   set, the new keys MUST match the default keys exactly (frozenset
   comparison) or it returns 400. Sets `autopilot_parameters_new_flag` based
   on whether the value actually changed.
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

## Instance manager — lifecycle and naming

- `POST /instance_manager/create` — creates a new `TelemetryTable` row. The
  `after_insert` hook sets `instance_identifier` to
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
  after first non-`"unknown"` set. Returns 400 on the immutability
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

## Waypoints

- `GET /waypoints/get/<id>` — current waypoints (a list of `[x, y]` pairs).
- `GET /waypoints/get_new/<id>` — `@require_write_lock`; returns `{}` if
  no new waypoints, else the list and clears the flag.
- `POST /waypoints/set/<id>` — body must be a list of `[x, y]` pairs where
  each coordinate is `int|float`. Validates each point is a list/tuple of
  length 2 with numeric coords; 400 otherwise. Sets
  `waypoints_new_flag = True`.

## Lock manager

`lock_manager.py` defines a fair `ReaderWriterLock` and a `LockManager` that
exposes `require_read_lock` / `require_write_lock` decorators. The
module-level `shared_lock_manager` singleton in `__init__.py` is what the
routes import. Don't instantiate per-route lock managers — the singleton is
what serializes access across all blueprints.

### Behavior asymmetry — pick the right decorator

- `@require_read_lock` is **blocking**. A reader waits as long as needed for
  any writer (or other readers) to finish. Readers never fail; they just wait.
  Use this for pure GETs that don't mutate state.
- `@require_write_lock` is **non-blocking**
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
`@require_write_lock`, **not** `@require_read_lock`, even though they're GETs.
This is because they mutate state — they clear the `*_new_flag` after reading.
If you copy a `get_new` route as a template for a pure read, switch the
decorator to `@require_read_lock`.

## Code style (Ruff)

Configured in `ruff.toml`. Highlights:
- `select = ["ALL"]` with a long curated `ignore` list.
- Line length 130, 4-space indent, double quotes, native line endings.
- numpy-style docstrings (`[lint.pydocstyle] convention = "numpy"`).
- `future-annotations = true` (analysis only; runtime is 3.12, native PEP 695).
- `skip-magic-trailing-comma = true` — don't rely on trailing commas to force
  one-per-line formatting.
- Notable ignores: `S101` (assert ok in tests), `T201` (print ok),
  `D100/D101/D103/D107` (no docstring required for modules/classes/methods/
  `__init__`), `PTH` (os.path is fine, don't suggest pathlib),
  `PLR0913` (many positional args ok), `TRY400` (logging.error ok, no need
  for .exception), `SLF001` (private member access ok).
- `unfixable = ["F401"]` — unused imports are flagged but NOT auto-removed
  (prevents accidental removal of re-exports in `__init__.py` files).

Run before committing:
```bash
ruff check .
ruff format --check .
```
