from __future__ import annotations

import http.client
import sys
import urllib.error
from email.message import Message

import pytest

from raiplaysound_cli import runtime
from raiplaysound_cli.errors import HTTPRequestError


class FakeResponse:
    def __init__(self, payload: bytes = b"ok") -> None:
        self.payload = payload
        self.headers = Message()
        self.headers["Content-Type"] = "text/plain"

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_http_get_retries_transient_disconnect(monkeypatch) -> None:
    calls = 0

    def fake_request(_url: str, *, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        assert timeout == 5.0
        if calls == 1:
            raise http.client.RemoteDisconnected("closed")
        return FakeResponse(b"ready")

    monkeypatch.setattr(runtime, "_request", fake_request)
    monkeypatch.setattr(runtime.time, "sleep", lambda _seconds: None)
    runtime.configure_http(timeout_seconds=5.0, retries=1, backoff_seconds=0.0)

    try:
        assert runtime.http_get("https://example.test") == "ready"
        assert calls == 2
    finally:
        runtime.configure_http(timeout_seconds=30.0, retries=2, backoff_seconds=2.0)


def test_http_get_does_not_retry_404(monkeypatch) -> None:
    calls = 0

    def fake_request(_url: str, *, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            "https://example.test/missing",
            404,
            "Not Found",
            hdrs=Message(),
            fp=None,
        )

    monkeypatch.setattr(runtime, "_request", fake_request)
    runtime.configure_http(retries=3, backoff_seconds=0.0)

    try:
        with pytest.raises(HTTPRequestError) as excinfo:
            runtime.http_get("https://example.test/missing")
        assert excinfo.value.code == 404
        assert calls == 1
    finally:
        runtime.configure_http(timeout_seconds=30.0, retries=2, backoff_seconds=2.0)


def test_run_streamed_process_times_out_and_marks_result() -> None:
    lines: list[str] = []

    result = runtime.run_streamed_process(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(30)",
        ],
        on_line=lines.append,
        timeout_seconds=1,
    )

    assert result.returncode == 124
    assert result.timed_out is True
    assert lines == ["start"]


def test_run_streamed_process_cleans_up_child_on_keyboard_interrupt(monkeypatch) -> None:
    kill_calls: list[tuple[int, int]] = []
    popen_kwargs: list[object] = []

    class FakeProcess:
        pid = 4242
        stdout = iter(())

        def __init__(self) -> None:
            self.wait_calls = 0

        def wait(self, timeout: int | None = None) -> int:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise KeyboardInterrupt
            assert timeout == 10
            return -runtime.signal.SIGTERM

    fake_process = FakeProcess()

    def fake_popen(_command: list[str], **kwargs: object) -> FakeProcess:
        popen_kwargs.append(kwargs["start_new_session"])
        return fake_process

    monkeypatch.setattr(runtime.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        runtime.os,
        "killpg",
        lambda pid, sig: kill_calls.append((pid, sig)),
    )

    with pytest.raises(KeyboardInterrupt):
        runtime.run_streamed_process(
            [sys.executable, "-c", "print('unused')"],
            on_line=lambda _line: None,
        )

    assert popen_kwargs == [True]
    assert kill_calls == [(4242, runtime.signal.SIGTERM)]
    assert fake_process.wait_calls == 2


def test_run_streamed_process_cleans_up_child_on_sigterm(monkeypatch) -> None:
    kill_calls: list[tuple[int, int]] = []
    signal_calls: list[tuple[int, object]] = []
    installed_handler = None
    previous_handler = object()

    class FakeProcess:
        pid = 4343
        stdout = iter(())

        def __init__(self) -> None:
            self.wait_calls = 0

        def wait(self, timeout: int | None = None) -> int:
            self.wait_calls += 1
            if self.wait_calls == 1:
                assert installed_handler is not None
                installed_handler(runtime.signal.SIGTERM, None)
            assert timeout == 10
            return -runtime.signal.SIGTERM

    fake_process = FakeProcess()

    def fake_signal(signum: int, handler: object) -> object:
        nonlocal installed_handler
        signal_calls.append((signum, handler))
        if handler is not previous_handler:
            installed_handler = handler
        return previous_handler

    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *_args, **_kwargs: fake_process)
    monkeypatch.setattr(runtime.signal, "getsignal", lambda _signum: previous_handler)
    monkeypatch.setattr(runtime.signal, "signal", fake_signal)
    monkeypatch.setattr(
        runtime.os,
        "killpg",
        lambda pid, sig: kill_calls.append((pid, sig)),
    )

    with pytest.raises(KeyboardInterrupt):
        runtime.run_streamed_process(
            [sys.executable, "-c", "print('unused')"],
            on_line=lambda _line: None,
        )

    assert kill_calls == [(4343, runtime.signal.SIGTERM)]
    assert signal_calls[0][0] == runtime.signal.SIGTERM
    assert signal_calls[-1] == (runtime.signal.SIGTERM, previous_handler)
    assert fake_process.wait_calls == 2
