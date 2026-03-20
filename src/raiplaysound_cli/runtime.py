from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .errors import CLIError, HTTPRequestError


def http_get(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "raiplaysound-cli/2.0",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise HTTPRequestError(
            url,
            f"RaiPlaySound returned HTTP {exc.code} for {url}.",
            code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise HTTPRequestError(url, f"network request failed for {url}: {reason}") from exc


def run_yt_dlp(
    args: list[str],
    *,
    capture_output: bool = True,
    allow_partial_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = ["yt-dlp", *args]
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise CLIError("yt-dlp is required but was not found in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        if allow_partial_failure:
            return subprocess.CompletedProcess(
                args=exc.cmd,
                returncode=exc.returncode,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or f"yt-dlp failed with exit code {exc.returncode}"
        raise CLIError(detail) from exc


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(lock_dir: Path, slug: str) -> None:
    pid_file = lock_dir / "pid"
    try:
        lock_dir.mkdir()
    except FileExistsError:
        pid = None
        if pid_file.exists():
            raw_pid = pid_file.read_text(encoding="utf-8").strip()
            if raw_pid.isdigit():
                pid = int(raw_pid)
        if pid is not None and process_is_running(pid):
            raise CLIError(
                "another download process is already running for "
                f"program slug '{slug}' (PID {pid})."
            ) from None
        shutil.rmtree(lock_dir, ignore_errors=True)
        lock_dir.mkdir()
    pid_file.write_text(str(os.getpid()), encoding="utf-8")


def release_lock(lock_dir: Path) -> None:
    with contextlib.suppress(OSError):
        shutil.rmtree(lock_dir, ignore_errors=True)
