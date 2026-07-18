from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SQLALCHEMY_BINDS = {
    None: f"sqlite:///{(BASE_DIR / 'instances.db').as_posix()}",
    "hashes": f"sqlite:///{(BASE_DIR / 'hashes.db').as_posix()}",
}
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Origins allowed to make cross-origin requests to this API.
#
# Used by create_app() when the CORS_ORIGINS env var is NOT set. To override
# on an existing deployment without rebuilding the image, set the
# CORS_ORIGINS env var (comma-separated) in docker-compose.yml instead of
# editing this file — src/instance/config.py is persisted in a named volume
# and is not overwritten on image updates.
CORS_ORIGINS = [
    "https://autoboat.aoe.vt.edu",
    "https://vt-autoboat-telemetry.uk",
    "https://www.vt-autoboat-telemetry.uk",
    "https://test.vt-autoboat-telemetry.uk",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
