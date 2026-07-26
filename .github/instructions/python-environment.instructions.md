---
description: "Use when configuring Python environment, running ruff, building the package, or doing local development without Docker. Covers pyenv alias, pip install -e .[dev], ruff check/format, and the Flask vs Gunicorn run modes."
applyTo: "pyproject.toml, ruff.toml, .python-version"
---

# Python environment & tooling

## Python version

- Pinned via `.python-version` (pyenv alias `telemetry`). The actual Python
  version is **3.12** — the Dockerfile uses `python:3.12-slim`.
- Local dev: `pyenv local telemetry` or just `pyenv shell 3.12.x` if you
  don't have the alias set up.
- Don't downgrade below 3.12 — the codebase uses PEP 695 type aliases
  (`type X = ...`) which require 3.12+.

## Installing for local development

```bash
pip install -e ".[dev]"
```

This installs the package in editable mode plus the `dev` optional extras
(`build`, `pyproject_hooks`, `annotated-types`, `typing_extensions`,
`typing-inspection`). The `dev` extras are for type-checking and building;
they're not runtime dependencies.

Runtime deps (from `pyproject.toml`):
- Flask 3.x, Flask-Cors, Flask-SQLAlchemy
- gunicorn (production server)
- SQLAlchemy 2.x, Werkzeug, Jinja2, itsdangerous, click, blinker, packaging,
  MarkupSafe

## Running the server (local dev)

```bash
# Development (Flask dev server with auto-reload):
flask run --app autoboat_telemetry_server
# (No FLASK_APP needed — src/app.py defines `app = create_app()` at module
# scope and the package is installed editable.)

# Or with gunicorn (closer to prod):
gunicorn "autoboat_telemetry_server:create_app()"
# Prod runs: gunicorn -w 1 --bind 0.0.0.0:8000 "autoboat_telemetry_server:create_app()"
```

The app expects `src/instance/config.py` to exist. If you're running outside
the canonical `/home/ubuntu/telemetry_server/src/instance` layout (e.g. on a
macOS dev machine), `create_app()` falls back to `Path.home()` and looks for
`~/telemetry_server/src/instance/config.py`. Simplest local setup: the
shipped `src/instance/config.py` works as-is for dev (it just sets SQLite
bind paths relative to its own location, so the DBs get created next to it).

## Ruff (lint + format)

Configured in `ruff.toml`. Highlights:

- `select = ["ALL"]` — every Ruff rule, then a long `ignore` list carves out
  what we don't enforce.
- `line-length = 130`, `indent-width = 4`.
- `[format]`: `quote-style = "double"`, `indent-style = "space"`,
  `line-ending = "native"`, `docstring-code-format = true`,
  `docstring-code-line-length = "dynamic"`,
  `skip-magic-trailing-comma = true` (don't rely on trailing commas to force
  one-per-line formatting).
- `[lint.pydocstyle] convention = "numpy"` — numpy-style docstrings.
- `[lint.pylint]`: `max-positional-args = 8`, `max-returns = 10`,
  `max-locals = 30`.
- `[lint]`: `dummy-variable-rgx = "^(_+|(_+[a-zA-Z0-9_]*[a-zA-Z0-9]+?))$"`
  (allow `_`, `__`, `_unused`, etc.), `future-annotations = true` (analysis
  mode; runtime is 3.12 so native PEP 695 syntax works).
- `unfixable = ["F401"]` — unused imports are flagged but NOT auto-removed.
  This protects re-exports in `__init__.py` files (`__all__ = [...]`).

Notable ignores (see `ruff.toml` for the full list):
- `S101` — `assert` is fine (used in tests).
- `T201` — `print` is fine.
- `D100`, `D101`, `D103`, `D107` — no docstring required for modules,
  public classes, public functions, or `__init__` methods. (Public
  functions/classes/methods that DO have docstrings should follow numpy
  convention.)
- `PTH` — `os.path` is fine, don't suggest pathlib. (Codebase predates the
  pathlib preference; don't mass-rewrite without checking with maintainer.)
- `PLR0913` — many positional args ok.
- `TRY400` — `logging.error` ok, no need for `.exception`.
- `SLF001` — private member access ok.
- `INP001` — implicit namespace packages ok.
- `TC001/TC002/TC003` — don't move imports into TYPE_CHECKING blocks.
- `ERA001` — commented-out code ok.
- `FBT001/002/003` — boolean positional args ok.

Run before committing:
```bash
ruff check .           # lint
ruff format --check .  # format check (dry-run)
ruff format .          # format (writes)
ruff check --fix .     # auto-fix everything except unfixable rules
```

## Building the package

```bash
python -m build
```

Produces `dist/telemetry_server-0.0.0.tar.gz` (sdist) and
`dist/telemetry_server-0.0.0-py3-none-any.whl` (wheel). The version in
`pyproject.toml` is `0.0.0` — we don't publish to PyPI; deployment is via
Docker images. Don't bump the version in `pyproject.toml` expecting it to
mean anything for releases — release versioning is via git tags (`v1.2.3`)
which drive the Docker image tags (see the github-actions instructions).

## Dependabot

`.github/dependabot.yml` opens weekly PRs for:
- `pip` updates (root `pyproject.toml`).
- `github-actions` updates (workflow files).

Keep the schedule weekly — daily is noisy for a small project. Review
dependabot PRs carefully for SQLAlchemy/Flask major bumps (those have
historically had breaking changes).
