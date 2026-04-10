from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence

MINIMUM_PYTHON = (3, 10)


def _site_packages_dirs(root: Path, env_dir_name: str) -> list[Path]:
    lib_dir = root / env_dir_name / "lib"
    if not lib_dir.is_dir():
        return []
    return [path for path in sorted(lib_dir.glob("python*/site-packages")) if path.is_dir()]


def runtime_sys_path_entries(root: Path) -> list[Path]:
    entries: list[Path] = []
    src_dir = root / "src"
    if src_dir.is_dir():
        entries.append(src_dir)
    entries.extend(_site_packages_dirs(root, ".venv"))
    entries.extend(_site_packages_dirs(root, "venv"))
    return entries


def discover_runtime_root(script_path: Path) -> Path:
    candidates = [script_path.parent, *script_path.parents]
    for candidate in candidates:
        if (candidate / "src" / "raiplaysound_cli").is_dir():
            return candidate
    return script_path.parent.parent


def _prepend_sys_path(entries: Sequence[Path]) -> None:
    for entry in reversed(entries):
        entry_str = str(entry)
        if entry_str not in sys.path:
            sys.path.insert(0, entry_str)


def _load_cli_module() -> ModuleType:
    return importlib.import_module("raiplaysound_cli.cli")


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < MINIMUM_PYTHON:
        sys.stderr.write("raiplaysound-cli requires Python 3.10 or newer.\n")
        return 1

    script_path = Path(__file__).resolve()
    root = discover_runtime_root(script_path)
    entries = runtime_sys_path_entries(root)
    if not entries:
        sys.stderr.write(
            "raiplaysound-cli could not find an installed package tree under "
            f"{root}. Re-run `make install` or `make install-dev`.\n"
        )
        return 1

    _prepend_sys_path(entries)
    try:
        cli_module = _load_cli_module()
    except ModuleNotFoundError as exc:
        if exc.name in {"raiplaysound_cli", "rich"}:
            sys.stderr.write(
                "raiplaysound-cli is missing from the local install tree. "
                "Re-run `make install` or `make install-dev`.\n"
            )
            return 1
        raise

    return int(cli_module.main(argv))
