# RaiPlaySound Podcast Downloader

A Bash-based downloader for RaiPlaySound programs that accepts a podcast slug or full program URL, downloads all episodes, and keeps future runs incremental using `yt-dlp --download-archive`.

## Features

- Accepts either a RaiPlaySound slug (for example, `musicalbox`) or full program URL
- Downloads playlist/program episodes from RaiPlaySound
- Saves audio as `.m4a`
- Uses sortable file naming:
  - `PodcastName - YYYY-MM-DD - EpisodeTitle.m4a`
- Stores files in `~/Music/RaiPlaySound/<slug>/`
- Keeps a per-podcast archive file (`.download-archive.txt`) to avoid re-downloading episodes
- Writes per-run logs to `~/.local/state/raiplaysound-downloader/logs/<slug>-run-YYYYMMDD-HHMMSS.log`
- Safe to run repeatedly (idempotent)
- Supports common podcast output formats: `mp3`, `m4a`, `aac`, `ogg`, `opus`, `flac`, `wav`
- Converts only when source format differs from requested output format

## Installation

1. Create or enter the project directory:

```bash
cd raiplaysound-downloader
```

1. Install dependencies with Homebrew:

```bash
brew install yt-dlp ffmpeg
```

1. Make the script executable:

```bash
chmod +x ./raiplaysound-podcast.sh
```

## Usage

Run using a slug:

```bash
./raiplaysound-podcast.sh musicalbox
```

If installed in your `PATH`, run from any directory:

```bash
raiplaysound-podcast.sh musicalbox
```

Run using a full program URL:

```bash
./raiplaysound-podcast.sh https://www.raiplaysound.it/programmi/musicalbox
```

Run and choose output format:

```bash
./raiplaysound-podcast.sh --format mp3 musicalbox
```

Reference episode example for this program:

- [Musical Box episode example](https://www.raiplaysound.it/audio/2026/02/Musical-Box-del-15022026-da038798-68f0-489b-9aa9-dc8b5cc45d64.html)

## Cron Example

Run daily at 06:30:

```cron
30 6 * * * /usr/local/bin/raiplaysound-podcast.sh musicalbox
```

## How `--download-archive` Works

The script uses `--download-archive` with:

- `~/Music/RaiPlaySound/<slug>/.download-archive.txt`

Each downloaded episode ID is recorded in that file. On later runs, `yt-dlp` checks the archive and skips episodes already present there. This makes repeated runs incremental and prevents duplicate downloads.
