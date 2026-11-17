"""Where things are, for every tool (backed by engine/crates/paths).

    paths.host()                 "windows" | "wsl" | "mac" | "linux"
    paths.to_host(r"C:\\x")       Path("/mnt/c/x") in WSL
    paths.to_windows(p)          r"C:\\x" / r"\\\\wsl.localhost\\<distro>\\..." (None off Windows/WSL)
    paths.dorico_install(5)      Install(dir, version) of Dorico's program folder (factory data)
    paths.dorico_appdata(5)      %APPDATA%\\Steinberg\\Dorico 5 (expression maps, prefs)
    paths.documents(), paths.dorico_projects(), paths.user_home()
    paths.corpus()["projects"]   test corpora from engine/tests/corpus.toml

Overrides: DORICO_INSTALL, DORICO_USER_HOME, DORICO_APPDATA, DORICO_DOCUMENTS, DORICO_PROJECTS,
DORICO_CORPUS_FILE and DORICO_<NAME> for each corpus entry.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

from . import _native

__all__ = ["Install", "corpus", "documents", "dorico_appdata", "dorico_install", "dorico_installs",
           "dorico_projects", "host", "to_host", "to_windows", "user_home", "windows_to_wsl", "wsl_to_windows"]


class Install(NamedTuple):
    dir: Path
    version: int | None


def host() -> str:
    return _native.host()[0]


def wsl_distro() -> str:
    return _native.host()[1]


def to_host(path: str | os.PathLike) -> Path:
    return Path(_native.to_host(str(path)))


def to_windows(path: str | os.PathLike) -> str | None:
    return _native.to_windows(str(path))


windows_to_wsl = _native.windows_to_wsl
wsl_to_windows = _native.wsl_to_windows


def dorico_installs() -> list[Install]:
    return [Install(Path(d), v) for d, v in _native.dorico_installs()]


def dorico_install(version: int | None = None) -> Install | None:
    r = _native.dorico_install(version)
    return Install(Path(r[0]), r[1]) if r else None


def _p(s: str | None) -> Path | None:
    return Path(s) if s else None


def user_home() -> Path | None:
    return _p(_native.user_home())


def dorico_appdata(version: int = 5) -> Path | None:
    return _p(_native.dorico_appdata(version))


def documents() -> Path | None:
    return _p(_native.documents())


def dorico_projects() -> Path | None:
    return _p(_native.dorico_projects())


def corpus() -> dict[str, Path]:
    """Corpus name -> path (may not exist on this machine; check before use)."""
    return {k: Path(v) for k, v in _native.corpus().items()}
