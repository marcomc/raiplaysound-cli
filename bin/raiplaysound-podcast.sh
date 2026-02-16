#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  raiplaysound-podcast.sh <slug|program_url>

Examples:
  raiplaysound-podcast.sh musicalbox
  raiplaysound-podcast.sh https://www.raiplaysound.it/programmi/musicalbox
USAGE
}

if [[ "$#" -ne 1 ]]; then
  usage
  exit 1
fi

INPUT="$1"
SLUG=""
PROGRAM_URL=""

if printf '%s' "${INPUT}" | grep -Eq '^https?://www\.raiplaysound\.it/programmi/[A-Za-z0-9-]+/?$'; then
  SLUG="$(printf '%s' "${INPUT}" | sed -E 's#^https?://www\.raiplaysound\.it/programmi/([A-Za-z0-9-]+)/?$#\1#' | tr '[:upper:]' '[:lower:]')"
  PROGRAM_URL="https://www.raiplaysound.it/programmi/${SLUG}"
elif printf '%s' "${INPUT}" | grep -Eq '^[A-Za-z0-9-]+$'; then
  SLUG="$(printf '%s' "${INPUT}" | tr '[:upper:]' '[:lower:]')"
  PROGRAM_URL="https://www.raiplaysound.it/programmi/${SLUG}"
else
  echo "Error: input must be a RaiPlaySound slug (e.g. musicalbox) or a full program URL." >&2
  usage
  exit 1
fi

STATE_BASE="${XDG_STATE_HOME:-${HOME}/.local/state}/raiplaysound-downloader"
LOGS_DIR="${RAIPLAYSOUND_LOG_DIR:-${STATE_BASE}/logs}"

TARGET_BASE="${HOME}/Music/RaiPlaySound"
TARGET_DIR="${TARGET_BASE}/${SLUG}"
ARCHIVE_FILE="${TARGET_DIR}/.download-archive.txt"
OUTPUT_TEMPLATE="${TARGET_DIR}/%(series,playlist_title,uploader)s - %(upload_date>%Y-%m-%d)s - %(title)s.%(ext)s"

mkdir -p "${LOGS_DIR}"
mkdir -p "${TARGET_DIR}"

LOCK_DIR="${TARGET_DIR}/.run-lock"
LOCK_PID_FILE="${LOCK_DIR}/pid"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  if [[ -f "${LOCK_PID_FILE}" ]]; then
    LOCK_PID="$(cat "${LOCK_PID_FILE}" 2>/dev/null || true)"
  else
    LOCK_PID=""
  fi

  if [[ -n "${LOCK_PID}" ]] && kill -0 "${LOCK_PID}" 2>/dev/null; then
    echo "Error: another download process is already running for slug '${SLUG}' (PID ${LOCK_PID})." >&2
    exit 1
  fi

  rm -rf "${LOCK_DIR}"
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    echo "Error: unable to acquire lock for slug '${SLUG}'." >&2
    exit 1
  fi
fi
printf '%s\n' "$$" > "${LOCK_PID_FILE}"
trap 'rm -rf "$LOCK_DIR" 2>/dev/null || true' EXIT

RUN_TS="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="${LOGS_DIR}/${SLUG}-run-${RUN_TS}.log"

exec >> "${LOG_FILE}" 2>&1

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "[${START_TS}] Starting download"
echo "Slug: ${SLUG}"
echo "Program URL: ${PROGRAM_URL}"
echo "Output directory: ${TARGET_DIR}"
echo "Archive file: ${ARCHIVE_FILE}"
echo "Log file: ${LOG_FILE}"

yt-dlp \
  --yes-playlist \
  --format "bestaudio/best" \
  --download-archive "${ARCHIVE_FILE}" \
  --no-overwrites \
  --ignore-errors \
  --extract-audio \
  --audio-format m4a \
  --audio-quality 0 \
  --add-metadata \
  --embed-thumbnail \
  -o "${OUTPUT_TEMPLATE}" \
  "${PROGRAM_URL}"

END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "[${END_TS}] Download run completed"
