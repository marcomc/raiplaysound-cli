#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  raiplaysound-podcast.sh [--format FORMAT] <slug|program_url>

Examples:
  raiplaysound-podcast.sh musicalbox
  raiplaysound-podcast.sh https://www.raiplaysound.it/programmi/musicalbox
  raiplaysound-podcast.sh --format mp3 musicalbox

Supported formats:
  mp3, m4a, aac, ogg, opus, flac, wav

Default format:
  m4a
USAGE
}

AUDIO_FORMAT="m4a"
INPUT=""

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    -f | --format)
      if [[ "$#" -lt 2 ]]; then
        echo "Error: --format requires a value." >&2
        usage
        exit 1
      fi
      AUDIO_FORMAT="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Error: unknown option '$1'." >&2
      usage
      exit 1
      ;;
    *)
      if [[ -n "${INPUT}" ]]; then
        echo "Error: only one slug or program URL is allowed." >&2
        usage
        exit 1
      fi
      INPUT="$1"
      shift
      ;;
  esac
done

if [[ -z "${INPUT}" && "$#" -eq 1 ]]; then
  INPUT="$1"
  shift
fi

if [[ "$#" -gt 0 ]]; then
  echo "Error: too many arguments." >&2
  usage
  exit 1
fi

if [[ -z "${INPUT}" ]]; then
  usage
  exit 1
fi

SLUG=""
PROGRAM_URL=""

case "${AUDIO_FORMAT}" in
  mp3 | m4a | aac | ogg | opus | flac | wav)
    ;;
  *)
    echo "Error: unsupported format '${AUDIO_FORMAT}'." >&2
    usage
    exit 1
    ;;
esac

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
START_TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "[${START_TS}] Starting download" | tee -a "${LOG_FILE}"
echo "Slug: ${SLUG}" | tee -a "${LOG_FILE}"
echo "Program URL: ${PROGRAM_URL}" | tee -a "${LOG_FILE}"
echo "Output directory: ${TARGET_DIR}" | tee -a "${LOG_FILE}"
echo "Archive file: ${ARCHIVE_FILE}" | tee -a "${LOG_FILE}"
echo "Output format: ${AUDIO_FORMAT}" | tee -a "${LOG_FILE}"
echo "Log file: ${LOG_FILE}" | tee -a "${LOG_FILE}"

# Run yt-dlp in a pseudo-terminal so per-episode progress bars are shown live.
script -q /dev/null \
  yt-dlp \
    --yes-playlist \
    --progress \
    --format "bestaudio/best" \
    --download-archive "${ARCHIVE_FILE}" \
    --no-overwrites \
    --ignore-errors \
    --extract-audio \
    --audio-format "${AUDIO_FORMAT}" \
    --audio-quality 0 \
    --add-metadata \
    --embed-thumbnail \
    -o "${OUTPUT_TEMPLATE}" \
    "${PROGRAM_URL}" | tr -d '\004\010' | sed 's/\^D//g' | tee -a "${LOG_FILE}"

END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "[${END_TS}] Download run completed" | tee -a "${LOG_FILE}"
