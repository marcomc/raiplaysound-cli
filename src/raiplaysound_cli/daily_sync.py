from __future__ import annotations

import argparse
import dataclasses
import json
import multiprocessing
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from email.utils import formatdate
from pathlib import Path
from typing import Sequence

from .config import Settings, expand_config_path, parse_env_file
from .episodes import detect_slug
from .errors import CLIError
from .runtime import run_streamed_process

AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}
DEFAULT_CONFIG_FILE = Path.home() / ".raiplaysound-cli.conf"
DEFAULT_LOG_FILE = Path.home() / "Library" / "Logs" / "raiplaysound-cli-daily-sync.log"


@dataclasses.dataclass(frozen=True, slots=True)
class DownloadRow:
    program: str
    episode_date: str
    title: str
    file_name: str


def _expand_optional_path(value: str, default: Path) -> Path:
    if not value.strip():
        return default
    return Path(expand_config_path(value))


def _favorite_slugs(favorites: Sequence[str]) -> list[str]:
    slugs: list[str] = []
    for favorite in favorites:
        try:
            slug, _program_url = detect_slug(favorite)
        except CLIError:
            continue
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def _audio_files_for_slugs(target_base: Path, slugs: Sequence[str]) -> set[Path]:
    files: set[Path] = set()
    for slug in slugs:
        show_dir = target_base / slug
        if not show_dir.is_dir():
            continue
        for path in show_dir.iterdir():
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                files.add(path)
    return files


def _collect_audio_files_worker(target_base: str, slugs: list[str], output_file: str) -> None:
    try:
        paths = _audio_files_for_slugs(Path(target_base), slugs)
    except Exception as exc:
        payload: dict[str, object] = {"status": "error", "message": str(exc)}
        Path(output_file).write_text(json.dumps(payload), encoding="utf-8")
        return
    payload = {"status": "ok", "paths": [str(path) for path in paths]}
    Path(output_file).write_text(json.dumps(payload), encoding="utf-8")


def _read_snapshot_payload(output_file: Path) -> tuple[set[Path], str]:
    try:
        payload = json.loads(output_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set(), "audio file snapshot produced no result"
    except json.JSONDecodeError as exc:
        return set(), f"audio file snapshot produced invalid result: {exc}"
    if not isinstance(payload, dict):
        return set(), "audio file snapshot produced invalid result"
    status = payload.get("status")
    if status != "ok":
        message = payload.get("message", "unknown error")
        return set(), f"audio file snapshot failed: {message}"
    paths = payload.get("paths", [])
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        return set(), "audio file snapshot produced invalid paths"
    return {Path(path) for path in paths}, ""


def _snapshot_audio_files(
    target_base: Path,
    slugs: Sequence[str],
    *,
    timeout_seconds: int,
) -> tuple[set[Path], str]:
    if timeout_seconds <= 0:
        return _audio_files_for_slugs(target_base, slugs), ""
    context = multiprocessing.get_context("spawn")
    with tempfile.NamedTemporaryFile(
        prefix="raiplaysound-audio-snapshot-",
        suffix=".json",
        delete=False,
    ) as handle:
        output_file = Path(handle.name)
    process = context.Process(
        target=_collect_audio_files_worker,
        args=(str(target_base), list(slugs), str(output_file)),
    )
    try:
        process.start()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
            return set(), f"audio file snapshot timed out after {timeout_seconds}s"
        if process.exitcode != 0:
            return set(), f"audio file snapshot failed with exit code {process.exitcode}"
        return _read_snapshot_payload(output_file)
    finally:
        output_file.unlink(missing_ok=True)


def _parse_downloaded_file(path: Path) -> tuple[str, str]:
    match = re.match(r"^.+ - (\d{4}-\d{2}-\d{2}) - (.+)$", path.stem)
    if not match:
        return "NA", path.stem
    return match.group(1), match.group(2).replace("⧸", "/")


def build_download_rows(
    *,
    target_base: Path,
    favorites: Sequence[str],
    before: set[Path],
    after: set[Path],
) -> list[DownloadRow]:
    favorite_slugs = _favorite_slugs(favorites)
    slug_by_dir = {target_base / slug: slug for slug in favorite_slugs}
    rows: list[DownloadRow] = []
    for path in sorted(after - before, key=lambda item: (str(item.parent), item.name)):
        program = slug_by_dir.get(path.parent, path.parent.name)
        episode_date, title = _parse_downloaded_file(path)
        rows.append(
            DownloadRow(
                program=program,
                episode_date=episode_date,
                title=title,
                file_name=path.name,
            )
        )
    return rows


def _plain_table(rows: Sequence[DownloadRow]) -> str:
    headers = ("Program", "Date", "Title", "File")
    data = [(row.program, row.episode_date, row.title, row.file_name) for row in rows]
    widths = [
        max(len(headers[index]), *(len(item[index]) for item in data))
        for index in range(len(headers))
    ]
    lines = [
        "  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))),
        "  ".join("-" * widths[index] for index in range(len(headers))),
    ]
    for item in data:
        lines.append("  ".join(item[index].ljust(widths[index]) for index in range(len(headers))))
    return "\n".join(lines)


def build_email_body(*, status_text: str, rows: Sequence[DownloadRow]) -> str:
    lines = [
        "RaiPlaySound CLI daily favourites sync",
        "",
        f"Status: {status_text}",
        f"New episodes downloaded: {len(rows)}",
        "",
    ]
    if rows:
        lines.extend([_plain_table(rows), ""])
    else:
        lines.extend(["No new episodes were downloaded.", ""])
    return "\n".join(lines)


def _extract_from_address(msmtp_config: Path) -> str:
    if not msmtp_config.exists():
        return ""
    for raw_line in msmtp_config.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("from "):
            return line.split(None, 1)[1].strip()
    return ""


def build_email_payload(
    *,
    email_to: str,
    email_from: str,
    email_from_name: str,
    subject: str,
    body: str,
    message_date: str | None = None,
) -> str:
    date_header = message_date or formatdate(localtime=True)
    return (
        f"From: {email_from_name} <{email_from}>\n"
        f"To: {email_to}\n"
        f"Subject: {subject}\n"
        f"Date: {date_header}\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "\n"
        f"{body}"
    )


def _append_log(log_file: Path, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def send_email_summary(
    *,
    config: dict[str, str],
    status_text: str,
    rows: Sequence[DownloadRow],
    dry_run: bool,
    log_file: Path,
) -> int:
    email_to = config.get("EMAIL_TO", "").strip()
    if not email_to:
        _append_log(log_file, "EMAIL_TO is not configured; skipping email summary.")
        return 0
    email_config = _expand_optional_path(
        config.get("EMAIL_CONFIG", ""),
        Path.home() / ".config" / "msmtp" / "config",
    )
    email_from = config.get("EMAIL_FROM", "").strip() or _extract_from_address(email_config)
    if not email_from:
        _append_log(
            log_file, "EMAIL_FROM is not configured and msmtp config has no from; skipping email."
        )
        return 0
    email_from_name = config.get("EMAIL_FROM_NAME", "raiplaysound-cli").strip()
    subject_prefix = config.get("EMAIL_SUBJECT_PREFIX", "[raiplaysound-cli]").strip()
    subject = f"{subject_prefix} daily favourites sync {status_text} on {socket.gethostname()}"
    body = build_email_body(status_text=status_text, rows=rows)
    payload = build_email_payload(
        email_to=email_to,
        email_from=email_from,
        email_from_name=email_from_name,
        subject=subject,
        body=body,
    )
    if dry_run:
        sys.stdout.write(payload)
        if not payload.endswith("\n"):
            sys.stdout.write("\n")
        _append_log(log_file, "Email dry run enabled; payload printed to stdout and not sent.")
        return 0
    msmtp_bin = config.get("MSMTP_BIN", "msmtp").strip() or "msmtp"
    if shutil.which(msmtp_bin) is None:
        _append_log(log_file, f"{msmtp_bin} is not installed or not in PATH; skipping email.")
        return 0
    if not email_config.exists():
        _append_log(log_file, f"msmtp config not found at {email_config}; skipping email.")
        return 0
    result = subprocess.run(
        [msmtp_bin, "--file", str(email_config), "--", email_to],
        input=payload,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode == 0:
        _append_log(log_file, f"Email summary sent to {email_to}.")
        return 0
    _append_log(log_file, f"Failed to send summary email with {msmtp_bin}.")
    return result.returncode


def _run_download(
    cli_args: Sequence[str],
    config_file: Path,
    log_file: Path,
    timeout_seconds: int = 0,
) -> int:
    _append_log(log_file, "Starting daily favourites download.")
    result = run_streamed_process(
        [*cli_args, "--config", str(config_file), "download", "--favourites"],
        on_line=lambda line: _append_log(log_file, line),
        timeout_seconds=timeout_seconds,
    )
    if result.timed_out:
        _append_log(log_file, f"Daily favourites download timed out after {timeout_seconds}s.")
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="raiplaysound-cli-daily-sync",
        description=(
            "Run the configured RaiPlaySound favourites download " "and send an email summary."
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_FILE),
        help="Config file path. Default: ~/.raiplaysound-cli.conf",
    )
    parser.add_argument(
        "--cli",
        default="",
        help="Optional raiplaysound-cli executable path. Defaults to this Python runtime.",
    )
    parser.add_argument(
        "--dry-run-email",
        action="store_true",
        help="Print the email payload instead of sending it.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_file = Path(expand_config_path(args.config))
    config = parse_env_file(config_file)
    settings = Settings.from_config(config)
    log_file = _expand_optional_path(
        config.get("DAILY_SYNC_LOG", ""),
        DEFAULT_LOG_FILE,
    )
    if not settings.favorites:
        _append_log(log_file, "FAVORITES is not configured; nothing to sync.")
        return 1
    slugs = _favorite_slugs(settings.favorites)
    before, before_error = _snapshot_audio_files(
        settings.target_base,
        slugs,
        timeout_seconds=settings.daily_sync_scan_timeout_seconds,
    )
    if before_error:
        _append_log(log_file, f"Before-run {before_error}; new-file summary skipped.")
    if args.cli:
        cli_args = [expand_config_path(args.cli)]
    else:
        cli_args = [sys.executable, "-m", "raiplaysound_cli"]
    download_status = _run_download(
        cli_args,
        config_file,
        log_file,
        timeout_seconds=settings.daily_sync_max_seconds,
    )
    after, after_error = _snapshot_audio_files(
        settings.target_base,
        slugs,
        timeout_seconds=settings.daily_sync_scan_timeout_seconds,
    )
    if after_error:
        _append_log(log_file, f"After-run {after_error}; new-file summary skipped.")
    if before_error or after_error:
        rows: list[DownloadRow] = []
    else:
        rows = build_download_rows(
            target_base=settings.target_base,
            favorites=settings.favorites,
            before=before,
            after=after,
        )
    status_text = (
        "ok" if download_status == 0 and not before_error and not after_error else "failed"
    )
    email_status = send_email_summary(
        config=config,
        status_text=status_text,
        rows=rows,
        dry_run=args.dry_run_email,
        log_file=log_file,
    )
    if download_status:
        return download_status
    if before_error or after_error:
        return email_status or 1
    return email_status


if __name__ == "__main__":
    raise SystemExit(main())
