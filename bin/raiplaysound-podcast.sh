#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./bin/raiplaysound-podcast.sh <slug|program_url>

Examples:
  ./bin/raiplaysound-podcast.sh musicalbox
  ./bin/raiplaysound-podcast.sh https://www.raiplaysound.it/programmi/musicalbox
USAGE
}

if [ "$#" -ne 1 ]; then
  usage
  exit 1
fi

INPUT="$1"
SLUG=""
PROGRAM_URL=""

if printf '%s' "$INPUT" | grep -Eq '^https?://www\.raiplaysound\.it/programmi/[A-Za-z0-9-]+/?$'; then
  SLUG="$(printf '%s' "$INPUT" | sed -E 's#^https?://www\.raiplaysound\.it/programmi/([A-Za-z0-9-]+)/?$#\1#' | tr '[:upper:]' '[:lower:]')"
  PROGRAM_URL="https://www.raiplaysound.it/programmi/${SLUG}"
elif printf '%s' "$INPUT" | grep -Eq '^[A-Za-z0-9-]+$'; then
  SLUG="$(printf '%s' "$INPUT" | tr '[:upper:]' '[:lower:]')"
  PROGRAM_URL="https://www.raiplaysound.it/programmi/${SLUG}"
else
  echo "Error: input must be a RaiPlaySound slug (e.g. musicalbox) or a full program URL." >&2
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOGS_DIR="${PROJECT_ROOT}/logs"

TARGET_BASE="${HOME}/Music/RaiPlaySound"
TARGET_DIR="${TARGET_BASE}/${SLUG}"
ARCHIVE_FILE="${TARGET_DIR}/.download-archive.txt"
OUTPUT_TEMPLATE="${TARGET_DIR}/%(series,playlist_title,uploader)s - %(upload_date>%Y-%m-%d)s - %(title)s.%(ext)s"

mkdir -p "$LOGS_DIR"
mkdir -p "$TARGET_DIR"

RUN_TS="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="${LOGS_DIR}/run-${RUN_TS}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting download"
echo "Slug: ${SLUG}"
echo "Program URL: ${PROGRAM_URL}"
echo "Output directory: ${TARGET_DIR}"
echo "Archive file: ${ARCHIVE_FILE}"
echo "Log file: ${LOG_FILE}"

yt-dlp \
  --yes-playlist \
  --download-archive "$ARCHIVE_FILE" \
  --no-overwrites \
  --ignore-errors \
  --extract-audio \
  --audio-format m4a \
  --audio-quality 0 \
  --add-metadata \
  --embed-thumbnail \
  -o "$OUTPUT_TEMPLATE" \
  "$PROGRAM_URL"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Download run completed"
