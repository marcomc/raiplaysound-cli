#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  raiplaysound-podcast.sh [--format FORMAT] [--jobs N] [--seasons LIST|all] [--redownload-missing] [--list-seasons] [--list-episodes] [--log[=PATH]] <slug|program_url>

Examples:
  raiplaysound-podcast.sh musicalbox
  raiplaysound-podcast.sh https://www.raiplaysound.it/programmi/musicalbox
  raiplaysound-podcast.sh --format mp3 --jobs 3 musicalbox
  raiplaysound-podcast.sh --seasons 1,2 america7
  raiplaysound-podcast.sh --seasons all america7
  raiplaysound-podcast.sh --list-seasons america7
  raiplaysound-podcast.sh --list-episodes --seasons 2 america7
  raiplaysound-podcast.sh --log america7
  raiplaysound-podcast.sh --log=/tmp/raiplaysound-debug.log america7
  raiplaysound-podcast.sh --redownload-missing america7

Supported formats:
  mp3, m4a, aac, ogg, opus, flac, wav

Default format:
  m4a

Default jobs:
  3
USAGE
}

AUDIO_FORMAT="m4a"
JOBS="3"
AUTO_REDOWNLOAD_MISSING="0"
SEASONS_ARG=""
LIST_SEASONS_ONLY="0"
LIST_EPISODES_ONLY="0"
ENABLE_LOG="0"
LOG_PATH_ARG=""
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
    -j | --jobs)
      if [[ "$#" -lt 2 ]]; then
        echo "Error: --jobs requires a value." >&2
        usage
        exit 1
      fi
      JOBS="$2"
      shift 2
      ;;
    -s | --seasons)
      if [[ "$#" -lt 2 ]]; then
        echo "Error: --seasons requires a value (e.g. 1,2)." >&2
        usage
        exit 1
      fi
      if [[ -z "${SEASONS_ARG}" ]]; then
        SEASONS_ARG="$2"
      else
        SEASONS_ARG="${SEASONS_ARG},$2"
      fi
      shift 2
      ;;
    --redownload-missing)
      AUTO_REDOWNLOAD_MISSING="1"
      shift
      ;;
    --log)
      ENABLE_LOG="1"
      if [[ "$#" -ge 2 ]]; then
        candidate="$2"
        if [[ "${candidate}" != -* ]] && ! [[ "${candidate}" =~ ^https?://www\.raiplaysound\.it/programmi/[A-Za-z0-9-]+/?$ ]] && ! [[ "${candidate}" =~ ^[A-Za-z0-9-]+$ ]]; then
          LOG_PATH_ARG="${candidate}"
          shift
        fi
      fi
      shift
      ;;
    --log=*)
      ENABLE_LOG="1"
      LOG_PATH_ARG="${1#--log=}"
      shift
      ;;
    --list-seasons)
      LIST_SEASONS_ONLY="1"
      shift
      ;;
    --list-episodes)
      LIST_EPISODES_ONLY="1"
      shift
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

case "${AUDIO_FORMAT}" in
  mp3 | m4a | aac | ogg | opus | flac | wav)
    ;;
  *)
    echo "Error: unsupported format '${AUDIO_FORMAT}'." >&2
    usage
    exit 1
    ;;
esac

if ! [[ "${JOBS}" =~ ^[0-9]+$ ]] || [[ "${JOBS}" -lt 1 ]]; then
  echo "Error: --jobs must be a positive integer." >&2
  exit 1
fi

if [[ "${LIST_SEASONS_ONLY}" -eq 1 ]] && [[ "${LIST_EPISODES_ONLY}" -eq 1 ]]; then
  echo "Error: use either --list-seasons or --list-episodes, not both." >&2
  exit 1
fi

IS_TTY="0"
if [[ -t 1 ]]; then
  IS_TTY="1"
fi

C_RESET=""
C_GREEN=""
C_YELLOW=""
C_RED=""
C_BLUE=""
C_CYAN=""
if [[ "${IS_TTY}" -eq 1 ]]; then
  C_RESET=$'\033[0m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_BLUE=$'\033[34m'
  C_CYAN=$'\033[36m'
fi

show_stage() {
  local message="$1"
  if [[ "${IS_TTY}" -eq 1 ]]; then
    printf '\r%b==>%b %s' "${C_CYAN}" "${C_RESET}" "${message}"
  else
    printf '%b==>%b %s\n' "${C_CYAN}" "${C_RESET}" "${message}"
  fi
}

finish_stage() {
  local message="$1"
  if [[ "${IS_TTY}" -eq 1 ]]; then
    printf '\r%b==>%b %s\n' "${C_GREEN}" "${C_RESET}" "${message}"
  else
    printf '%b==>%b %s\n' "${C_GREEN}" "${C_RESET}" "${message}"
  fi
}

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

declare -A REQUESTED_SEASONS=()
REQUESTED_SEASONS_COUNT=0
REQUEST_ALL_SEASONS="0"
if [[ -n "${SEASONS_ARG}" ]]; then
  CLEANED_SEASONS_ARG="$(printf '%s' "${SEASONS_ARG}" | tr -d '[:space:]')"
  IFS=',' read -r -a SEASON_PARTS <<< "${CLEANED_SEASONS_ARG}"
  for season_part in "${SEASON_PARTS[@]}"; do
    if [[ -z "${season_part}" ]]; then
      continue
    fi
    lower_season_part="$(printf '%s' "${season_part}" | tr '[:upper:]' '[:lower:]')"
    if [[ "${lower_season_part}" == "all" ]]; then
      REQUEST_ALL_SEASONS="1"
      REQUESTED_SEASONS_COUNT=0
      REQUESTED_SEASONS=()
      continue
    fi
    if [[ "${REQUEST_ALL_SEASONS}" -eq 1 ]]; then
      continue
    fi
    if ! [[ "${season_part}" =~ ^[0-9]+$ ]] || [[ "${season_part}" -lt 1 ]] || [[ "${season_part}" -gt 100 ]]; then
      echo "Error: invalid season '${season_part}'. Allowed values are 1-100 or 'all'." >&2
      exit 1
    fi
    if [[ -z "${REQUESTED_SEASONS[${season_part}]:-}" ]]; then
      REQUESTED_SEASONS["${season_part}"]="1"
      REQUESTED_SEASONS_COUNT=$((REQUESTED_SEASONS_COUNT + 1))
    fi
  done
fi

TARGET_BASE="${HOME}/Music/RaiPlaySound"
TARGET_DIR="${TARGET_BASE}/${SLUG}"
ARCHIVE_FILE="${TARGET_DIR}/.download-archive.txt"
OUTPUT_TEMPLATE="${TARGET_DIR}/%(series,playlist_title,uploader)s - S%(season_number|0)02d%(episode_number|0)02d - %(upload_date>%Y-%m-%d)s - %(episode,title)s.%(ext)s"

mkdir -p "${TARGET_DIR}"

LOCK_DIR="${TARGET_DIR}/.run-lock"
LOCK_PID_FILE="${LOCK_DIR}/pid"
LOCK_ACQUIRED="0"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/raiplaysound.XXXXXX")"
cleanup() {
  if [[ "${CURSOR_HIDDEN:-0}" -eq 1 ]]; then
    printf '\033[?25h'
  fi
  if [[ "${LOCK_ACQUIRED}" -eq 1 ]]; then
    rm -rf "${LOCK_DIR}" 2>/dev/null || true
  fi
  rm -rf "${WORK_DIR}" 2>/dev/null || true
}
trap cleanup EXIT

declare -a EPISODE_IDS=()
declare -a EPISODE_URLS=()
declare -a EPISODE_LABELS=()
declare -a EPISODE_SEASON_HINTS=()
EPISODE_LIST_FILE="${WORK_DIR}/episodes.tsv"
SEASON_SOURCES_FILE="${WORK_DIR}/season-sources.txt"
SEASON_PAGES_FILE="${WORK_DIR}/season-pages.txt"
TMP_EPISODE_LIST_FILE="${WORK_DIR}/episodes-raw.tsv"
touch "${TMP_EPISODE_LIST_FILE}"

USE_EXTENDED_FEEDS="0"
if [[ "${LIST_SEASONS_ONLY}" -eq 1 ]] || [[ "${REQUEST_ALL_SEASONS}" -eq 1 ]] || [[ "${REQUESTED_SEASONS_COUNT}" -gt 0 ]]; then
  USE_EXTENDED_FEEDS="1"
fi

if [[ "${USE_EXTENDED_FEEDS}" -eq 0 ]]; then
  printf '%s\n' "${PROGRAM_URL}" > "${SEASON_SOURCES_FILE}"
  finish_stage "Using main program feed (current season)."
else
  show_stage "Discovering available season pages ..."
  curl -Ls "${PROGRAM_URL}" \
    | rg -o "/programmi/${SLUG}/episodi/stagione-[0-9]+" \
    | awk '!seen[$0]++ { print "https://www.raiplaysound.it"$0 }' \
    | sort -u > "${SEASON_PAGES_FILE}" || true

  if [[ "${REQUESTED_SEASONS_COUNT}" -gt 0 ]] && [[ "${REQUEST_ALL_SEASONS}" -eq 0 ]] && [[ "${LIST_SEASONS_ONLY}" -eq 0 ]]; then
    while IFS= read -r season_page; do
      [[ -z "${season_page}" ]] && continue
      if [[ "${season_page}" =~ stagione-([0-9]+)$ ]]; then
        season_page_num="${BASH_REMATCH[1]}"
        if [[ -n "${REQUESTED_SEASONS[${season_page_num}]:-}" ]]; then
          printf '%s\n' "${season_page}" >> "${SEASON_SOURCES_FILE}"
        fi
      fi
    done < "${SEASON_PAGES_FILE}"
    printf '%s\n' "${PROGRAM_URL}" >> "${SEASON_SOURCES_FILE}"
    sort -u "${SEASON_SOURCES_FILE}" -o "${SEASON_SOURCES_FILE}"
    season_source_count="$(wc -l < "${SEASON_SOURCES_FILE}" | tr -d '[:space:]')"
    finish_stage "Using ${season_source_count} feeds for requested seasons."
  else
    if [[ -s "${SEASON_PAGES_FILE}" ]]; then
      cat "${SEASON_PAGES_FILE}" > "${SEASON_SOURCES_FILE}"
    fi
    printf '%s\n' "${PROGRAM_URL}" >> "${SEASON_SOURCES_FILE}"
    sort -u "${SEASON_SOURCES_FILE}" -o "${SEASON_SOURCES_FILE}"
    season_source_count="$(wc -l < "${SEASON_SOURCES_FILE}" | tr -d '[:space:]')"
    finish_stage "Found ${season_source_count} feeds (season pages + main)."
  fi
fi

show_stage "Discovering episodes from program feeds ..."
while IFS= read -r season_source; do
  [[ -z "${season_source}" ]] && continue
  season_hint=""
  if [[ "${season_source}" =~ stagione-([0-9]+)$ ]]; then
    season_hint="${BASH_REMATCH[1]}"
  fi

  yt-dlp --flat-playlist --print $'%(id)s\t%(webpage_url)s' "${season_source}" \
    | awk -F '\t' -v sh="${season_hint}" 'NF >= 2 { print $1"\t"$2"\t"sh }' >> "${TMP_EPISODE_LIST_FILE}"
done < "${SEASON_SOURCES_FILE}"
finish_stage "Episode feed scan completed."

awk -F '\t' '!seen[$1]++ { print $1"\t"$2"\t"$3 }' "${TMP_EPISODE_LIST_FILE}" > "${EPISODE_LIST_FILE}"

while IFS=$'\t' read -r episode_id episode_url season_hint; do
  if [[ -z "${episode_id}" ]] || [[ -z "${episode_url}" ]]; then
    continue
  fi

  base_name="$(basename "${episode_url}")"
  base_name="${base_name%.json}"
  label="$(printf '%s' "${base_name}" | sed -E "s/-${episode_id}$//")"
  if [[ -z "${label}" ]] || [[ "${label}" == "${base_name}" ]]; then
    label="${episode_id}"
  fi

  EPISODE_IDS+=("${episode_id}")
  EPISODE_URLS+=("${episode_url}")
  EPISODE_LABELS+=("${label}")
  EPISODE_SEASON_HINTS+=("${season_hint}")
done < "${EPISODE_LIST_FILE}"

TOTAL="${#EPISODE_IDS[@]}"
if [[ "${TOTAL}" -eq 0 ]]; then
  if [[ "${IS_TTY}" -eq 1 ]]; then
    printf '\n'
  fi
  echo "No episodes found for ${PROGRAM_URL}." >&2
  exit 1
fi
finish_stage "Discovered ${TOTAL} episodes."

infer_season_from_text() {
  local text="$1"
  if [[ "${text}" =~ [Ss]([0-9]{1,3})[[:space:]_-]*[Ee][0-9]{1,3} ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
    return 0
  fi
  return 1
}

extract_year_from_url() {
  local url="$1"
  if [[ "${url}" =~ /([0-9]{4})/([0-9]{2})/ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
    return 0
  fi
  printf 'NA\n'
  return 0
}

declare -a EPISODE_TITLES=()
declare -a EPISODE_UPLOAD_DATES=()
declare -a EPISODE_SEASONS=()
declare -a EPISODE_YEARS=()
declare -A SEASON_COUNTS=()
declare -A SEASON_YEAR_MIN=()
declare -A SEASON_YEAR_MAX=()
declare -A META_UPLOAD_BY_ID=()
declare -A META_TITLE_BY_ID=()
declare -A META_SEASON_BY_ID=()
SHOW_YEAR_MIN=""
SHOW_YEAR_MAX=""
DETECTED_SEASON_EVIDENCE="0"

METADATA_RAW_FILE="${WORK_DIR}/metadata-raw.tsv"
METADATA_FILE="${WORK_DIR}/metadata.tsv"
touch "${METADATA_RAW_FILE}"

feed_total="$(wc -l < "${SEASON_SOURCES_FILE}" | tr -d '[:space:]')"
feed_index=0
while IFS= read -r season_source; do
  [[ -z "${season_source}" ]] && continue
  feed_index=$((feed_index + 1))
  show_stage "Collecting metadata feed ${feed_index}/${feed_total} ..."
  yt-dlp --skip-download --ignore-errors --print $'%(id)s\t%(upload_date|NA)s\t%(title|NA)s\t%(season_number|NA)s' "${season_source}" \
    | awk -F '\t' 'NF >= 4 { print $1"\t"$2"\t"$3"\t"$4 }' >> "${METADATA_RAW_FILE}"
done < "${SEASON_SOURCES_FILE}"

awk -F '\t' '!seen[$1]++ { print $1"\t"$2"\t"$3"\t"$4 }' "${METADATA_RAW_FILE}" > "${METADATA_FILE}"
while IFS=$'\t' read -r meta_id meta_upload meta_title meta_season; do
  [[ -z "${meta_id}" ]] && continue
  META_UPLOAD_BY_ID["${meta_id}"]="${meta_upload}"
  META_TITLE_BY_ID["${meta_id}"]="${meta_title}"
  META_SEASON_BY_ID["${meta_id}"]="${meta_season}"
done < "${METADATA_FILE}"

for ((i = 0; i < TOTAL; i++)); do
  show_stage "Normalizing metadata ${i}/${TOTAL} ..."
  episode_id="${EPISODE_IDS[i]}"
  episode_url="${EPISODE_URLS[i]}"
  label="${EPISODE_LABELS[i]}"
  season_hint="${EPISODE_SEASON_HINTS[i]}"

  upload_date="${META_UPLOAD_BY_ID[${episode_id}]:-NA}"
  meta_title="${META_TITLE_BY_ID[${episode_id}]:-NA}"
  season_number="${META_SEASON_BY_ID[${episode_id}]:-NA}"

  if [[ -z "${meta_title}" ]] || [[ "${meta_title}" == "NA" ]]; then
    meta_title="$(printf '%s' "${label}" | tr '-' ' ')"
  fi
  if [[ -z "${upload_date}" ]]; then
    upload_date="NA"
  fi

  season_candidate="NA"
  if [[ -n "${season_number}" ]] && [[ "${season_number}" != "NA" ]] && [[ "${season_number}" =~ ^[0-9]+$ ]]; then
    season_candidate="${season_number}"
    DETECTED_SEASON_EVIDENCE="1"
  elif [[ -n "${season_hint}" ]] && [[ "${season_hint}" =~ ^[0-9]+$ ]]; then
    season_candidate="${season_hint}"
    DETECTED_SEASON_EVIDENCE="1"
  else
    set +e
    season_from_title="$(infer_season_from_text "${meta_title}")"
    season_from_title_rc=$?
    set -e
    if [[ "${season_from_title_rc}" -eq 0 ]]; then
      season_candidate="${season_from_title}"
      DETECTED_SEASON_EVIDENCE="1"
    fi
  fi
  if ! [[ "${season_candidate}" =~ ^[0-9]+$ ]]; then
    season_candidate="1"
  fi

  if [[ "${upload_date}" =~ ^[0-9]{8}$ ]]; then
    episode_year="${upload_date:0:4}"
  else
    episode_year="$(extract_year_from_url "${episode_url}")"
  fi

  EPISODE_TITLES+=("${meta_title}")
  EPISODE_UPLOAD_DATES+=("${upload_date}")
  EPISODE_SEASONS+=("${season_candidate}")
  EPISODE_YEARS+=("${episode_year}")

  SEASON_COUNTS["${season_candidate}"]=$((SEASON_COUNTS["${season_candidate}"] + 1))
  if [[ "${episode_year}" =~ ^[0-9]{4}$ ]]; then
    if [[ -z "${SHOW_YEAR_MIN}" ]] || [[ "${episode_year}" -lt "${SHOW_YEAR_MIN}" ]]; then
      SHOW_YEAR_MIN="${episode_year}"
    fi
    if [[ -z "${SHOW_YEAR_MAX}" ]] || [[ "${episode_year}" -gt "${SHOW_YEAR_MAX}" ]]; then
      SHOW_YEAR_MAX="${episode_year}"
    fi
    if [[ -z "${SEASON_YEAR_MIN[${season_candidate}]:-}" ]] || [[ "${episode_year}" -lt "${SEASON_YEAR_MIN[${season_candidate}]}" ]]; then
      SEASON_YEAR_MIN["${season_candidate}"]="${episode_year}"
    fi
    if [[ -z "${SEASON_YEAR_MAX[${season_candidate}]:-}" ]] || [[ "${episode_year}" -gt "${SEASON_YEAR_MAX[${season_candidate}]}" ]]; then
      SEASON_YEAR_MAX["${season_candidate}"]="${episode_year}"
    fi
  fi
done
finish_stage "Metadata collected for ${TOTAL} episodes."

AVAILABLE_SEASONS_SORTED="$(printf '%s\n' "${!SEASON_COUNTS[@]}" | sort -n)"
LATEST_SEASON="$(printf '%s\n' "${!SEASON_COUNTS[@]}" | sort -n | tail -n 1)"
if [[ -z "${LATEST_SEASON}" ]]; then
  LATEST_SEASON="1"
fi
HAS_SEASONS="0"
if [[ "${DETECTED_SEASON_EVIDENCE}" -eq 1 ]]; then
  HAS_SEASONS="1"
fi
season_key_count="$(printf '%s\n' "${!SEASON_COUNTS[@]}" | wc -l | tr -d '[:space:]')"
if [[ "${season_key_count}" -gt 1 ]]; then
  HAS_SEASONS="1"
fi

if [[ "${REQUESTED_SEASONS_COUNT}" -gt 0 ]]; then
  if [[ "${HAS_SEASONS}" -eq 0 ]]; then
    echo "Error: '${SLUG}' does not expose seasons, so --seasons cannot be used." >&2
    exit 1
  fi
  for requested_season in "${!REQUESTED_SEASONS[@]}"; do
    if [[ -z "${SEASON_COUNTS[${requested_season}]:-}" ]]; then
      echo "Error: season ${requested_season} is not available for '${SLUG}'." >&2
      exit 1
    fi
  done
fi

if [[ "${LIST_SEASONS_ONLY}" -eq 1 ]]; then
  if [[ "${HAS_SEASONS}" -eq 0 ]]; then
    show_year_span="unknown year"
    if [[ "${SHOW_YEAR_MIN}" =~ ^[0-9]{4}$ ]] && [[ "${SHOW_YEAR_MAX}" =~ ^[0-9]{4}$ ]]; then
      if [[ "${SHOW_YEAR_MIN}" == "${SHOW_YEAR_MAX}" ]]; then
        show_year_span="${SHOW_YEAR_MIN}"
      else
        show_year_span="${SHOW_YEAR_MIN}-${SHOW_YEAR_MAX}"
      fi
    fi
    printf 'No seasons detected for %s (%s).\n' "${SLUG}" "${PROGRAM_URL}"
    printf '  - Episodes: %d (published: %s)\n' "${TOTAL}" "${show_year_span}"
  else
    printf 'Available seasons for %s (%s):\n' "${SLUG}" "${PROGRAM_URL}"
    while IFS= read -r season; do
      [[ -z "${season}" ]] && continue
      year_min="${SEASON_YEAR_MIN[${season}]:-NA}"
      year_max="${SEASON_YEAR_MAX[${season}]:-NA}"
      year_span="unknown year"
      if [[ "${year_min}" =~ ^[0-9]{4}$ ]] && [[ "${year_max}" =~ ^[0-9]{4}$ ]]; then
        if [[ "${year_min}" == "${year_max}" ]]; then
          year_span="${year_min}"
        else
          year_span="${year_min}-${year_max}"
        fi
      fi
      printf '  - Season %s: %s episodes (published: %s)\n' "${season}" "${SEASON_COUNTS[${season}]}" "${year_span}"
    done <<< "${AVAILABLE_SEASONS_SORTED}"
  fi
  exit 0
fi

if [[ "${LIST_EPISODES_ONLY}" -eq 1 ]]; then
  declare -A LIST_SEASONS=()
  if [[ "${HAS_SEASONS}" -eq 0 ]]; then
    LIST_SEASONS["1"]="1"
  elif [[ "${REQUEST_ALL_SEASONS}" -eq 1 ]]; then
    while IFS= read -r all_season; do
      [[ -z "${all_season}" ]] && continue
      LIST_SEASONS["${all_season}"]="1"
    done <<< "${AVAILABLE_SEASONS_SORTED}"
  elif [[ "${REQUESTED_SEASONS_COUNT}" -gt 0 ]]; then
    for requested_season in "${!REQUESTED_SEASONS[@]}"; do
      LIST_SEASONS["${requested_season}"]="1"
    done
  else
    LIST_SEASONS["${LATEST_SEASON}"]="1"
  fi

  printf 'Episodes for %s (%s):\n' "${SLUG}" "${PROGRAM_URL}"
  if [[ "${HAS_SEASONS}" -eq 0 ]]; then
    printf '  Season model: none (single stream)\n'
  else
    printf '  Seasons: '
    first_printed="1"
    for list_season in $(printf '%s\n' "${!LIST_SEASONS[@]}" | sort -n); do
      if [[ "${first_printed}" -eq 1 ]]; then
        printf '%s' "${list_season}"
        first_printed="0"
      else
        printf ',%s' "${list_season}"
      fi
    done
    printf '\n'
  fi

  for ((i = 0; i < TOTAL; i++)); do
    season="${EPISODE_SEASONS[i]}"
    if [[ -z "${LIST_SEASONS[${season}]:-}" ]]; then
      continue
    fi
    upload_date="${EPISODE_UPLOAD_DATES[i]}"
    pretty_date="unknown-date"
    if [[ "${upload_date}" =~ ^[0-9]{8}$ ]]; then
      pretty_date="${upload_date:0:4}-${upload_date:4:2}-${upload_date:6:2}"
    fi
    if [[ "${HAS_SEASONS}" -eq 0 ]]; then
      printf '  - %s | %s\n' "${pretty_date}" "${EPISODE_TITLES[i]}"
    else
      printf '  - S%s | %s | %s\n' "${season}" "${pretty_date}" "${EPISODE_TITLES[i]}"
    fi
  done
  exit 0
fi

if [[ "${HAS_SEASONS}" -eq 1 ]] && [[ "${REQUEST_ALL_SEASONS}" -eq 0 ]] && [[ "${REQUESTED_SEASONS_COUNT}" -eq 0 ]] && [[ "${LIST_SEASONS_ONLY}" -eq 0 ]] && [[ "${LIST_EPISODES_ONLY}" -eq 0 ]]; then
  declare -a FILTERED_IDS=()
  declare -a FILTERED_URLS=()
  declare -a FILTERED_LABELS=()
  declare -a FILTERED_TITLES=()
  declare -a FILTERED_UPLOAD_DATES=()
  declare -a FILTERED_SEASONS=()
  declare -a FILTERED_YEARS=()

  for ((i = 0; i < TOTAL; i++)); do
    season="${EPISODE_SEASONS[i]}"
    if [[ "${season}" != "${LATEST_SEASON}" ]]; then
      continue
    fi
    FILTERED_IDS+=("${EPISODE_IDS[i]}")
    FILTERED_URLS+=("${EPISODE_URLS[i]}")
    FILTERED_LABELS+=("${EPISODE_LABELS[i]}")
    FILTERED_TITLES+=("${EPISODE_TITLES[i]}")
    FILTERED_UPLOAD_DATES+=("${EPISODE_UPLOAD_DATES[i]}")
    FILTERED_SEASONS+=("${EPISODE_SEASONS[i]}")
    FILTERED_YEARS+=("${EPISODE_YEARS[i]}")
  done

  EPISODE_IDS=("${FILTERED_IDS[@]}")
  EPISODE_URLS=("${FILTERED_URLS[@]}")
  EPISODE_LABELS=("${FILTERED_LABELS[@]}")
  EPISODE_TITLES=("${FILTERED_TITLES[@]}")
  EPISODE_UPLOAD_DATES=("${FILTERED_UPLOAD_DATES[@]}")
  EPISODE_SEASONS=("${FILTERED_SEASONS[@]}")
  EPISODE_YEARS=("${FILTERED_YEARS[@]}")
  TOTAL="${#EPISODE_IDS[@]}"
fi

if [[ "${HAS_SEASONS}" -eq 1 ]] && [[ "${REQUESTED_SEASONS_COUNT}" -gt 0 ]]; then
  declare -a FILTERED_IDS=()
  declare -a FILTERED_URLS=()
  declare -a FILTERED_LABELS=()
  declare -a FILTERED_TITLES=()
  declare -a FILTERED_UPLOAD_DATES=()
  declare -a FILTERED_SEASONS=()
  declare -a FILTERED_YEARS=()

  for ((i = 0; i < TOTAL; i++)); do
    season="${EPISODE_SEASONS[i]}"
    if [[ -z "${REQUESTED_SEASONS[${season}]:-}" ]]; then
      continue
    fi
    FILTERED_IDS+=("${EPISODE_IDS[i]}")
    FILTERED_URLS+=("${EPISODE_URLS[i]}")
    FILTERED_LABELS+=("${EPISODE_LABELS[i]}")
    FILTERED_TITLES+=("${EPISODE_TITLES[i]}")
    FILTERED_UPLOAD_DATES+=("${EPISODE_UPLOAD_DATES[i]}")
    FILTERED_SEASONS+=("${EPISODE_SEASONS[i]}")
    FILTERED_YEARS+=("${EPISODE_YEARS[i]}")
  done

  EPISODE_IDS=("${FILTERED_IDS[@]}")
  EPISODE_URLS=("${FILTERED_URLS[@]}")
  EPISODE_LABELS=("${FILTERED_LABELS[@]}")
  EPISODE_TITLES=("${FILTERED_TITLES[@]}")
  EPISODE_UPLOAD_DATES=("${FILTERED_UPLOAD_DATES[@]}")
  EPISODE_SEASONS=("${FILTERED_SEASONS[@]}")
  EPISODE_YEARS=("${FILTERED_YEARS[@]}")
  TOTAL="${#EPISODE_IDS[@]}"
fi

if [[ "${TOTAL}" -eq 0 ]]; then
  echo "No episodes selected for download." >&2
  exit 1
fi

if [[ "${REQUEST_ALL_SEASONS}" -eq 1 ]]; then
  DOWNLOAD_SEASONS_LABEL="all (${AVAILABLE_SEASONS_SORTED//$'\n'/,})"
elif [[ "${REQUESTED_SEASONS_COUNT}" -gt 0 ]]; then
  DOWNLOAD_SEASONS_LABEL="$(printf '%s\n' "${!REQUESTED_SEASONS[@]}" | sort -n | paste -sd ',' -)"
elif [[ "${HAS_SEASONS}" -eq 0 ]]; then
  DOWNLOAD_SEASONS_LABEL="none (all episodes)"
else
  DOWNLOAD_SEASONS_LABEL="current (${LATEST_SEASON})"
fi

RUN_TS="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE=""
if [[ "${ENABLE_LOG}" -eq 1 ]]; then
  if [[ -z "${LOG_PATH_ARG}" ]]; then
    LOG_FILE="${TARGET_DIR}/${SLUG}-run-${RUN_TS}.log"
  elif [[ -d "${LOG_PATH_ARG}" ]] || [[ "${LOG_PATH_ARG}" == */ ]]; then
    mkdir -p "${LOG_PATH_ARG}"
    LOG_FILE="${LOG_PATH_ARG%/}/${SLUG}-run-${RUN_TS}.log"
  else
    mkdir -p "$(dirname "${LOG_PATH_ARG}")"
    LOG_FILE="${LOG_PATH_ARG}"
  fi
  : > "${LOG_FILE}"
fi

log_line() {
  if [[ "${ENABLE_LOG}" -eq 1 ]]; then
    printf '%s\n' "$1" >> "${LOG_FILE}"
  fi
}

acquire_lock() {
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    lock_pid=""
    if [[ -f "${LOCK_PID_FILE}" ]]; then
      lock_pid="$(cat "${LOCK_PID_FILE}" 2>/dev/null || true)"
    fi
    if [[ -n "${lock_pid}" ]] && kill -0 "${lock_pid}" 2>/dev/null; then
      echo "Error: another download process is already running for slug '${SLUG}' (PID ${lock_pid})." >&2
      exit 1
    fi
    rm -rf "${LOCK_DIR}"
    if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
      echo "Error: unable to acquire lock for slug '${SLUG}'." >&2
      exit 1
    fi
  fi
  printf '%s\n' "$$" > "${LOCK_PID_FILE}"
  LOCK_ACQUIRED="1"
}

acquire_lock

START_TS="$(date '+%Y-%m-%d %H:%M:%S')"
if [[ ! -t 1 ]]; then
  printf '[%s] Starting download\n' "${START_TS}"
  printf 'Slug: %s\n' "${SLUG}"
  printf 'Program URL: %s\n' "${PROGRAM_URL}"
  printf 'Seasons: %s\n' "${DOWNLOAD_SEASONS_LABEL}"
  printf 'Output directory: %s\n' "${TARGET_DIR}"
  printf 'Archive file: %s\n' "${ARCHIVE_FILE}"
  printf 'Output format: %s\n' "${AUDIO_FORMAT}"
  printf 'Parallel jobs: %s\n' "${JOBS}"
  if [[ "${ENABLE_LOG}" -eq 1 ]]; then
    printf 'Log file: %s\n' "${LOG_FILE}"
  fi
fi

log_line "[${START_TS}] Starting download"
log_line "Slug: ${SLUG}"
log_line "Program URL: ${PROGRAM_URL}"
log_line "Seasons: ${DOWNLOAD_SEASONS_LABEL}"
log_line "Output directory: ${TARGET_DIR}"
log_line "Archive file: ${ARCHIVE_FILE}"
log_line "Output format: ${AUDIO_FORMAT}"
log_line "Parallel jobs: ${JOBS}"
if [[ "${ENABLE_LOG}" -eq 1 ]]; then
  log_line "Log file: ${LOG_FILE}"
fi

declare -A ARCHIVED_IDS=()
if [[ -f "${ARCHIVE_FILE}" ]]; then
  while read -r extractor archived_id _; do
    if [[ -n "${extractor}" ]] && [[ -n "${archived_id}" ]]; then
      ARCHIVED_IDS["${archived_id}"]="1"
    fi
  done < "${ARCHIVE_FILE}"
fi

has_local_media_for_episode() {
  local episode_url="$1"
  local resolved
  local base
  local ext

  resolved="$(yt-dlp --skip-download --parse-metadata 'title:^(?P<series>.+?) S(?P<season_number>[0-9]+)E(?P<episode_number>[0-9]+)\s*(?P<episode>.*)$' --print filename -o "${OUTPUT_TEMPLATE}" "${episode_url}" 2>/dev/null | head -n 1 || true)"
  if [[ -z "${resolved}" ]]; then
    return 1
  fi

  base="${resolved%.*}"
  for ext in "${AUDIO_FORMAT}" mp3 m4a aac ogg opus flac wav mp4 webm m4b; do
    if [[ -f "${base}.${ext}" ]]; then
      return 0
    fi
  done

  return 1
}

declare -a MISSING_ARCHIVE_IDS=()
declare -a MISSING_ARCHIVE_LABELS=()
if [[ "${#ARCHIVED_IDS[@]}" -gt 0 ]]; then
  for ((i = 0; i < TOTAL; i++)); do
    episode_id="${EPISODE_IDS[i]}"
    if [[ -z "${ARCHIVED_IDS[${episode_id}]:-}" ]]; then
      continue
    fi

    set +e
    has_local_media_for_episode "${EPISODE_URLS[i]}"
    media_check_rc=$?
    set -e
    if [[ "${media_check_rc}" -ne 0 ]]; then
      MISSING_ARCHIVE_IDS+=("${episode_id}")
      MISSING_ARCHIVE_LABELS+=("${EPISODE_LABELS[i]}")
    fi
  done
fi

if [[ "${#MISSING_ARCHIVE_IDS[@]}" -gt 0 ]]; then
  log_line "Detected ${#MISSING_ARCHIVE_IDS[@]} archived episodes with missing local files."
  MISSING_IDS_FILE="${WORK_DIR}/missing-archive-ids.txt"
  printf '%s\n' "${MISSING_ARCHIVE_IDS[@]}" > "${MISSING_IDS_FILE}"

  if [[ "${AUTO_REDOWNLOAD_MISSING}" -eq 1 ]]; then
    if [[ -f "${ARCHIVE_FILE}" ]]; then
      awk 'NR==FNR { drop[$1]=1; next } !($2 in drop)' "${MISSING_IDS_FILE}" "${ARCHIVE_FILE}" > "${ARCHIVE_FILE}.tmp"
      mv "${ARCHIVE_FILE}.tmp" "${ARCHIVE_FILE}"
      log_line "Auto mode enabled: removed ${#MISSING_ARCHIVE_IDS[@]} IDs from archive for re-download."
    fi
  elif [[ -t 0 ]]; then
    printf '\nDetected %d archived episodes with missing local files:\n' "${#MISSING_ARCHIVE_IDS[@]}"
    for ((i = 0; i < ${#MISSING_ARCHIVE_IDS[@]}; i++)); do
      printf '  - %s (%s)\n' "${MISSING_ARCHIVE_LABELS[i]}" "${MISSING_ARCHIVE_IDS[i]}"
    done

    read -r -p "Re-download these missing archived episodes now? [y/N] " reply
    case "${reply}" in
      y | Y | yes | YES)
        if [[ -f "${ARCHIVE_FILE}" ]]; then
          awk 'NR==FNR { drop[$1]=1; next } !($2 in drop)' "${MISSING_IDS_FILE}" "${ARCHIVE_FILE}" > "${ARCHIVE_FILE}.tmp"
          mv "${ARCHIVE_FILE}.tmp" "${ARCHIVE_FILE}"
          log_line "Removed ${#MISSING_ARCHIVE_IDS[@]} IDs from archive for re-download."
        fi
        ;;
      *)
        log_line "User chose not to re-download missing archived episodes."
        ;;
    esac
  else
    log_line "Non-interactive mode: skipping re-download prompt for missing archived episodes."
  fi
fi

declare -a STATUS_FILES=()
declare -a PIDS=()
declare -a ACTIVE=()
for ((i = 0; i < TOTAL; i++)); do
  STATUS_FILE="${WORK_DIR}/status_${i}.txt"
  printf 'QUEUED|0|%s\n' "${EPISODE_LABELS[i]}" > "${STATUS_FILE}"
  STATUS_FILES+=("${STATUS_FILE}")
  PIDS+=("0")
  ACTIVE+=("0")
done

CURSOR_HIDDEN="0"
RENDER_INITIALIZED="0"
RENDER_HEADER_LINES="10"
if [[ "${ENABLE_LOG}" -eq 1 ]]; then
  RENDER_HEADER_LINES=$((RENDER_HEADER_LINES + 1))
fi
TERM_LINES="$(tput lines 2>/dev/null || printf '24')"
if ! [[ "${TERM_LINES}" =~ ^[0-9]+$ ]] || [[ "${TERM_LINES}" -lt 12 ]]; then
  TERM_LINES="24"
fi
DISPLAY_STATUS_LINES=$((TERM_LINES - RENDER_HEADER_LINES - 2))
if [[ "${DISPLAY_STATUS_LINES}" -lt 3 ]]; then
  DISPLAY_STATUS_LINES=3
fi
RENDER_COMPACT="0"
if [[ "${TOTAL}" -gt "${DISPLAY_STATUS_LINES}" ]]; then
  RENDER_COMPACT="1"
fi
RENDER_EXTRA_LINES=0
if [[ "${RENDER_COMPACT}" -eq 1 ]]; then
  RENDER_EXTRA_LINES=1
  RENDER_BODY_LINES="${DISPLAY_STATUS_LINES}"
else
  RENDER_BODY_LINES="${TOTAL}"
fi
RENDER_TOTAL_LINES="$((RENDER_HEADER_LINES + RENDER_BODY_LINES + RENDER_EXTRA_LINES))"

make_bar() {
  local percent="$1"
  local width=30
  local fill=$((percent * width / 100))
  local empty=$((width - fill))
  local left=""
  local right=""
  if [[ "${fill}" -gt 0 ]]; then
    printf -v left '%*s' "${fill}" ''
    left="${left// /#}"
  fi
  if [[ "${empty}" -gt 0 ]]; then
    printf -v right '%*s' "${empty}" ''
    right="${right// /-}"
  fi
  printf '%s%s' "${left}" "${right}"
}

render_progress() {
  local running_count="$1"
  local completed_count="$2"
  local state percent label bar color
  local hidden_count display_count
  local -a states=()
  local -a percents=()
  local -a labels=()
  local -a visible_indices=()
  local idx i

  if [[ "${IS_TTY}" -ne 1 ]]; then
    return
  fi

  if [[ "${RENDER_INITIALIZED}" -eq 1 ]]; then
    printf '\033[%dA' "${RENDER_TOTAL_LINES}"
  else
    printf '\033[?25l'
    CURSOR_HIDDEN="1"
    RENDER_INITIALIZED="1"
  fi

  printf '[%s] Starting download\n' "${START_TS}"
  printf 'Slug: %s\n' "${SLUG}"
  printf 'Program URL: %s\n' "${PROGRAM_URL}"
  printf 'Seasons: %s\n' "${DOWNLOAD_SEASONS_LABEL}"
  printf 'Output directory: %s\n' "${TARGET_DIR}"
  printf 'Archive file: %s\n' "${ARCHIVE_FILE}"
  printf 'Output format: %s\n' "${AUDIO_FORMAT}"
  printf 'Parallel jobs: %s\n' "${JOBS}"
  if [[ "${ENABLE_LOG}" -eq 1 ]]; then
    printf 'Log file: %s\n' "${LOG_FILE}"
  fi
  printf '%b==>%b Progress: %d/%d episodes, running=%d\n\n' "${C_CYAN}" "${C_RESET}" "${completed_count}" "${TOTAL}" "${running_count}"

  for ((idx = 0; idx < TOTAL; idx++)); do
    IFS='|' read -r state percent label < "${STATUS_FILES[idx]}"
    states[idx]="${state}"
    percents[idx]="${percent}"
    labels[idx]="${label}"
  done

  if [[ "${RENDER_COMPACT}" -eq 0 ]]; then
    display_count="${TOTAL}"
    for ((idx = 0; idx < TOTAL; idx++)); do
      visible_indices+=("${idx}")
    done
  else
    display_count="${DISPLAY_STATUS_LINES}"
    declare -A seen=()

    # Always prioritize currently running/error rows.
    for ((idx = 0; idx < TOTAL; idx++)); do
      state="${states[idx]}"
      if [[ "${state}" == "DOWNLOADING" ]] || [[ "${state}" == "ERROR" ]]; then
        if [[ -z "${seen[${idx}]:-}" ]]; then
          visible_indices+=("${idx}")
          seen["${idx}"]=1
        fi
      fi
    done

    # Then show upcoming queued rows near the scheduler pointer.
    for ((idx = next; idx < TOTAL; idx++)); do
      [[ "${#visible_indices[@]}" -ge "${display_count}" ]] && break
      state="${states[idx]}"
      if [[ "${state}" == "QUEUED" ]] && [[ -z "${seen[${idx}]:-}" ]]; then
        visible_indices+=("${idx}")
        seen["${idx}"]=1
      fi
    done

    # Then show most recent completed/skipped from the end.
    for ((idx = TOTAL - 1; idx >= 0; idx--)); do
      [[ "${#visible_indices[@]}" -ge "${display_count}" ]] && break
      state="${states[idx]}"
      if [[ "${state}" == "DONE" ]] || [[ "${state}" == "SKIP" ]]; then
        if [[ -z "${seen[${idx}]:-}" ]]; then
          visible_indices+=("${idx}")
          seen["${idx}"]=1
        fi
      fi
    done

    # Fill any remaining slots with unshown rows in natural order.
    for ((idx = 0; idx < TOTAL; idx++)); do
      [[ "${#visible_indices[@]}" -ge "${display_count}" ]] && break
      if [[ -z "${seen[${idx}]:-}" ]]; then
        visible_indices+=("${idx}")
        seen["${idx}"]=1
      fi
    done
  fi

  for i in "${visible_indices[@]}"; do
    state="${states[i]}"
    percent="${percents[i]}"
    label="${labels[i]}"

    case "${state}" in
      DONE) color="${C_GREEN}" ;;
      SKIP) color="${C_CYAN}" ;;
      ERROR) color="${C_RED}" ;;
      DOWNLOADING) color="${C_YELLOW}" ;;
      *) color="${C_BLUE}" ;;
    esac

    bar="$(make_bar "${percent}")"
    printf '%2d. %b%-11s%b [%s] %3d%%  %s\n' "$((i + 1))" "${color}" "${state}" "${C_RESET}" "${bar}" "${percent}" "${label}"
  done

  if [[ "${RENDER_COMPACT}" -eq 1 ]]; then
    hidden_count=$((TOTAL - display_count))
    printf '%b==>%b Showing %d/%d rows (%d hidden due to terminal height)\n' "${C_BLUE}" "${C_RESET}" "${display_count}" "${TOTAL}" "${hidden_count}"
  fi
}

start_episode_download() {
  local idx="$1"
  local episode_id="${EPISODE_IDS[idx]}"
  local episode_url="${EPISODE_URLS[idx]}"
  local label="${EPISODE_LABELS[idx]}"
  local status_file="${STATUS_FILES[idx]}"

  (
    log_line "Starting episode: ${label} (${episode_id})"
    printf 'DOWNLOADING|0|%s\n' "${label}" > "${status_file}"

    yt_verbose_args=()
    if [[ "${ENABLE_LOG}" -eq 1 ]]; then
      yt_verbose_args+=(--verbose)
    fi

    yt-dlp \
      --format "bestaudio/best" \
      --parse-metadata 'title:^(?P<series>.+?) S(?P<season_number>[0-9]+)E(?P<episode_number>[0-9]+)\s*(?P<episode>.*)$' \
      --download-archive "${ARCHIVE_FILE}" \
      --no-overwrites \
      --ignore-errors \
      --extract-audio \
      --audio-format "${AUDIO_FORMAT}" \
      --audio-quality 0 \
      --add-metadata \
      --embed-thumbnail \
      --newline \
      --progress \
      --progress-template 'progress:%(progress.downloaded_bytes|0)d:%(progress.total_bytes|0)d:%(progress.total_bytes_estimate|0)d:%(progress._percent_str)s' \
      "${yt_verbose_args[@]}" \
      -o "${OUTPUT_TEMPLATE}" \
      "${episode_url}" 2>&1 | while IFS= read -r line; do
        if [[ "${ENABLE_LOG}" -eq 1 ]] && [[ "${line}" != download:*%* ]]; then
          printf '%s\n' "${line}" >> "${LOG_FILE}"
        fi

        if [[ "${line}" == *"has already been recorded in the archive"* ]]; then
          printf 'SKIP|100|%s\n' "${label}" > "${status_file}"
          continue
        fi

        if [[ "${line}" == ERROR:* ]]; then
          printf 'ERROR|100|%s\n' "${label}" > "${status_file}"
          continue
        fi

        if [[ "${line}" == progress:* ]]; then
          progress_payload="${line#progress:}"
          IFS=':' read -r downloaded_bytes total_bytes total_bytes_estimate raw_percent <<< "${progress_payload}"

          percent_candidate=""
          if [[ "${total_bytes}" =~ ^[0-9]+$ ]] && [[ "${total_bytes}" -gt 0 ]] && [[ "${downloaded_bytes}" =~ ^[0-9]+$ ]]; then
            percent_candidate="$((downloaded_bytes * 100 / total_bytes))"
          elif [[ "${total_bytes_estimate}" =~ ^[0-9]+$ ]] && [[ "${total_bytes_estimate}" -gt 0 ]] && [[ "${downloaded_bytes}" =~ ^[0-9]+$ ]]; then
            percent_candidate="$((downloaded_bytes * 100 / total_bytes_estimate))"
          else
            raw_percent="${raw_percent%%%*}"
            raw_percent="${raw_percent// /}"
            raw_percent="${raw_percent//$'\r'/}"
            percent_candidate="${raw_percent%%.*}"
          fi

          if [[ "${percent_candidate}" =~ ^[0-9]+$ ]]; then
            if [[ "${percent_candidate}" -gt 100 ]]; then
              percent_candidate=100
            fi
            printf 'DOWNLOADING|%s|%s\n' "${percent_candidate}" "${label}" > "${status_file}"
          fi
        fi
      done

    rc=${PIPESTATUS[0]}
    IFS='|' read -r current_state _ _ < "${status_file}"

    if [[ "${current_state}" == "SKIP" ]]; then
      log_line "Episode skipped by archive: ${label} (${episode_id})"
      exit 0
    fi

    if [[ "${rc}" -eq 0 ]] && [[ "${current_state}" != "ERROR" ]]; then
      printf 'DONE|100|%s\n' "${label}" > "${status_file}"
      log_line "Episode done: ${label} (${episode_id})"
      exit 0
    fi

    printf 'ERROR|100|%s\n' "${label}" > "${status_file}"
    log_line "Episode error: ${label} (${episode_id}) rc=${rc}"
    exit 1
  ) &

  PIDS[idx]="$!"
  ACTIVE[idx]="1"
}

running=0
completed=0
next=0

while [[ "${completed}" -lt "${TOTAL}" ]]; do
  while [[ "${running}" -lt "${JOBS}" ]] && [[ "${next}" -lt "${TOTAL}" ]]; do
    start_episode_download "${next}"
    running=$((running + 1))
    next=$((next + 1))
  done

  for ((i = 0; i < TOTAL; i++)); do
    if [[ "${ACTIVE[i]}" -eq 1 ]] && ! kill -0 "${PIDS[i]}" 2>/dev/null; then
      if wait "${PIDS[i]}"; then
        :
      fi
      ACTIVE[i]="0"
      running=$((running - 1))
      completed=$((completed + 1))
    fi
  done

  render_progress "${running}" "${completed}"
  sleep 0.5
done

render_progress 0 "${completed}"

done_count=0
skip_count=0
error_count=0
for ((i = 0; i < TOTAL; i++)); do
  IFS='|' read -r final_state _ _ < "${STATUS_FILES[i]}"
  case "${final_state}" in
    DONE)
      done_count=$((done_count + 1))
      ;;
    SKIP)
      skip_count=$((skip_count + 1))
      ;;
    ERROR)
      error_count=$((error_count + 1))
      ;;
    *)
      ;;
  esac
done

if [[ "${IS_TTY}" -eq 1 ]]; then
  printf '\n'
fi
printf '%b==>%b Completed: done=%d, skipped=%d, errors=%d\n' "${C_BLUE}" "${C_RESET}" "${done_count}" "${skip_count}" "${error_count}"
END_TS="$(date '+%Y-%m-%d %H:%M:%S')"
log_line "[${END_TS}] Download run completed"
log_line "Summary: done=${done_count}, skipped=${skip_count}, errors=${error_count}"

if [[ "${error_count}" -gt 0 ]]; then
  exit 1
fi
