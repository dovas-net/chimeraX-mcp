from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import tomllib


try:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject_path.exists():
        with pyproject_path.open("rb") as fh:
            __version__ = tomllib.load(fh)["project"]["version"]
    else:
        __version__ = version("chimerax-mcp")
except (KeyError, PackageNotFoundError, OSError, tomllib.TOMLDecodeError):
    __version__ = "0.4.0"
