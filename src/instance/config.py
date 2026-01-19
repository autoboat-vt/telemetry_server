from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SQLALCHEMY_DATABASE_URI = f"sqlite:///{(BASE_DIR / 'app.db').as_posix()}"
SQLALCHEMY_TRACK_MODIFICATIONS = False
