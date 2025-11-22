import tomlkit
import os

version = os.environ.get("NEW_VERSION")

with open("pyproject.toml", "rb") as f:
    data = tomlkit.load(f)

data["project"]["version"] = version

with open("pyproject.toml", "wb") as f:
    tomlkit.dump(data, f)
