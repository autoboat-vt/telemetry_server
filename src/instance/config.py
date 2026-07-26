from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SQLALCHEMY_BINDS = {
    None: f"sqlite:///{(BASE_DIR / 'instances.db').as_posix()}",
    "hashes": f"sqlite:///{(BASE_DIR / 'hashes.db').as_posix()}",
}
SQLALCHEMY_TRACK_MODIFICATIONS = False

# CORS origins allowlist. Read by create_app() as app.config["CORS_ORIGINS"]
# (precedence: CORS_ORIGINS env var > this list > DEFAULT_CORS_ORIGINS in
# autoboat_telemetry_server/__init__.py). This file is persisted in the
# named instance volume, so editing it on a deployed host overrides the
# baked-in default without rebuilding the image. Keep this list in sync with
# DEFAULT_CORS_ORIGINS in __init__.py unless you deliberately want to diverge.
CORS_ORIGINS: list[str] = [
    "https://autoboat.aoe.vt.edu",
    "https://www.autoboat.aoe.vt.edu",
    "https://vt-autoboat-telemetry.uk",
    "https://www.vt-autoboat-telemetry.uk",
    "https://test.vt-autoboat-telemetry.uk",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
