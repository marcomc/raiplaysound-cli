from __future__ import annotations

import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def load_launcher_support() -> types.ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "launcher" / "launcher_support.py"
    spec = spec_from_file_location("launcher_support_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load launcher support module from {module_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_sys_path_entries_prefers_source_then_site_packages(tmp_path: Path) -> None:
    support = load_launcher_support()
    root = tmp_path

    (root / "src" / "raiplaysound_cli").mkdir(parents=True)
    (root / ".venv" / "lib" / "python3.14" / "site-packages").mkdir(parents=True)
    (root / "venv" / "lib" / "python3.13" / "site-packages").mkdir(parents=True)

    entries = support.runtime_sys_path_entries(root)

    assert entries == [
        root / "src",
        root / ".venv" / "lib" / "python3.14" / "site-packages",
        root / "venv" / "lib" / "python3.13" / "site-packages",
    ]


def test_main_bootstraps_paths_and_invokes_cli(monkeypatch, tmp_path: Path) -> None:
    support = load_launcher_support()
    entries = [
        tmp_path / "src",
        tmp_path / "venv" / "lib" / "python3.14" / "site-packages",
    ]
    original_sys_path = sys.path.copy()
    calls: list[str] = []

    def fake_import_module(name: str) -> types.SimpleNamespace:
        def fake_main(argv: list[str] | None = None) -> int:
            calls.append(name)
            return 0

        return types.SimpleNamespace(main=fake_main)

    monkeypatch.setattr(support, "runtime_sys_path_entries", lambda _root: entries)
    monkeypatch.setattr(support.importlib, "import_module", fake_import_module)

    try:
        result = support.main(["download", "--version"])
        assert result == 0
        assert calls == ["raiplaysound_cli.cli"]
        assert sys.path[0] == str(entries[0])
        assert sys.path[1] == str(entries[1])
    finally:
        sys.path[:] = original_sys_path


def test_main_reports_missing_runtime_tree(monkeypatch, capsys) -> None:
    support = load_launcher_support()
    monkeypatch.setattr(support, "runtime_sys_path_entries", lambda _root: [])

    result = support.main([])
    captured = capsys.readouterr()

    assert result == 1
    assert "could not find an installed package tree" in captured.err
