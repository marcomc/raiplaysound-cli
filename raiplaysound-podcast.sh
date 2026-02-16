#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  raiplaysound-podcast.sh [--format FORMAT] [--jobs N] [--seasons LIST|all] [--redownload-missing] [--list-seasons] [--list-episodes] [--list-stations] [--stations-detailed] [--list-podcasts] [--podcasts-group-by MODE] [--station STATION_SHORT] [--refresh-podcast-catalog] [--catalog-max-age-hours N] [--log[=PATH]] [--refresh-metadata] [--clear-metadata-cache] [--metadata-max-age-hours N] [<slug|program_url>]

Examples:
  raiplaysound-podcast.sh musicalbox
  raiplaysound-podcast.sh https://www.raiplaysound.it/programmi/musicalbox
  raiplaysound-podcast.sh --format mp3 --jobs 3 musicalbox
  raiplaysound-podcast.sh --seasons 1,2 america7
  raiplaysound-podcast.sh --seasons all america7
  raiplaysound-podcast.sh --list-seasons america7
  raiplaysound-podcast.sh --list-episodes --seasons 2 america7
  raiplaysound-podcast.sh --list-stations
  raiplaysound-podcast.sh --list-stations --stations-detailed
  raiplaysound-podcast.sh --list-podcasts
  raiplaysound-podcast.sh --list-podcasts --podcasts-group-by station
  raiplaysound-podcast.sh --list-podcasts --station radio2
  raiplaysound-podcast.sh --refresh-podcast-catalog --list-podcasts
  raiplaysound-podcast.sh --log america7
  raiplaysound-podcast.sh --log=/tmp/raiplaysound-debug.log america7
  raiplaysound-podcast.sh --refresh-metadata america7
  raiplaysound-podcast.sh --clear-metadata-cache america7
  raiplaysound-podcast.sh --redownload-missing america7

Supported formats:
  mp3, m4a, aac, ogg, opus, flac, wav

Default format:
  m4a

Default jobs:
  3

Podcast list grouping modes:
  alpha, station, both
USAGE
}

trim_ws() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "${s}"
}

normalize_bool() {
  local v
  v="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "${v}" in
    1 | true | yes | on) printf '1' ;;
    0 | false | no | off) printf '0' ;;
    *) printf '' ;;
  esac
}

expand_config_path() {
  local p="$1"

  if [[ "${p}" == [~] ]]; then
    p="${HOME}"
  elif [[ "${p}" == [~]/* ]]; then
    p="${HOME}/${p#\~/}"
  fi

  p="${p//\$\{HOME\}/${HOME}}"
  p="${p//\$HOME/${HOME}}"
  printf '%s' "${p}"
}

load_config_file() {
  local config_file="$1"
  local line key raw_value value bool_v

  [[ -f "${config_file}" ]] || return 0

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="$(trim_ws "${line}")"
    [[ -z "${line}" ]] && continue
    [[ "${line}" == \#* ]] && continue
    [[ "${line}" != *=* ]] && continue

    key="$(trim_ws "${line%%=*}")"
    raw_value="${line#*=}"
    value="$(trim_ws "${raw_value}")"

    if [[ "${value}" == \"*\" ]] && [[ "${value}" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "${value}" == \'*\' ]]; then
      value="${value:1:${#value}-2}"
    fi

    case "${key}" in
      AUDIO_FORMAT) AUDIO_FORMAT="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')" ;;
      JOBS) JOBS="${value}" ;;
      SEASONS_ARG) SEASONS_ARG="${value}" ;;
      LIST_SEASONS_ONLY)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && LIST_SEASONS_ONLY="${bool_v}"
        ;;
      LIST_EPISODES_ONLY)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && LIST_EPISODES_ONLY="${bool_v}"
        ;;
      LIST_STATIONS_ONLY)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && LIST_STATIONS_ONLY="${bool_v}"
        ;;
      STATIONS_DETAILED)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && STATIONS_DETAILED="${bool_v}"
        ;;
      LIST_PODCASTS_ONLY)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && LIST_PODCASTS_ONLY="${bool_v}"
        ;;
      PODCASTS_GROUP_BY) PODCASTS_GROUP_BY="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')" ;;
      STATION_FILTER) STATION_FILTER="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')" ;;
      FORCE_REFRESH_CATALOG)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && FORCE_REFRESH_CATALOG="${bool_v}"
        ;;
      CATALOG_MAX_AGE_HOURS) CATALOG_MAX_AGE_HOURS="${value}" ;;
      CATALOG_CACHE_FILE) CATALOG_CACHE_FILE="$(expand_config_path "${value}")" ;;
      AUTO_REDOWNLOAD_MISSING)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && AUTO_REDOWNLOAD_MISSING="${bool_v}"
        ;;
      ENABLE_LOG)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && ENABLE_LOG="${bool_v}"
        ;;
      LOG_PATH_ARG) LOG_PATH_ARG="$(expand_config_path "${value}")" ;;
      FORCE_REFRESH_METADATA)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && FORCE_REFRESH_METADATA="${bool_v}"
        ;;
      CLEAR_METADATA_CACHE)
        bool_v="$(normalize_bool "${value}")"
        [[ -n "${bool_v}" ]] && CLEAR_METADATA_CACHE="${bool_v}"
        ;;
      METADATA_MAX_AGE_HOURS) METADATA_MAX_AGE_HOURS="${value}" ;;
      CHECK_JOBS) CHECK_JOBS="${value}" ;;
      TARGET_BASE) TARGET_BASE="$(expand_config_path "${value}")" ;;
      INPUT)
        INPUT="${value}"
        INPUT_FROM_CONFIG="1"
        ;;
      *) ;;
    esac
  done < "${config_file}"
}

AUDIO_FORMAT="m4a"
JOBS="3"
AUTO_REDOWNLOAD_MISSING="0"
SEASONS_ARG=""
LIST_SEASONS_ONLY="0"
LIST_EPISODES_ONLY="0"
LIST_STATIONS_ONLY="0"
STATIONS_DETAILED="0"
LIST_PODCASTS_ONLY="0"
PODCASTS_GROUP_BY="both"
STATION_FILTER=""
FORCE_REFRESH_CATALOG="0"
CATALOG_MAX_AGE_HOURS="${RAIPLAYSOUND_CATALOG_MAX_AGE_HOURS:-24}"
CATALOG_CACHE_FILE="${HOME}/.local/state/raiplaysound-downloader/podcast-catalog.tsv"
ENABLE_LOG="0"
LOG_PATH_ARG=""
FORCE_REFRESH_METADATA="0"
CLEAR_METADATA_CACHE="0"
METADATA_MAX_AGE_HOURS="${RAIPLAYSOUND_METADATA_MAX_AGE_HOURS:-24}"
CHECK_JOBS="${RAIPLAYSOUND_CHECK_JOBS:-8}"
TARGET_BASE="${HOME}/Music/RaiPlaySound"
INPUT=""
INPUT_FROM_CONFIG="0"

CONFIG_FILE="${HOME}/.raiplaysound-downloader.conf"
load_config_file "${CONFIG_FILE}"

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
    --list-stations)
      LIST_STATIONS_ONLY="1"
      shift
      ;;
    --stations-detailed)
      STATIONS_DETAILED="1"
      shift
      ;;
    --list-podcasts)
      LIST_PODCASTS_ONLY="1"
      shift
      ;;
    --podcasts-group-by)
      if [[ "$#" -lt 2 ]]; then
        echo "Error: --podcasts-group-by requires a value (alpha|station|both)." >&2
        usage
        exit 1
      fi
      PODCASTS_GROUP_BY="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"
      shift 2
      ;;
    --station)
      if [[ "$#" -lt 2 ]]; then
        echo "Error: --station requires a value (for example: radio2, radio1, isoradio, none)." >&2
        usage
        exit 1
      fi
      STATION_FILTER="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"
      shift 2
      ;;
    --refresh-podcast-catalog)
      FORCE_REFRESH_CATALOG="1"
      shift
      ;;
    --catalog-max-age-hours)
      if [[ "$#" -lt 2 ]]; then
        echo "Error: --catalog-max-age-hours requires a value." >&2
        usage
        exit 1
      fi
      CATALOG_MAX_AGE_HOURS="$2"
      shift 2
      ;;
    --refresh-metadata)
      FORCE_REFRESH_METADATA="1"
      shift
      ;;
    --clear-metadata-cache)
      CLEAR_METADATA_CACHE="1"
      shift
      ;;
    --metadata-max-age-hours)
      if [[ "$#" -lt 2 ]]; then
        echo "Error: --metadata-max-age-hours requires a value." >&2
        usage
        exit 1
      fi
      METADATA_MAX_AGE_HOURS="$2"
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
        if [[ "${INPUT_FROM_CONFIG}" -eq 1 ]]; then
          INPUT="$1"
          INPUT_FROM_CONFIG="0"
          shift
          continue
        fi
        echo "Error: only one slug or program URL is allowed." >&2
        usage
        exit 1
      fi
      INPUT="$1"
      INPUT_FROM_CONFIG="0"
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

if ! [[ "${METADATA_MAX_AGE_HOURS}" =~ ^[0-9]+$ ]]; then
  echo "Error: --metadata-max-age-hours must be a non-negative integer." >&2
  exit 1
fi

if ! [[ "${CATALOG_MAX_AGE_HOURS}" =~ ^[0-9]+$ ]]; then
  echo "Error: --catalog-max-age-hours must be a non-negative integer." >&2
  exit 1
fi

if ! [[ "${CHECK_JOBS}" =~ ^[0-9]+$ ]] || [[ "${CHECK_JOBS}" -lt 1 ]]; then
  echo "Error: CHECK_JOBS must be a positive integer." >&2
  exit 1
fi

if [[ "${PODCASTS_GROUP_BY}" != "alpha" ]] && [[ "${PODCASTS_GROUP_BY}" != "station" ]] && [[ "${PODCASTS_GROUP_BY}" != "both" ]]; then
  echo "Error: --podcasts-group-by must be one of: alpha, station, both." >&2
  exit 1
fi

if [[ -n "${STATION_FILTER}" ]] && ! [[ "${STATION_FILTER}" =~ ^[a-z0-9_-]+$ ]]; then
  echo "Error: --station must contain only lowercase letters, numbers, '-' or '_' (example: radio2, isoradio, none)." >&2
  exit 1
fi

if [[ -n "${TARGET_BASE}" ]]; then
  TARGET_BASE="$(expand_config_path "${TARGET_BASE}")"
fi
if [[ -n "${LOG_PATH_ARG}" ]]; then
  LOG_PATH_ARG="$(expand_config_path "${LOG_PATH_ARG}")"
fi
if [[ -n "${CATALOG_CACHE_FILE}" ]]; then
  CATALOG_CACHE_FILE="$(expand_config_path "${CATALOG_CACHE_FILE}")"
fi
if [[ "${TARGET_BASE}" == *"\$HOME"* ]] || [[ "${TARGET_BASE}" == *"\${HOME}"* ]]; then
  echo "Error: TARGET_BASE contains unresolved HOME variable: ${TARGET_BASE}" >&2
  exit 1
fi
if [[ -n "${LOG_PATH_ARG}" ]] && { [[ "${LOG_PATH_ARG}" == *"\$HOME"* ]] || [[ "${LOG_PATH_ARG}" == *"\${HOME}"* ]]; }; then
  echo "Error: LOG_PATH_ARG contains unresolved HOME variable: ${LOG_PATH_ARG}" >&2
  exit 1
fi
if [[ "${CATALOG_CACHE_FILE}" == *"\$HOME"* ]] || [[ "${CATALOG_CACHE_FILE}" == *"\${HOME}"* ]]; then
  echo "Error: CATALOG_CACHE_FILE contains unresolved HOME variable: ${CATALOG_CACHE_FILE}" >&2
  exit 1
fi

if [[ "${LIST_SEASONS_ONLY}" -eq 1 ]] && [[ "${LIST_EPISODES_ONLY}" -eq 1 ]]; then
  echo "Error: use either --list-seasons or --list-episodes, not both." >&2
  exit 1
fi

if [[ "${LIST_STATIONS_ONLY}" -eq 1 ]] && [[ "${LIST_PODCASTS_ONLY}" -eq 1 ]]; then
  echo "Error: use either --list-stations or --list-podcasts, not both." >&2
  exit 1
fi

if [[ "${LIST_STATIONS_ONLY}" -eq 1 ]] || [[ "${LIST_PODCASTS_ONLY}" -eq 1 ]]; then
  if [[ "${LIST_SEASONS_ONLY}" -eq 1 ]] || [[ "${LIST_EPISODES_ONLY}" -eq 1 ]]; then
    echo "Error: station/podcast listing cannot be combined with season/episode listing." >&2
    exit 1
  fi
  if [[ -n "${SEASONS_ARG}" ]]; then
    echo "Error: --seasons is only valid with download mode or --list-episodes." >&2
    exit 1
  fi
  if [[ "${AUTO_REDOWNLOAD_MISSING}" -eq 1 ]]; then
    echo "Error: --redownload-missing is not valid with station/podcast listing." >&2
    exit 1
  fi
  if [[ -n "${INPUT}" ]]; then
    echo "Error: do not pass slug/URL with --list-stations or --list-podcasts." >&2
    exit 1
  fi
fi

if [[ "${LIST_PODCASTS_ONLY}" -eq 0 ]] && [[ "${FORCE_REFRESH_CATALOG}" -eq 1 ]]; then
  echo "Error: --refresh-podcast-catalog can only be used with --list-podcasts." >&2
  exit 1
fi

if [[ "${LIST_PODCASTS_ONLY}" -eq 0 ]] && [[ -n "${STATION_FILTER}" ]]; then
  echo "Error: --station can only be used with --list-podcasts." >&2
  exit 1
fi

if [[ "${LIST_STATIONS_ONLY}" -eq 0 ]] && [[ "${STATIONS_DETAILED}" -eq 1 ]]; then
  echo "Error: --stations-detailed can only be used with --list-stations." >&2
  exit 1
fi

if [[ "${LIST_STATIONS_ONLY}" -eq 0 ]] && [[ "${LIST_PODCASTS_ONLY}" -eq 0 ]] && [[ -z "${INPUT}" ]]; then
  usage
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
    printf '\r%b==>%b %s\033[K' "${C_CYAN}" "${C_RESET}" "${message}"
  else
    printf '%b==>%b %s\n' "${C_CYAN}" "${C_RESET}" "${message}"
  fi
}

finish_stage() {
  local message="$1"
  if [[ "${IS_TTY}" -eq 1 ]]; then
    printf '\r%b==>%b %s\033[K\n' "${C_GREEN}" "${C_RESET}" "${message}"
  else
    printf '%b==>%b %s\n' "${C_GREEN}" "${C_RESET}" "${message}"
  fi
}

collect_stations_file() {
  local out_file="$1"
  curl -Ls --connect-timeout 5 --max-time 30 --retry 2 "https://www.raiplaysound.it/dirette.json" \
    | tr -d '\n' \
    | sed 's/"type":"RaiPlaySound Diretta Item"/\
"type":"RaiPlaySound Diretta Item"/g' \
    | sed -n 's/.*"title":"\([^"]*\)".*"weblink":"\([^"]*\)".*"path_id":"\([^"]*\)".*/\1\t\2\t\3/p' \
    | awk -F '\t' '
        NF >= 3 {
          short=$2
          gsub("^/","",short)
          gsub("/.*$","",short)
          if (short == "") {
            short="unknown"
          }
          if (!seen[short]++) {
            print short"\t"$1"\t"$2"\t"$3
          }
        }
      ' > "${out_file}"
}

cache_file_is_fresh() {
  local cache_file="$1"
  local max_age_hours="$2"
  local cache_mtime now_epoch max_age_seconds cache_age_seconds

  [[ -s "${cache_file}" ]] || return 1

  cache_mtime="$(stat -f '%m' "${cache_file}" 2>/dev/null || true)"
  if [[ -z "${cache_mtime}" ]]; then
    cache_mtime="$(stat -c '%Y' "${cache_file}" 2>/dev/null || true)"
  fi

  now_epoch="$(date '+%s')"
  max_age_seconds=$((max_age_hours * 3600))
  if ! [[ "${cache_mtime}" =~ ^[0-9]+$ ]] || ! [[ "${now_epoch}" =~ ^[0-9]+$ ]]; then
    return 1
  fi

  cache_age_seconds=$((now_epoch - cache_mtime))
  if [[ "${cache_age_seconds}" -ge 0 ]] && [[ "${cache_age_seconds}" -le "${max_age_seconds}" ]]; then
    return 0
  fi
  return 1
}

podcast_cache_format_is_current() {
  local cache_file="$1"
  [[ -s "${cache_file}" ]] || return 1
  if awk -F '\t' '
    NF < 4 { bad=1 }
    $3 == "No station" && tolower($4) != "none" { bad=1 }
    END { exit bad }
  ' "${cache_file}" >/dev/null; then
    return 0
  fi
  return 1
}

collect_podcast_catalog_file() {
  local out_file="$1"
  local tmp_dir slug_file raw_file slug_total
  local sitemap_index_url="https://www.raiplaysound.it/sitemap.archivio.programmi.xml"
  local catalog_jobs="16"

  tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/raiplaysound-catalog.XXXXXX")"
  slug_file="${tmp_dir}/podcast-slugs.txt"
  raw_file="${tmp_dir}/podcast-raw.tsv"

  curl -Ls --connect-timeout 5 --max-time 30 --retry 2 "${sitemap_index_url}" \
    | rg -o 'https://www\.raiplaysound\.it/sitemap\.programmi\.[^<]+' \
    | sed -E 's#^.*/sitemap\.programmi\.##; s#\.xml$##' \
    | sort -u > "${slug_file}"

  slug_total="$(wc -l < "${slug_file}" | tr -d '[:space:]')"
  show_stage "Fetching podcast metadata for ${slug_total} programs with ${catalog_jobs} parallel workers ..."

  : > "${raw_file}"
  declare -a catalog_pids=()
  declare -a catalog_rows=()
  catalog_running=0
  catalog_index=0

  while IFS= read -r slug; do
    [[ -z "${slug}" ]] && continue

    while [[ "${catalog_running}" -ge "${catalog_jobs}" ]]; do
      for ((j = 0; j < ${#catalog_pids[@]}; j++)); do
        if [[ "${catalog_pids[j]}" != "0" ]] && ! kill -0 "${catalog_pids[j]}" 2>/dev/null; then
          wait "${catalog_pids[j]}" || true
          catalog_pids[j]="0"
          catalog_running=$((catalog_running - 1))
        fi
      done
      sleep 0.02
    done

    row_file="${tmp_dir}/podcast-row-${catalog_index}.tsv"
    (
      json_line="$(curl -Ls --connect-timeout 5 --max-time 20 --retry 1 "https://www.raiplaysound.it/programmi/${slug}.json" | tr -d '\n' || true)"
      [[ -z "${json_line}" ]] && exit 0

      title_raw="$(printf '%s' "${json_line}" | awk -F '"title":"' '{if (NF>1) { split($2,a,"\""); print a[1] }}')"
      station_raw="$(printf '%s' "${json_line}" | awk -F '"channel":{"name":"' '{if (NF>1) { split($2,a,"\""); print a[1] }}')"
      station_short_raw="$(printf '%s' "${json_line}" | sed -n 's/.*"channel":{[^}]*"category_path":"\([^"]*\)".*/\1/p')"
      title="${title_raw//\\\//\/}"
      title="${title//\\\"/\"}"
      title="${title//\\n/ }"
      title="${title//\\t/ }"
      title="${title//\\\\/\\}"
      station="${station_raw//\\\//\/}"
      station="${station//\\\"/\"}"
      station="${station//\\n/ }"
      station="${station//\\t/ }"
      station="${station//\\\\/\\}"
      station_short="${station_short_raw//\\\//\/}"
      station_short="${station_short//\\\"/\"}"
      station_short="${station_short//\\n/ }"
      station_short="${station_short//\\t/ }"
      station_short="${station_short//\\\\/\\}"

      [[ -z "${title}" ]] && title="${slug}"
      if [[ -z "${station}" ]]; then
        station="No station"
        station_short="none"
      fi
      if [[ -z "${station_short}" ]]; then
        station_short="unknown"
      fi
      station_short="$(printf '%s' "${station_short}" | tr '[:upper:]' '[:lower:]')"
      printf '%s\t%s\t%s\t%s\n' "${slug}" "${title}" "${station}" "${station_short}" > "${row_file}"
    ) &

    catalog_pids+=("$!")
    catalog_rows+=("${row_file}")
    catalog_running=$((catalog_running + 1))
    catalog_index=$((catalog_index + 1))
  done < "${slug_file}"

  for ((j = 0; j < ${#catalog_pids[@]}; j++)); do
    if [[ "${catalog_pids[j]}" != "0" ]]; then
      wait "${catalog_pids[j]}" || true
    fi
  done

  for row_file in "${catalog_rows[@]}"; do
    [[ -f "${row_file}" ]] || continue
    cat "${row_file}" >> "${raw_file}"
  done

  awk -F '\t' '!seen[$1]++ { print $1"\t"$2"\t"$3"\t"$4 }' "${raw_file}" > "${out_file}"
  rm -rf "${tmp_dir}" 2>/dev/null || true
}

print_podcasts_alpha() {
  local catalog_file="$1"
  local count
  count="$(wc -l < "${catalog_file}" | tr -d '[:space:]')"
  printf 'Podcasts grouped alphabetically (%s):\n' "${count}"
  LC_ALL=C sort -f -t $'\t' -k2,2 -k1,1 "${catalog_file}" | LC_ALL=C awk -F '\t' '
    {
      first=toupper(substr($2,1,1))
      if (first !~ /[A-Z]/) {
        first="#"
      }
      if (first != grp) {
        grp=first
        print ""
        print "[" grp "]"
      }
      printf "  - %s (%s) [%s:%s]\n", $2, $1, $3, $4
    }'
}

print_podcasts_station() {
  local catalog_file="$1"
  local count
  count="$(wc -l < "${catalog_file}" | tr -d '[:space:]')"
  printf 'Podcasts grouped by station (%s):\n' "${count}"
  LC_ALL=C sort -f -t $'\t' -k3,3 -k2,2 "${catalog_file}" | LC_ALL=C awk -F '\t' '
    {
      if ($3 != grp) {
        grp=$3
        grp_short=$4
        print ""
        print "[" grp " | " grp_short "]"
      }
      printf "  - %s (%s)\n", $2, $1
    }'
}

if [[ "${LIST_STATIONS_ONLY}" -eq 1 ]]; then
  LIST_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/raiplaysound-list.XXXXXX")"
  trap 'rm -rf "${LIST_TMP_DIR}" 2>/dev/null || true' EXIT
  STATIONS_FILE="${LIST_TMP_DIR}/stations.tsv"
  show_stage "Loading radio stations ..."
  collect_stations_file "${STATIONS_FILE}"
  station_count="$(wc -l < "${STATIONS_FILE}" | tr -d '[:space:]')"
  finish_stage "Loaded ${station_count} stations."
  if [[ "${STATIONS_DETAILED}" -eq 1 ]]; then
    printf 'Available RaiPlaySound radio stations (detailed):\n'
  else
    printf 'Available RaiPlaySound radio stations (short -> name):\n'
  fi
  while IFS=$'\t' read -r station_short station_name station_link station_json_path; do
    [[ -z "${station_name}" ]] && continue
    if [[ "${STATIONS_DETAILED}" -eq 1 ]]; then
      printf '  - %-16s %s\n' "${station_short}" "${station_name}"
      printf '      page: %s\n' "https://www.raiplaysound.it${station_link}"
      printf '      feed: %s\n' "https://www.raiplaysound.it${station_json_path}"
    else
      printf '  - %-16s %s\n' "${station_short}" "${station_name}"
    fi
  done < "${STATIONS_FILE}"
  exit 0
fi

if [[ "${LIST_PODCASTS_ONLY}" -eq 1 ]]; then
  LIST_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/raiplaysound-list.XXXXXX")"
  trap 'rm -rf "${LIST_TMP_DIR}" 2>/dev/null || true' EXIT
  PODCASTS_FILE="${LIST_TMP_DIR}/podcasts.tsv"
  PODCASTS_FILTERED_FILE="${LIST_TMP_DIR}/podcasts-filtered.tsv"
  mkdir -p "$(dirname "${CATALOG_CACHE_FILE}")"
  cache_format_ok="0"
  set +e
  podcast_cache_format_is_current "${CATALOG_CACHE_FILE}"
  cache_format_rc=$?
  set -e
  if [[ "${cache_format_rc}" -eq 0 ]]; then
    cache_format_ok="1"
  fi
  cache_is_fresh="0"
  if [[ "${FORCE_REFRESH_CATALOG}" -eq 0 ]] && [[ "${cache_format_ok}" -eq 1 ]]; then
    set +e
    cache_file_is_fresh "${CATALOG_CACHE_FILE}" "${CATALOG_MAX_AGE_HOURS}"
    cache_check_rc=$?
    set -e
    if [[ "${cache_check_rc}" -eq 0 ]]; then
      cache_is_fresh="1"
    fi
  fi

  if [[ "${cache_is_fresh}" -eq 1 ]]; then
    show_stage "Using cached podcast catalog ..."
    cp "${CATALOG_CACHE_FILE}" "${PODCASTS_FILE}"
    finish_stage "Podcast catalog cache hit."
  else
    show_stage "Collecting podcast catalog (this can take a while) ..."
    collect_podcast_catalog_file "${PODCASTS_FILE}"
    cp "${PODCASTS_FILE}" "${CATALOG_CACHE_FILE}"
    finish_stage "Podcast catalog cache updated: ${CATALOG_CACHE_FILE}"
  fi

  if [[ -n "${STATION_FILTER}" ]]; then
    awk -F '\t' -v station_filter="${STATION_FILTER}" 'tolower($4) == station_filter { print }' "${PODCASTS_FILE}" > "${PODCASTS_FILTERED_FILE}"
    PODCASTS_FILE="${PODCASTS_FILTERED_FILE}"
    podcast_count="$(wc -l < "${PODCASTS_FILE}" | tr -d '[:space:]')"
    finish_stage "Collected ${podcast_count} podcasts for station '${STATION_FILTER}'."
    if [[ "${podcast_count}" -eq 0 ]]; then
      echo "No podcasts found for station short name '${STATION_FILTER}'." >&2
      echo "Use --list-stations to see valid values (or use 'none' for podcasts without station)." >&2
      exit 1
    fi
  else
    podcast_count="$(wc -l < "${PODCASTS_FILE}" | tr -d '[:space:]')"
    finish_stage "Collected ${podcast_count} podcasts."
  fi

  if [[ "${PODCASTS_GROUP_BY}" == "alpha" ]] || [[ "${PODCASTS_GROUP_BY}" == "both" ]]; then
    print_podcasts_alpha "${PODCASTS_FILE}"
  fi
  if [[ "${PODCASTS_GROUP_BY}" == "both" ]]; then
    printf '\n'
  fi
  if [[ "${PODCASTS_GROUP_BY}" == "station" ]] || [[ "${PODCASTS_GROUP_BY}" == "both" ]]; then
    print_podcasts_station "${PODCASTS_FILE}"
  fi
  exit 0
fi

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

TARGET_DIR="${TARGET_BASE}/${SLUG}"
ARCHIVE_FILE="${TARGET_DIR}/.download-archive.txt"
METADATA_CACHE_FILE="${TARGET_DIR}/.metadata-cache.tsv"
OUTPUT_TEMPLATE="${TARGET_DIR}/%(series,playlist_title,uploader)s - S%(season_number|0)02d%(episode_number|0)02d - %(upload_date>%Y-%m-%d)s - %(episode,title)s.%(ext)s"

mkdir -p "${TARGET_DIR}"

if [[ "${CLEAR_METADATA_CACHE}" -eq 1 ]]; then
  rm -f "${METADATA_CACHE_FILE}"
  finish_stage "Metadata cache cleared: ${METADATA_CACHE_FILE}"
fi

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
declare -A CACHE_UPLOAD_BY_ID=()
declare -A CACHE_TITLE_BY_ID=()
declare -A CACHE_SEASON_BY_ID=()
declare -A META_UPLOAD_BY_ID=()
declare -A META_TITLE_BY_ID=()
declare -A META_SEASON_BY_ID=()
SHOW_YEAR_MIN=""
SHOW_YEAR_MAX=""
DETECTED_SEASON_EVIDENCE="0"
CACHE_IS_FRESH="0"
if [[ "${FORCE_REFRESH_METADATA}" -eq 1 ]]; then
  CACHE_IS_FRESH="0"
elif [[ -f "${METADATA_CACHE_FILE}" ]]; then
  cache_mtime="$(stat -f '%m' "${METADATA_CACHE_FILE}" 2>/dev/null || true)"
  if [[ -z "${cache_mtime}" ]]; then
    cache_mtime="$(stat -c '%Y' "${METADATA_CACHE_FILE}" 2>/dev/null || true)"
  fi
  now_epoch="$(date '+%s')"
  max_age_seconds=$((METADATA_MAX_AGE_HOURS * 3600))
  if [[ "${cache_mtime}" =~ ^[0-9]+$ ]] && [[ "${now_epoch}" =~ ^[0-9]+$ ]]; then
    cache_age_seconds=$((now_epoch - cache_mtime))
    if [[ "${cache_age_seconds}" -ge 0 ]] && [[ "${cache_age_seconds}" -le "${max_age_seconds}" ]]; then
      CACHE_IS_FRESH="1"
    fi
  fi
fi

if [[ "${CACHE_IS_FRESH}" -eq 1 ]]; then
  while IFS=$'\t' read -r cache_id cache_upload cache_season cache_title; do
    [[ -z "${cache_id}" ]] && continue
    CACHE_UPLOAD_BY_ID["${cache_id}"]="${cache_upload}"
    CACHE_SEASON_BY_ID["${cache_id}"]="${cache_season}"
    CACHE_TITLE_BY_ID["${cache_id}"]="${cache_title}"
  done < "${METADATA_CACHE_FILE}"
fi

show_stage "Checking metadata cache ..."
need_metadata_fetch="0"
for ((i = 0; i < TOTAL; i++)); do
  episode_id="${EPISODE_IDS[i]}"
  cache_upload="${CACHE_UPLOAD_BY_ID[${episode_id}]:-}"
  cache_title="${CACHE_TITLE_BY_ID[${episode_id}]:-}"
  cache_season="${CACHE_SEASON_BY_ID[${episode_id}]:-NA}"

  if [[ -z "${cache_upload}" ]] || [[ -z "${cache_title}" ]] || [[ "${cache_title}" == "NA" ]]; then
    need_metadata_fetch="1"
    break
  fi

  META_UPLOAD_BY_ID["${episode_id}"]="${cache_upload}"
  META_TITLE_BY_ID["${episode_id}"]="${cache_title}"
  META_SEASON_BY_ID["${episode_id}"]="${cache_season}"
done
if [[ "${FORCE_REFRESH_METADATA}" -eq 1 ]]; then
  need_metadata_fetch="1"
  finish_stage "Forced metadata refresh requested."
elif [[ "${need_metadata_fetch}" -eq 0 ]]; then
  finish_stage "Metadata cache hit for ${TOTAL} episodes."
elif [[ -f "${METADATA_CACHE_FILE}" ]] && [[ "${CACHE_IS_FRESH}" -eq 0 ]]; then
  finish_stage "Metadata cache is stale. Refreshing."
fi

METADATA_RAW_FILE="${WORK_DIR}/metadata-raw.tsv"
METADATA_FILE="${WORK_DIR}/metadata.tsv"
touch "${METADATA_RAW_FILE}"

if [[ "${need_metadata_fetch}" -eq 1 ]]; then
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
    CACHE_UPLOAD_BY_ID["${meta_id}"]="${meta_upload}"
    CACHE_TITLE_BY_ID["${meta_id}"]="${meta_title}"
    CACHE_SEASON_BY_ID["${meta_id}"]="${meta_season}"
  done < "${METADATA_FILE}"

  METADATA_CACHE_TMP="${WORK_DIR}/metadata-cache.tmp"
  {
    printf '%s\n' "${!CACHE_UPLOAD_BY_ID[@]}" "${!CACHE_TITLE_BY_ID[@]}" | awk 'NF' | sort -u | while IFS= read -r cid; do
      [[ -z "${cid}" ]] && continue
      c_upload="${CACHE_UPLOAD_BY_ID[${cid}]:-NA}"
      c_season="${CACHE_SEASON_BY_ID[${cid}]:-NA}"
      c_title="${CACHE_TITLE_BY_ID[${cid}]:-NA}"
      c_title="${c_title//$'\t'/ }"
      c_title="${c_title//$'\n'/ }"
      printf '%s\t%s\t%s\t%s\n' "${cid}" "${c_upload}" "${c_season}" "${c_title}"
    done
  } > "${METADATA_CACHE_TMP}"
  mv "${METADATA_CACHE_TMP}" "${METADATA_CACHE_FILE}"
fi

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
  declare -a CHECK_PIDS=()
  declare -a CHECK_RESULT_FILES=()
  declare -a CHECK_IDS=()
  declare -a CHECK_LABELS=()
  check_running=0
  check_total=0

  show_stage "Checking archived episodes against local files ..."
  for ((i = 0; i < TOTAL; i++)); do
    episode_id="${EPISODE_IDS[i]}"
    if [[ -z "${ARCHIVED_IDS[${episode_id}]:-}" ]]; then
      continue
    fi
    check_total=$((check_total + 1))

    while [[ "${check_running}" -ge "${CHECK_JOBS}" ]]; do
      for ((j = 0; j < ${#CHECK_PIDS[@]}; j++)); do
        if [[ "${CHECK_PIDS[j]}" != "0" ]] && ! kill -0 "${CHECK_PIDS[j]}" 2>/dev/null; then
          wait "${CHECK_PIDS[j]}" || true
          CHECK_PIDS[j]="0"
          check_running=$((check_running - 1))
        fi
      done
      sleep 0.05
    done

    result_file="${WORK_DIR}/archive-check-${i}.txt"
    check_url="${EPISODE_URLS[i]}"
    (
      set +e
      has_local_media_for_episode "${check_url}"
      media_check_rc=$?
      set -e
      if [[ "${media_check_rc}" -eq 0 ]]; then
        printf 'OK\n' > "${result_file}"
      else
        printf 'MISS\n' > "${result_file}"
      fi
    ) &
    CHECK_PIDS+=("$!")
    CHECK_RESULT_FILES+=("${result_file}")
    CHECK_IDS+=("${episode_id}")
    CHECK_LABELS+=("${EPISODE_LABELS[i]}")
    check_running=$((check_running + 1))
  done

  for ((j = 0; j < ${#CHECK_PIDS[@]}; j++)); do
    if [[ "${CHECK_PIDS[j]}" != "0" ]]; then
      wait "${CHECK_PIDS[j]}" || true
    fi
  done

  for ((j = 0; j < ${#CHECK_RESULT_FILES[@]}; j++)); do
    if [[ -f "${CHECK_RESULT_FILES[j]}" ]] && [[ "$(cat "${CHECK_RESULT_FILES[j]}" 2>/dev/null || true)" == "MISS" ]]; then
      MISSING_ARCHIVE_IDS+=("${CHECK_IDS[j]}")
      MISSING_ARCHIVE_LABELS+=("${CHECK_LABELS[j]}")
    fi
  done
  finish_stage "Archive/local check completed for ${check_total} archived episodes."
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
  printf 'QUEUED|0|--|%s\n' "${EPISODE_LABELS[i]}" > "${STATUS_FILE}"
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

format_bytes() {
  local bytes="$1"
  local whole frac div unit

  if ! [[ "${bytes}" =~ ^[0-9]+$ ]]; then
    printf '?'
    return
  fi

  if ((bytes < 1024)); then
    printf '%dB' "${bytes}"
    return
  elif ((bytes < 1048576)); then
    div=1024
    unit="KiB"
  elif ((bytes < 1073741824)); then
    div=1048576
    unit="MiB"
  elif ((bytes < 1099511627776)); then
    div=1073741824
    unit="GiB"
  else
    div=1099511627776
    unit="TiB"
  fi

  whole=$((bytes / div))
  frac=$(((bytes % div) * 10 / div))
  if ((whole >= 100)); then
    printf '%d%s' "${whole}" "${unit}"
  else
    printf '%d.%d%s' "${whole}" "${frac}" "${unit}"
  fi
}

render_progress() {
  local running_count="$1"
  local completed_count="$2"
  local state percent size label bar color
  local hidden_count display_count
  local -a states=()
  local -a percents=()
  local -a sizes=()
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

  printf '[%s] Starting download\033[K\n' "${START_TS}"
  printf 'Slug: %s\033[K\n' "${SLUG}"
  printf 'Program URL: %s\033[K\n' "${PROGRAM_URL}"
  printf 'Seasons: %s\033[K\n' "${DOWNLOAD_SEASONS_LABEL}"
  printf 'Output directory: %s\033[K\n' "${TARGET_DIR}"
  printf 'Archive file: %s\033[K\n' "${ARCHIVE_FILE}"
  printf 'Output format: %s\033[K\n' "${AUDIO_FORMAT}"
  printf 'Parallel jobs: %s\033[K\n' "${JOBS}"
  if [[ "${ENABLE_LOG}" -eq 1 ]]; then
    printf 'Log file: %s\033[K\n' "${LOG_FILE}"
  fi
  printf '%b==>%b Progress: %d/%d episodes, running=%d\033[K\n\033[K\n' "${C_CYAN}" "${C_RESET}" "${completed_count}" "${TOTAL}" "${running_count}"

  for ((idx = 0; idx < TOTAL; idx++)); do
    IFS='|' read -r state percent size label < "${STATUS_FILES[idx]}"
    states[idx]="${state}"
    percents[idx]="${percent}"
    sizes[idx]="${size}"
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
    size="${sizes[i]}"
    label="${labels[i]}"

    case "${state}" in
      DONE) color="${C_GREEN}" ;;
      SKIP) color="${C_CYAN}" ;;
      ERROR) color="${C_RED}" ;;
      DOWNLOADING) color="${C_YELLOW}" ;;
      *) color="${C_BLUE}" ;;
    esac

    bar="$(make_bar "${percent}")"
    printf '%2d. %b%-11s%b [%s] %3d%%  %-18s %s\033[K\n' "$((i + 1))" "${color}" "${state}" "${C_RESET}" "${bar}" "${percent}" "${size}" "${label}"
  done

  if [[ "${RENDER_COMPACT}" -eq 1 ]]; then
    hidden_count=$((TOTAL - display_count))
    printf '%b==>%b Showing %d/%d rows (%d hidden due to terminal height)\033[K\n' "${C_BLUE}" "${C_RESET}" "${display_count}" "${TOTAL}" "${hidden_count}"
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
    printf 'DOWNLOADING|0|0B/?|%s\n' "${label}" > "${status_file}"

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
          printf 'SKIP|100|downloaded|%s\n' "${label}" > "${status_file}"
          continue
        fi

        if [[ "${line}" == ERROR:* ]]; then
          printf 'ERROR|100|error|%s\n' "${label}" > "${status_file}"
          continue
        fi

        if [[ "${line}" == progress:* ]]; then
          progress_payload="${line#progress:}"
          IFS=':' read -r downloaded_bytes total_bytes total_bytes_estimate raw_percent <<< "${progress_payload}"
          size_display="?"

          percent_candidate=""
          if [[ "${total_bytes}" =~ ^[0-9]+$ ]] && [[ "${total_bytes}" -gt 0 ]] && [[ "${downloaded_bytes}" =~ ^[0-9]+$ ]]; then
            percent_candidate="$((downloaded_bytes * 100 / total_bytes))"
            downloaded_human="$(format_bytes "${downloaded_bytes}")"
            total_human="$(format_bytes "${total_bytes}")"
            size_display="${downloaded_human}/${total_human}"
          elif [[ "${total_bytes_estimate}" =~ ^[0-9]+$ ]] && [[ "${total_bytes_estimate}" -gt 0 ]] && [[ "${downloaded_bytes}" =~ ^[0-9]+$ ]]; then
            percent_candidate="$((downloaded_bytes * 100 / total_bytes_estimate))"
            downloaded_human="$(format_bytes "${downloaded_bytes}")"
            estimate_human="$(format_bytes "${total_bytes_estimate}")"
            size_display="${downloaded_human}/~${estimate_human}"
          else
            raw_percent="${raw_percent%%%*}"
            raw_percent="${raw_percent// /}"
            raw_percent="${raw_percent//$'\r'/}"
            percent_candidate="${raw_percent%%.*}"
            if [[ "${downloaded_bytes}" =~ ^[0-9]+$ ]]; then
              size_display="$(format_bytes "${downloaded_bytes}")/?"
            fi
          fi

          if [[ "${percent_candidate}" =~ ^[0-9]+$ ]]; then
            if [[ "${percent_candidate}" -gt 100 ]]; then
              percent_candidate=100
            fi
            printf 'DOWNLOADING|%s|%s|%s\n' "${percent_candidate}" "${size_display}" "${label}" > "${status_file}"
          fi
        fi
      done

    rc=${PIPESTATUS[0]}
    IFS='|' read -r current_state _ current_size _ < "${status_file}"

    if [[ "${current_state}" == "SKIP" ]]; then
      log_line "Episode skipped by archive: ${label} (${episode_id})"
      exit 0
    fi

    if [[ "${rc}" -eq 0 ]] && [[ "${current_state}" != "ERROR" ]]; then
      if [[ -z "${current_size}" ]] || [[ "${current_size}" == "--" ]] || [[ "${current_size}" == "?" ]]; then
        current_size="done"
      fi
      printf 'DONE|100|%s|%s\n' "${current_size}" "${label}" > "${status_file}"
      log_line "Episode done: ${label} (${episode_id})"
      exit 0
    fi

    printf 'ERROR|100|error|%s\n' "${label}" > "${status_file}"
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
  IFS='|' read -r final_state _ _ _ < "${STATUS_FILES[i]}"
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
