from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SQLALCHEMY_BINDS = {
    None: f"sqlite:///{(BASE_DIR / 'instances.db').as_posix()}",
    "hashes": f"sqlite:///{(BASE_DIR / 'hashes.db').as_posix()}",
}
SQLALCHEMY_TRACK_MODIFICATIONS = False
