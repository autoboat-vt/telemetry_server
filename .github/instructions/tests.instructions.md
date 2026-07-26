---
description: "Use when editing tests under tests/, including conftest.py and any test_*.py file. Covers the macOS /home bootstrap, fixtures (tmp_instance_dir / app / client / db_session), route testing via FlaskClient, per-test INSTANCE_DIR isolation, the deferred-import pattern, ruff relaxations, and where to add new tests."
applyTo: "tests/**"
---

# Tests — `tests/`

## Layout & config

Tests live in `tests/` at the repo root (one directory per concern, mirroring
the source tree where practical):

- `conftest.py` — pytest config + shared fixtures + the macOS import bootstrap.
- `test_init.py` — app factory (`create_app`), CORS resolution, `INSTANCE_DIR`
  discovery, `shared_lock_manager` singleton.
- `test_models.py` — `TelemetryTable` + `HashTable` (hashing, validation,
  `to_dict`, the `after_insert` hook, `validate_user` immutability).
- `test_lock_manager.py` — `ReaderWriterLock` exclusion semantics + the
  `require_read_lock` / `require_write_lock` decorators (blocking vs 429).
- `test_types.py` — `DiagnosticMessageIntensity` IntEnum mapping (the
  cross-repo wire contract) + type aliases.
- `test_routes.py` — end-to-end route tests through the Flask test client
  (status codes, response shapes, the error-code ladder, lock behavior).

Pytest is configured in `pyproject.toml` under `[tool.pytest.ini_options]`:
`testpaths = ["tests"]`, `pythonpath = ["src"]`, `minversion = "8.0"`. Run
with plain `pytest` after `pip install -e ".[dev]"`.

## The conftest bootstrap — DO NOT break import ordering

`tests/conftest.py` defines `_bootstrap_package_import()` and calls it at
**module scope** (collection time, before any test runs). The package's
`__init__.py` discovers `INSTANCE_DIR` at import time by scanning `/home` for
exactly one user directory — which fails with `RuntimeError` on macOS (and
any non-Linux dev box) because `/home` is empty. The bootstrap
monkeypatches `pathlib.Path.iterdir` so `Path("/home").iterdir()` returns the
repo's parent directory (`FAKE_HOME = REPO_ROOT.parent`), which satisfies the
discovery logic and resolves `INSTANCE_DIR` to the checked-in
`src/instance/config.py`.

Hard rules:

1. **`_bootstrap_package_import()` must run before the package is imported.**
   It guards on `if "autoboat_telemetry_server" in sys.modules: return` so it
   is idempotent — but if anything imports the package first (e.g. a
   stray top-level import in a test module that runs before conftest), the
   bootstrap is skipped and the import already failed. This is why test
   modules defer most `autoboat_telemetry_server` imports into test method
   bodies (see "Deferred imports" below).
2. **Do not move `_bootstrap_package_import()` into a fixture.** Fixtures run
   per-test; the package needs to be importable at collection time so test
   modules' deferred imports resolve. The module-level call is load-bearing.
3. **`FAKE_HOME = REPO_ROOT.parent`** — the repo's parent must contain a
   `telemetry_server/src/instance/config.py` for the discovery to resolve.
   This is why tests break if you clone the repo into a directory NOT named
   `telemetry_server`. Don't rename the repo directory.

## Fixtures — when to use which

`conftest.py` provides four fixtures. Pick the smallest one that does the job:

| Fixture | Provides | Use when |
| --- | --- | --- |
| `tmp_instance_dir` | A temp dir with a copy of `src/instance/config.py` (no DB, no app). | You need to write a custom `config.py` and build the app yourself (e.g. `TestCorsPrecedence` writes a `CORS_ORIGINS` override into config.py, then calls `ats.create_app()` directly so it can assert on response headers). |
| `app` | A `Flask` app with `INSTANCE_DIR` monkeypatched to `tmp_instance_dir`, `db.create_all()` run, `TESTING=True`, app context active. | You need the DB or app config but will call routes via `app.test_client()` yourself, or you need `app_context` for direct model access. |
| `client` | `app.test_client()` (built on `app`). | Route tests — the common case. Use for all `test_routes.py`-style end-to-end tests. |
| `db_session` | `db.session` bound to the test app's context. | Direct model-layer tests that need a DB session but aren't going through routes. |

`app` does the `INSTANCE_DIR` monkeypatch **and restores it in a `finally`
block** after the test yields. If you bypass `app` and monkeypatch
`INSTANCE_DIR` yourself (the `tmp_instance_dir`-only path), you MUST restore
it in a `try/finally` — leaving `INSTANCE_DIR` pointing at a deleted temp dir
poisons every subsequent test. Copy this pattern from
`test_init.py::TestCorsPrecedence`:

```python
def test_something(self, tmp_instance_dir: Path) -> None:
    import autoboat_telemetry_server as ats

    (tmp_instance_dir / "config.py").write_text("...")
    original = ats.INSTANCE_DIR
    ats.INSTANCE_DIR = tmp_instance_dir
    try:
        app = ats.create_app()
        # ... assertions ...
    finally:
        ats.INSTANCE_DIR = original
```

Per-test DB isolation is automatic: `app` creates the SQLite DBs inside
`tmp_path` and `db.drop_all()`s them on teardown. Don't share state between
tests through the DB — each test gets a fresh one.

## Deferred imports inside test methods

Most `test_*.py` modules import `autoboat_telemetry_server` symbols **inside
the test method body**, not at module top:

```python
def test_single_origin(self) -> None:
    from autoboat_telemetry_server import _parse_cors_origins

    assert _parse_cors_origins("https://example.com") == ["https://example.com"]
```

This is deliberate and is why `ruff.toml` ignores `PLC0415` (import outside
top level) for `tests/**`. The reason: conftest's bootstrap must run before
the package is imported, and deferring imports into method bodies keeps the
package import lazy (per-test, after conftest has patched `Path.iterdir`).
Some modules (`test_models.py`, `test_lock_manager.py`, `test_types.py`)
do import at module top because they don't trigger the `/home` scan on import
— but `test_init.py` and any test touching `create_app()` should defer.

**Do not add a local import that shadows a module-level import.** This
confuses ruff's scope analysis: a `from pathlib import Path` inside one
method makes ruff report `F821 Undefined name 'Path'` on the `Path`
annotations in *other* method signatures in the same class. If a type is
already imported at module top, use the module-level import — don't re-import
locally. (`F401` unused-import is `unfixable` in `ruff.toml`, so stale local
imports won't be auto-removed and will fail CI.)

## Route tests — use the Flask test client

`test_routes.py` is the canonical pattern for route testing. Rules:

1. **Go through `client` (the Flask test client), not direct route method
   calls.** This exercises the full HTTP stack: URL routing, the lock
   decorators, JSON request/response encoding, error handlers. Direct calls
   skip the decorators and the `jsonify` wrapper, hiding real bugs.
2. **Use the helper functions at the top of `test_routes.py`** (`_create_instance`,
   `_make_config`) rather than reinventing the setup. If you need a new
   reusable setup step, add a helper next to the existing ones.
3. **Assert on both status code and response body.** The error-code ladder
   (AGENTS.md §3.12) is a contract: 404 for missing instance, 400 for
   malformed/invalid input, 429 for write-lock contention, 500 for the
   catch-all. Pin both the code and a substring of the body so error message
   drift is caught:
   ```python
   response = client.delete("/instance_manager/delete/9999")
   assert response.status_code == 404
   assert b"Instance not found" in response.data
   ```
4. **Group tests into one class per route domain or per behavior cluster.**
   `TestInstanceManagerCreate`, `TestInstanceManagerSetUser`,
   `TestInstanceManagerSetName`, etc. — not one giant `TestRoutes` class.
   This keeps the test output readable and lets you target a group with
   `pytest tests/test_routes.py::TestInstanceManagerSetUser`.
5. **JSON bodies:** pass `json=...` to `client.post` (Flask sets the content
   type and encodes). Read responses with `response.get_json()` for JSON, or
   `response.get_data(as_text=True)` / `response.data` for plain strings.
6. **The double-JSON gotcha (AGENTS.md §5):** `autopilot_parameters` routes
   that do `json.loads(request.json)` expect the body to be a JSON-encoded
   *string*. In tests, send `json=json.dumps({...})` (a string), not
   `json={...}` (a dict). `test_routes.py` has examples — copy them.

## Asserting on observable behavior, not internals

Prefer assertions on HTTP response shape / headers / status over
`app.config` internals. Example: `TestCorsPrecedence` checks the
`Access-Control-Allow-Origin` response header rather than
`app.config["CORS_ORIGINS"]`, because `create_app()` passes the resolved list
to flask-cors without writing it back to config — asserting on the config
key would pass while the actual CORS behavior was broken. Tests that pin
internal state (like `test_models.py::TestComputeHash` asserting on the
hash formula) are fine when the internal state IS the contract; otherwise
test through the public surface.

## Ruff relaxation for tests

`ruff.toml` has a per-file-ignores block:

```toml
[lint.per-file-ignores]
"tests/**" = ["D102", "ANN001", "ANN201", "PLC0415", "PT018"]
```

- `D102` — test methods don't need docstrings (but a docstring explaining a
  non-obvious regression guard, like in `TestCorsPrecedence`, is welcome).
- `ANN001` / `ANN201` — fixtures and test helpers don't need full annotations
  (though the existing code annotates them; match the surrounding style).
- `PLC0415` — deferred imports inside test methods are allowed (see above).
- `PT018` — multiple assertions per test are fine (don't split
  `assert a; assert b` into two tests just to satisfy the linter).

Everything else from the global `select = ["ALL"]` still applies: `S101`
(assert) is globally ignored, `T201` (print) is globally ignored, but unused
imports (`F401`), undefined names (`F821`), etc. will fail CI. Run
`ruff check tests/` and `ruff format tests/` before committing.

## Running tests

```bash
pytest                                   # full suite
pytest tests/test_routes.py              # one file
pytest tests/test_routes.py::TestInstanceManagerSetUser   # one class
pytest tests/test_routes.py::TestInstanceManagerSetUser::test_set_user_twice_returns_400  # one test
pytest -k "cors"                         # by keyword expression
pytest -x                                # stop on first failure
pytest --tb=short                        # shorter tracebacks
pytest -q                                # quiet (dots only)
```

CI (`.github/workflows/build.yml`, `test` job) runs `ruff check .`,
`ruff format --check .`, then `pytest`. The `test` job gates the Docker
`build` job via `needs: test` — a failing test fails fast before any image
build minutes are spent. Do not remove that gate; if you must force a build
past a failing test in an emergency, run the `build` job alone via
`workflow_dispatch` instead of editing the gate.

## Adding new tests

1. **Put them in the right file.** Match the module under test:
   - `create_app()`, CORS, `INSTANCE_DIR`, `shared_lock_manager` → `test_init.py`
   - `TelemetryTable` / `HashTable` models → `test_models.py`
   - `ReaderWriterLock` / `LockManager` → `test_lock_manager.py`
   - `types.py` (enums, type aliases) → `test_types.py`
   - Any route handler → `test_routes.py` (use the Flask test client)
2. **Add a module docstring** describing what the file covers (every existing
   test file has one — match the style).
3. **Group related tests into a class** with a short docstring explaining the
   behavior cluster, especially for regression guards (the docstring is where
   you explain *why* this test exists, e.g. "config.py once defined
   DEFAULT_CORS_ORIGINS instead of CORS_ORIGINS, so ...").
4. **For regression tests, name them for the bug they pin**, not the feature
   they test: `test_includes_www_website_mirror`, not `test_cors_origins_1`.
   The name should make the failure self-explanatory in CI output.
5. **Run `ruff check tests/` and `ruff format tests/`** on the new file, then
   `pytest` the new file before committing. The full suite must stay green.
