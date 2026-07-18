from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SQLALCHEMY_BINDS = {
    None: f"sqlite:///{(BASE_DIR / 'instances.db').as_posix()}",
    "hashes": f"sqlite:///{(BASE_DIR / 'hashes.db').as_posix()}",
}
SQLALCHEMY_TRACK_MODIFICATIONS = False

DEFAULT_CORS_ORIGINS: list[str] = [
    "https://autoboat.aoe.vt.edu",
    "https://www.autoboat.aoe.vt.edu",
    "https://vt-autoboat-telemetry.uk",
    "https://www.vt-autoboat-telemetry.uk",
    "https://test.vt-autoboat-telemetry.uk",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
