from __future__ import annotations

import contextlib
import dataclasses
import http.client
import os
import random
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import Thread, current_thread, main_thread
from typing import Any, Callable, Iterator

from .errors import CLIError, HTTPRequestError

_HTTP_TIMEOUT_SECONDS = 30.0
_HTTP_RETRIES = 2
_HTTP_BACKOFF_SECONDS = 2.0


@dataclasses.dataclass(frozen=True, slots=True)
class ProcessRunResult:
    returncode: int
    timed_out: bool = False


@contextlib.contextmanager
def _raise_keyboard_interrupt_on_sigterm() -> Iterator[None]:
    if current_thread() is not main_thread():
        yield
        return
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def handle_sigterm(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handle_sigterm)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


def configure_http(
    *,
    timeout_seconds: float | None = None,
    retries: int | None = None,
    backoff_seconds: float | None = None,
) -> None:
    global _HTTP_TIMEOUT_SECONDS, _HTTP_RETRIES, _HTTP_BACKOFF_SECONDS
    if timeout_seconds is not None:
        _HTTP_TIMEOUT_SECONDS = max(timeout_seconds, 1.0)
    if retries is not None:
        _HTTP_RETRIES = max(retries, 0)
    if backoff_seconds is not None:
        _HTTP_BACKOFF_SECONDS = max(backoff_seconds, 0.0)


def _request(url: str, *, timeout: float) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "raiplaysound-cli/2.0",
            "Accept": "*/*",
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _retry_delay(attempt: int) -> float:
    base = _HTTP_BACKOFF_SECONDS * (2 ** max(attempt - 1, 0))
    if base <= 0:
        return 0.0
    return base + random.uniform(0, min(base, 1.0))


def _transient_http_error(exc: urllib.error.HTTPError) -> bool:
    return exc.code == 429 or 500 <= exc.code <= 599


def http_get(url: str, *, timeout: float | None = None) -> str:
    request_timeout = _HTTP_TIMEOUT_SECONDS if timeout is None else timeout
    last_error: BaseException | None = None
    attempts = _HTTP_RETRIES + 1
    for attempt in range(1, attempts + 1):
        try:
            with _request(url, timeout=request_timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if not _transient_http_error(exc) or attempt == attempts:
                raise HTTPRequestError(
                    url,
                    f"RaiPlaySound returned HTTP {exc.code} for {url}.",
                    code=exc.code,
                ) from exc
            last_error = exc
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.RemoteDisconnected,
        ) as exc:
            if attempt == attempts:
                reason = getattr(exc, "reason", exc)
                raise HTTPRequestError(url, f"network request failed for {url}: {reason}") from exc
            last_error = exc
        if attempt < attempts:
            time.sleep(_retry_delay(attempt))
    reason = getattr(last_error, "reason", last_error)
    raise HTTPRequestError(url, f"network request failed for {url}: {reason}")


def http_get_bytes(url: str, *, timeout: float | None = None) -> tuple[bytes, str]:
    request_timeout = _HTTP_TIMEOUT_SECONDS if timeout is None else timeout
    last_error: BaseException | None = None
    attempts = _HTTP_RETRIES + 1
    for attempt in range(1, attempts + 1):
        try:
            with _request(url, timeout=request_timeout) as response:
                content_type = response.headers.get_content_type()
                return response.read(), content_type
        except urllib.error.HTTPError as exc:
            if not _transient_http_error(exc) or attempt == attempts:
                raise HTTPRequestError(
                    url,
                    f"RaiPlaySound returned HTTP {exc.code} for {url}.",
                    code=exc.code,
                ) from exc
            last_error = exc
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.RemoteDisconnected,
        ) as exc:
            if attempt == attempts:
                reason = getattr(exc, "reason", exc)
                raise HTTPRequestError(url, f"network request failed for {url}: {reason}") from exc
            last_error = exc
        if attempt < attempts:
            time.sleep(_retry_delay(attempt))
    reason = getattr(last_error, "reason", last_error)
    raise HTTPRequestError(url, f"network request failed for {url}: {reason}")


def run_streamed_process(
    command: list[str],
    *,
    on_line: Callable[[str], None] | None = None,
    timeout_seconds: int = 0,
) -> ProcessRunResult:
    def stop_process(force: bool) -> None:
        if os.name == "nt":
            if force:
                process.kill()
            else:
                process.terminate()
            return
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)

    def stop_and_wait() -> None:
        with contextlib.suppress(OSError):
            stop_process(force=False)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                stop_process(force=True)
            process.wait()
        if reader is not None:
            reader.join(timeout=2)

    process = subprocess.Popen(
        command,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE if on_line is not None else None,
        stderr=subprocess.STDOUT if on_line is not None else None,
        start_new_session=os.name != "nt",
    )
    reader: Thread | None = None

    def _read_output() -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            assert on_line is not None
            on_line(raw_line.rstrip())

    if on_line is not None:
        assert process.stdout is not None
        reader = Thread(target=_read_output, daemon=True)
        reader.start()
    try:
        with _raise_keyboard_interrupt_on_sigterm():
            returncode = process.wait(timeout=timeout_seconds or None)
    except subprocess.TimeoutExpired:
        stop_and_wait()
        return ProcessRunResult(returncode=124, timed_out=True)
    except BaseException:
        stop_and_wait()
        raise
    if reader is not None:
        reader.join()
    return ProcessRunResult(returncode=returncode)


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
