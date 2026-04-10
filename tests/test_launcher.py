from __future__ import annotations

import subprocess
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


def test_uninstall_dev_restores_legacy_standalone_install(tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    venv_dir = tmp_path / ".venv"
    install_path = tmp_path / "bin" / "raiplaysound-cli"
    launcher_path = install_dir / "bin" / "raiplaysound-cli"
    legacy_path = install_dir / "venv" / "bin" / "raiplaysound-cli"
    dev_launcher_path = venv_dir / "bin" / "raiplaysound-cli"
    repo_root = Path(__file__).resolve().parents[1]

    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    legacy_path.chmod(0o755)
    install_path.parent.mkdir(parents=True)
    dev_launcher_path.parent.mkdir(parents=True)
    dev_launcher_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    dev_launcher_path.chmod(0o755)
    install_path.symlink_to(dev_launcher_path)

    result = subprocess.run(
        [
            "make",
            f"CURDIR={repo_root}",
            f"INSTALL_DIR={install_dir}",
            f"VENV={venv_dir}",
            f"BINDIR={install_path.parent}",
            f"INSTALL_PATH={install_path}",
            f"INSTALL_LAUNCHER_PATH={launcher_path}",
            f"INSTALL_VENV={install_dir / 'venv'}",
            "uninstall-dev",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    assert result.returncode == 0
    assert install_path.is_symlink()
    assert install_path.resolve() == legacy_path
    assert "Restored legacy standalone install" in result.stdout


def test_install_stamps_launcher_with_install_venv_python(tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    bindir = tmp_path / "bin"
    repo_root = Path(__file__).resolve().parents[1]
    install_launcher_path = install_dir / "bin" / "raiplaysound-cli"
    install_launcher_support = install_dir / "bin" / "launcher_support.py"
    install_venv = install_dir / "venv"
    install_path = bindir / "raiplaysound-cli"

    result = subprocess.run(
        [
            "make",
            f"CURDIR={repo_root}",
            f"INSTALL_DIR={install_dir}",
            f"INSTALL_VENV={install_venv}",
            f"INSTALL_LAUNCHER_PATH={install_launcher_path}",
            f"INSTALL_LAUNCHER_DIR={install_launcher_path.parent}",
            f"BINDIR={bindir}",
            f"INSTALL_PATH={install_path}",
            "install",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    assert result.returncode == 0
    assert install_launcher_path.read_text(encoding="utf-8").startswith(
        f"#!{install_venv / 'bin' / 'python'}"
    )
    assert install_launcher_support.exists()
