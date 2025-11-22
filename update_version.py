import tomli_w, tomli
import os

version = os.environ.get("NEW_VERSION")

with open("pyproject.toml", "rb") as f:
    data = tomli.load(f)

data["project"]["version"] = version

with open("pyproject.toml", "wb") as f:
    tomli_w.dump(data, f)
