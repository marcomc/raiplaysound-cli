from __future__ import annotations

from pathlib import Path
from typing import Iterator

from raiplaysound_cli import outputs
from raiplaysound_cli.models import ProgramDetails


def test_generate_rss_feed_uses_cache_and_filename_fallback(monkeypatch, tmp_path: Path) -> None:
    target_dir = tmp_path / "america7"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-1\t20240101\t1\tEpisode & One\n",
        encoding="utf-8",
    )
    (target_dir / "America7 - 2024-01-01 - file-title.m4a").write_bytes(b"audio-one")
    (target_dir / "America7 - 2024-01-02 - fallback-title.mp3").write_bytes(b"audio-two")
    monkeypatch.setattr(outputs, "fetch_show_title", lambda _slug: "America & Seven")
    details = ProgramDetails(
        slug="america7",
        title="America & Seven",
        author="Oliviero & RAI",
        description="Description & details",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="https://www.raiplaysound.it/cover.jpg",
        artwork_file="cover.jpg",
    )
    (target_dir / "cover.jpg").write_bytes(b"cover")

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "america7",
        "https://www.raiplaysound.it/programmi/america7",
        metadata_cache_file,
        "https://example.test/audio",
        details,
    )
    content = feed_path.read_text(encoding="utf-8")

    assert feed_path == target_dir / "feed.xml"
    assert "<title>America &amp; Seven</title>" in content
    assert "<description>Description &amp; details</description>" in content
    assert "<itunes:author>Oliviero &amp; RAI</itunes:author>" in content
    assert '<itunes:image href="https://example.test/audio/america7/cover.jpg"/>' in content
    assert "<url>https://example.test/audio/america7/cover.jpg</url>" in content
    assert "<title>Episode &amp; One</title>" in content
    assert "<title>fallback-title</title>" in content
    assert "https://example.test/audio/america7/" in content
    assert "%20fallback-title.mp3" in content


def test_generate_playlist_sorts_by_date_and_uses_cache_title(tmp_path: Path) -> None:
    target_dir = tmp_path / "musicalbox"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-2\t20240102\t1\tSecond Episode\n" "ep-1\t20240101\t1\tFirst Episode\n",
        encoding="utf-8",
    )
    (target_dir / "Musical Box - 2024-01-02 - two.m4a").write_bytes(b"two")
    (target_dir / "Musical Box - 2024-01-01 - one.m4a").write_bytes(b"one")

    playlist_path = outputs.generate_playlist(target_dir, metadata_cache_file)
    lines = playlist_path.read_text(encoding="utf-8").splitlines()

    assert playlist_path == target_dir / "playlist.m3u"
    assert lines == [
        "#EXTM3U",
        "#EXTINF:-1,First Episode",
        "Musical Box - 2024-01-01 - one.m4a",
        "#EXTINF:-1,Second Episode",
        "Musical Box - 2024-01-02 - two.m4a",
    ]


def test_outputs_fall_back_to_filename_when_date_is_ambiguous(tmp_path: Path, monkeypatch) -> None:
    target_dir = tmp_path / "america7"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-1\t20240101\t1\tFirst Title\n" "ep-2\t20240101\t1\tSecond Title\n",
        encoding="utf-8",
    )
    first = target_dir / "America7 - 2024-01-01 - file-one.m4a"
    second = target_dir / "America7 - 2024-01-01 - file-two.m4a"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    monkeypatch.setattr(outputs, "fetch_show_title", lambda _slug: "America7")

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "america7",
        "https://www.raiplaysound.it/programmi/america7",
        metadata_cache_file,
        "",
    )
    playlist_path = outputs.generate_playlist(target_dir, metadata_cache_file)
    feed_content = feed_path.read_text(encoding="utf-8")
    playlist_content = playlist_path.read_text(encoding="utf-8")

    assert "file-one" in feed_content
    assert "file-two" in feed_content
    assert "First Title" not in feed_content
    assert "Second Title" not in feed_content
    assert f'<enclosure url="{first.resolve().as_uri()}"' in feed_content
    assert f'<enclosure url="{second.resolve().as_uri()}"' in feed_content
    assert "#EXTINF:-1,file-one" in playlist_content
    assert "#EXTINF:-1,file-two" in playlist_content


def test_generate_rss_feed_keeps_multiple_same_day_files_when_cache_is_partial(
    monkeypatch, tmp_path: Path
) -> None:
    target_dir = tmp_path / "musicalbox"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-1\t20240101\t1\tEpisode One\n",
        encoding="utf-8",
    )
    (target_dir / "Musical Box - 2024-01-01 - first-title.m4a").write_bytes(b"first")
    (target_dir / "Musical Box - 2024-01-01 - second-title.m4a").write_bytes(b"second")
    monkeypatch.setattr(outputs, "fetch_show_title", lambda _slug: "Musical Box")

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "musicalbox",
        "https://www.raiplaysound.it/programmi/musicalbox",
        metadata_cache_file,
        "",
    )
    content = feed_path.read_text(encoding="utf-8")

    assert content.count("<item>") == 2
    assert '<guid isPermaLink="false">ep-1</guid>' not in content
    assert "first-title" in content
    assert "second-title" in content


def test_prepare_program_assets_downloads_artwork_and_writes_details(
    monkeypatch, tmp_path: Path
) -> None:
    target_dir = tmp_path / "america7"
    target_dir.mkdir()
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="RAI",
        description="Show description",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="https://www.raiplaysound.it/dl/img/cover.png",
    )
    monkeypatch.setattr(outputs, "fetch_program_details", lambda _slug: details)
    monkeypatch.setattr(outputs, "http_get_bytes", lambda *_args, **_kwargs: (b"png", "image/png"))

    result = outputs.prepare_program_assets(
        target_dir,
        "america7",
        "https://www.raiplaysound.it/programmi/america7",
    )

    assert result.artwork_file == "cover.png"
    assert (target_dir / "cover.png").read_bytes() == b"png"
    assert '"artwork_file": "cover.png"' in (target_dir / outputs.PROGRAM_INFO_FILE).read_text(
        encoding="utf-8"
    )


def test_prepare_program_assets_preserves_cached_details_when_fetch_fails(
    monkeypatch, tmp_path: Path
) -> None:
    target_dir = tmp_path / "america7"
    target_dir.mkdir()
    cached = ProgramDetails(
        slug="america7",
        title="Cached Title",
        author="Cached Author",
        description="Cached description",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="https://www.raiplaysound.it/dl/img/cover.png",
        artwork_file="cover.png",
    )
    outputs.write_program_details(target_dir, cached)
    (target_dir / "cover.png").write_bytes(b"cover")
    monkeypatch.setattr(outputs, "fetch_program_details", lambda _slug: None)
    monkeypatch.setattr(outputs, "http_get_bytes", lambda *_args, **_kwargs: (b"png", "image/png"))

    result = outputs.prepare_program_assets(
        target_dir,
        "america7",
        "https://www.raiplaysound.it/programmi/america7",
    )

    assert result.title == "Cached Title"
    assert result.author == "Cached Author"
    assert result.description == "Cached description"
    assert result.image_url == "https://www.raiplaysound.it/dl/img/cover.png"
    assert result.artwork_file == "cover.png"
    assert '"title": "Cached Title"' in (target_dir / outputs.PROGRAM_INFO_FILE).read_text(
        encoding="utf-8"
    )


def test_prepare_program_assets_preserves_cached_artwork_when_download_fails(
    monkeypatch, tmp_path: Path
) -> None:
    target_dir = tmp_path / "america7"
    target_dir.mkdir()
    cached = ProgramDetails(
        slug="america7",
        title="Cached Title",
        author="Cached Author",
        description="Cached description",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="https://www.raiplaysound.it/dl/img/cached-cover.png",
        artwork_file="cover.png",
    )
    fetched = ProgramDetails(
        slug="america7",
        title="Fresh Title",
        author="Fresh Author",
        description="Fresh description",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="https://www.raiplaysound.it/dl/img/new-cover.png",
        artwork_file="",
    )
    outputs.write_program_details(target_dir, cached)
    (target_dir / "cover.png").write_bytes(b"cover")
    monkeypatch.setattr(outputs, "fetch_program_details", lambda _slug: fetched)
    monkeypatch.setattr(
        outputs,
        "http_get_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()),
    )

    result = outputs.prepare_program_assets(
        target_dir,
        "america7",
        "https://www.raiplaysound.it/programmi/america7",
    )

    assert result.title == "Fresh Title"
    assert result.author == "Fresh Author"
    assert result.description == "Fresh description"
    assert result.artwork_file == "cover.png"
    assert '"artwork_file": "cover.png"' in (target_dir / outputs.PROGRAM_INFO_FILE).read_text(
        encoding="utf-8"
    )


def test_generate_program_index_hides_missing_feed_link(monkeypatch, tmp_path: Path) -> None:
    target_base = tmp_path / "RaiPlaySound"
    show_dir = target_base / "america7"
    show_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="Oliviero Bergamini",
        description="America oltre gli stereotipi.",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="",
        artwork_file="cover.jpg",
    )
    outputs.write_program_details(show_dir, details)
    (show_dir / "cover.jpg").write_bytes(b"cover")
    (show_dir / "America7 - 2024-01-01 - one.m4a").write_bytes(b"one")

    index_path = outputs.generate_program_index(target_base, "https://example.test/audio")
    content = index_path.read_text(encoding="utf-8")

    assert index_path == target_base / "index.html"
    assert "America7" in content
    assert '<link rel="apple-touch-icon" href="apple-touch-icon.png">' in content
    assert '<link rel="icon" href="apple-touch-icon.png">' in content
    assert "<title>RaiPlayPodcast</title>" in content
    assert "RaiPlayPodcast</h1>" in content
    assert '<img class="app-icon" src="apple-touch-icon.png" alt="" aria-hidden="true">' in content
    assert "Oliviero Bergamini" in content
    assert "1 episodi" in content
    assert "Ultimo: 2024-01-01" in content
    assert "america7/cover.jpg" in content
    assert "Apple Podcasts" not in content
    assert "https://example.test/audio" not in content
    assert "feed.xml" not in content

    (show_dir / "feed.xml").write_text("<rss></rss>\n", encoding="utf-8")

    content = outputs.generate_program_index(target_base, "https://example.test/audio").read_text(
        encoding="utf-8"
    )

    assert '<a class="feed" href="https://example.test/audio/america7/feed.xml">RSS</a>' in content
    assert 'href="pcast://example.test/audio/america7/feed.xml"' in content
    assert "Apple Podcasts" in content
    assert "america7/cover.jpg" in content

    content = outputs.generate_program_index(
        target_base,
        "https://example.test/audio",
        apple_podcasts=False,
    ).read_text(encoding="utf-8")

    assert '<a class="feed" href="https://example.test/audio/america7/feed.xml">RSS</a>' in content
    assert "Apple Podcasts" not in content
    assert "pcast://example.test/audio/america7/feed.xml" not in content


def test_generate_program_index_uses_editorial_latest_date_from_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    show_dir = target_base / "musicalbox"
    show_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    outputs.write_program_details(
        show_dir,
        ProgramDetails(
            slug="musicalbox",
            title="Musical Box",
            author="Raffaele Costantino",
            description="Musica.",
            page_url="https://www.raiplaysound.it/programmi/musicalbox",
            image_url="",
            artwork_file="cover.jpg",
        ),
    )
    (show_dir / "cover.jpg").write_bytes(b"cover")
    (show_dir / ".metadata-cache.tsv").write_text(
        "ep-sat\t20260509\tNA\tMusical Box del 09/05/2026\n"
        "ep-sun\t20260510\tNA\tMusical Box del 10/05/2026\n",
        encoding="utf-8",
    )
    (show_dir / "Musical Box - 2026-05-10 - Musical Box del 09\u29f805\u29f82026.m4a").write_bytes(
        b"sat"
    )
    (show_dir / "Musical Box - 2026-05-11 - Musical Box del 10\u29f805\u29f82026.m4a").write_bytes(
        b"sun"
    )

    content = outputs.generate_program_index(target_base, "").read_text(encoding="utf-8")

    assert "2 episodi" in content
    assert "Ultimo: 2026-05-10" in content
    assert "Ultimo: 2026-05-11" not in content


def test_generate_local_outputs_regenerates_selected_artifacts(monkeypatch, tmp_path: Path) -> None:
    target_base = tmp_path / "RaiPlaySound"
    show_dir = target_base / "america7"
    show_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="Oliviero Bergamini",
        description="America oltre gli stereotipi.",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="",
        artwork_file="cover.jpg",
    )
    outputs.write_program_details(show_dir, details)
    (show_dir / "cover.jpg").write_bytes(b"cover")
    (show_dir / ".metadata-cache.tsv").write_text(
        "ep-1\t20240101\tNA\tEpisode One\n",
        encoding="utf-8",
    )
    (show_dir / "America7 - 2024-01-01 - Episode One.m4a").write_bytes(b"audio")

    result = outputs.generate_local_outputs(
        target_base,
        "https://example.test/audio",
        rss=True,
        playlist=True,
        index=True,
        apple_podcasts=False,
    )

    assert result["rss"] == 1
    assert result["playlist"] == 1
    assert result["index"] == target_base / "index.html"
    assert (show_dir / "feed.xml").exists()
    assert (show_dir / "playlist.m3u").exists()
    index_content = (target_base / "index.html").read_text(encoding="utf-8")
    assert "https://example.test/audio/america7/feed.xml" in index_content
    assert "Apple Podcasts" not in index_content


def test_generate_local_outputs_playlist_only_does_not_refresh_assets(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    show_dir = target_base / "america7"
    show_dir.mkdir(parents=True)
    (show_dir / ".metadata-cache.tsv").write_text(
        "ep-1\t20240101\tNA\tEpisode One\n",
        encoding="utf-8",
    )
    (show_dir / "America7 - 2024-01-01 - Episode One.m4a").write_bytes(b"audio")

    def fail_asset_refresh(_show_dir: Path, _slug: str) -> ProgramDetails:
        raise AssertionError("playlist-only regeneration must not refresh program assets")

    monkeypatch.setattr(outputs, "ensure_program_assets", fail_asset_refresh)

    result = outputs.generate_local_outputs(target_base, playlist=True)

    assert result["playlist"] == 1
    assert (show_dir / "playlist.m3u").exists()
    assert not (show_dir / outputs.PROGRAM_INFO_FILE).exists()


def test_generate_program_index_backfills_missing_program_artwork(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    show_dir = target_base / "radio2storierock"
    show_dir.mkdir(parents=True)
    (show_dir / "Radio2 Storie Rock - 2024-01-01 - one.m4a").write_bytes(b"one")
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    monkeypatch.setattr(
        outputs,
        "fetch_program_details",
        lambda slug: ProgramDetails(
            slug=slug,
            title="Radio2 Storie Rock",
            author="RAI",
            description="Storie rock.",
            page_url=f"https://www.raiplaysound.it/programmi/{slug}",
            image_url=(
                "https://www.raiplaysound.it/dl/img/2021/11/19/"
                "1637311880369_radio2%20storie-rock_2048x2048.jpg"
            ),
        ),
    )
    monkeypatch.setattr(outputs, "http_get_bytes", lambda *_args, **_kwargs: (b"jpg", "image/jpeg"))

    content = outputs.generate_program_index(target_base, "").read_text(encoding="utf-8")

    assert (show_dir / "cover.jpg").read_bytes() == b"jpg"
    assert (show_dir / outputs.PROGRAM_INFO_FILE).exists()
    assert "radio2storierock/cover.jpg" in content
    assert "Radio2 Storie Rock" in content


def test_generate_program_index_skips_unreadable_program_folder(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    good_dir = target_base / "america7"
    bad_dir = target_base / "broken-show"
    good_dir.mkdir(parents=True)
    bad_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="Oliviero Bergamini",
        description="America oltre gli stereotipi.",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="",
        artwork_file="cover.jpg",
    )
    outputs.write_program_details(good_dir, details)
    (good_dir / "cover.jpg").write_bytes(b"cover")
    (good_dir / "America7 - 2024-01-01 - one.m4a").write_bytes(b"one")

    original_iterdir = Path.iterdir

    def patched_iterdir(path: Path) -> Iterator[Path]:
        if path == bad_dir:
            raise PermissionError("unreadable folder")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", patched_iterdir)

    content = outputs.generate_program_index(target_base, "").read_text(encoding="utf-8")

    assert "America7" in content
    assert "broken-show" not in content


def test_generate_program_index_skips_folder_when_asset_refresh_cannot_write(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    good_dir = target_base / "america7"
    blocked_dir = target_base / "blocked-show"
    good_dir.mkdir(parents=True)
    blocked_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="Oliviero Bergamini",
        description="America oltre gli stereotipi.",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="",
        artwork_file="cover.jpg",
    )
    outputs.write_program_details(good_dir, details)
    (good_dir / "cover.jpg").write_bytes(b"cover")
    (good_dir / "America7 - 2024-01-01 - one.m4a").write_bytes(b"one")
    (blocked_dir / "Blocked - 2024-01-01 - one.m4a").write_bytes(b"one")

    original_ensure_program_assets = outputs.ensure_program_assets

    def patched_ensure_program_assets(target_dir: Path, slug: str) -> ProgramDetails:
        if target_dir == blocked_dir:
            raise PermissionError("read-only folder")
        return original_ensure_program_assets(target_dir, slug)

    monkeypatch.setattr(outputs, "ensure_program_assets", patched_ensure_program_assets)

    content = outputs.generate_program_index(target_base, "").read_text(encoding="utf-8")

    assert "America7" in content
    assert "blocked-show" not in content


def test_generate_program_index_skips_non_show_folder_without_audio(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    good_dir = target_base / "america7"
    empty_dir = target_base / "notes"
    good_dir.mkdir(parents=True)
    empty_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="Oliviero Bergamini",
        description="America oltre gli stereotipi.",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="",
        artwork_file="cover.jpg",
    )
    outputs.write_program_details(good_dir, details)
    (good_dir / "cover.jpg").write_bytes(b"cover")
    (good_dir / "America7 - 2024-01-01 - one.m4a").write_bytes(b"one")

    content = outputs.generate_program_index(target_base, "").read_text(encoding="utf-8")

    assert "America7" in content
    assert "notes" not in content
    assert not (empty_dir / outputs.PROGRAM_INFO_FILE).exists()


def test_generate_program_index_skips_folder_when_is_dir_raises(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    good_dir = target_base / "america7"
    restricted_dir = target_base / "restricted-show"
    good_dir.mkdir(parents=True)
    restricted_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="Oliviero Bergamini",
        description="America oltre gli stereotipi.",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="",
        artwork_file="cover.jpg",
    )
    outputs.write_program_details(good_dir, details)
    (good_dir / "cover.jpg").write_bytes(b"cover")
    (good_dir / "America7 - 2024-01-01 - one.m4a").write_bytes(b"one")

    original_is_dir = Path.is_dir

    def patched_is_dir(path: Path) -> bool:
        if path == restricted_dir:
            raise PermissionError("restricted folder")
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", patched_is_dir)

    content = outputs.generate_program_index(target_base, "").read_text(encoding="utf-8")

    assert "America7" in content
    assert "restricted-show" not in content


def test_generate_program_index_skips_feed_link_when_feed_exists_check_raises(
    monkeypatch, tmp_path: Path
) -> None:
    target_base = tmp_path / "RaiPlaySound"
    show_dir = target_base / "america7"
    show_dir.mkdir(parents=True)
    monkeypatch.setattr(
        outputs,
        "download_index_icon",
        lambda root: (root / outputs.INDEX_ICON_FILE),
    )
    details = ProgramDetails(
        slug="america7",
        title="America7",
        author="Oliviero Bergamini",
        description="America oltre gli stereotipi.",
        page_url="https://www.raiplaysound.it/programmi/america7",
        image_url="",
        artwork_file="cover.jpg",
    )
    outputs.write_program_details(show_dir, details)
    (show_dir / "cover.jpg").write_bytes(b"cover")
    (show_dir / "America7 - 2024-01-01 - one.m4a").write_bytes(b"one")
    (show_dir / "feed.xml").write_text("<rss></rss>\n", encoding="utf-8")

    original_exists = Path.exists

    def patched_exists(path: Path) -> bool:
        if path == show_dir / "feed.xml":
            raise PermissionError("restricted feed path")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", patched_exists)

    content = outputs.generate_program_index(target_base, "https://example.test/audio").read_text(
        encoding="utf-8"
    )

    assert "America7" in content
    assert "https://example.test/audio/america7/feed.xml" not in content


def test_generate_rss_feed_sorts_items_by_real_publish_date(tmp_path: Path, monkeypatch) -> None:
    target_dir = tmp_path / "musicalbox"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-older\t20231231\t1\tOlder Episode\n" "ep-newer\t20240101\t1\tNewer Episode\n",
        encoding="utf-8",
    )
    (target_dir / "Musical Box - 2023-12-31 - older.m4a").write_bytes(b"old")
    (target_dir / "Musical Box - 2024-01-01 - newer.m4a").write_bytes(b"new")
    monkeypatch.setattr(outputs, "fetch_show_title", lambda _slug: "Musical Box")

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "musicalbox",
        "https://www.raiplaysound.it/programmi/musicalbox",
        metadata_cache_file,
        "",
    )
    content = feed_path.read_text(encoding="utf-8")

    assert content.index("<title>Newer Episode</title>") < content.index(
        "<title>Older Episode</title>"
    )


def test_outputs_match_cache_by_title_when_filename_date_is_shifted(
    tmp_path: Path, monkeypatch
) -> None:
    target_dir = tmp_path / "musicalbox"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-sat\t20260502\tNA\tMusical Box del 02/05/2026\n"
        "ep-sun\t20260503\tNA\tMusical Box del 03/05/2026\n",
        encoding="utf-8",
    )
    (
        target_dir / "Musical Box - 2026-05-03 - Musical Box del 02\u29f805\u29f82026.m4a"
    ).write_bytes(b"sat")
    (
        target_dir / "Musical Box - 2026-05-04 - Musical Box del 03\u29f805\u29f82026.m4a"
    ).write_bytes(b"sun")
    monkeypatch.setattr(outputs, "fetch_show_title", lambda _slug: "Musical Box")

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "musicalbox",
        "https://www.raiplaysound.it/programmi/musicalbox",
        metadata_cache_file,
        "",
    )
    playlist_path = outputs.generate_playlist(target_dir, metadata_cache_file)
    feed_content = feed_path.read_text(encoding="utf-8")
    playlist_content = playlist_path.read_text(encoding="utf-8")

    assert "<title>Musical Box del 02/05/2026</title>" in feed_content
    assert "<title>Musical Box del 03/05/2026</title>" in feed_content
    assert '<guid isPermaLink="false">ep-sat</guid>' in feed_content
    assert '<guid isPermaLink="false">ep-sun</guid>' in feed_content
    assert "Sat, 02 May 2026 00:00:00 GMT" in feed_content
    assert "Sun, 03 May 2026 00:00:00 GMT" in feed_content
    assert "#EXTINF:-1,Musical Box del 02/05/2026" in playlist_content
    assert "#EXTINF:-1,Musical Box del 03/05/2026" in playlist_content


def test_outputs_do_not_match_duplicate_titles_by_name(tmp_path: Path, monkeypatch) -> None:
    target_dir = tmp_path / "show"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-older\t20260502\tNA\tRepeated Title\n" "ep-newer\t20260503\tNA\tRepeated Title\n",
        encoding="utf-8",
    )
    audio = target_dir / "Show - 2026-05-04 - Repeated Title.m4a"
    audio.write_bytes(b"audio")
    monkeypatch.setattr(outputs, "fetch_show_title", lambda _slug: "Show")

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "show",
        "https://www.raiplaysound.it/programmi/show",
        metadata_cache_file,
        "",
    )
    playlist_path = outputs.generate_playlist(target_dir, metadata_cache_file)
    feed_content = feed_path.read_text(encoding="utf-8")
    playlist_content = playlist_path.read_text(encoding="utf-8")

    assert '<guid isPermaLink="false">Show - 2026-05-04 - Repeated Title</guid>' in feed_content
    assert '<guid isPermaLink="false">ep-newer</guid>' not in feed_content
    assert '<guid isPermaLink="false">ep-older</guid>' not in feed_content
    assert "Mon, 04 May 2026 00:00:00 GMT" in feed_content
    assert "#EXTINF:-1,Repeated Title" in playlist_content


def test_outputs_do_not_reuse_one_title_match_for_multiple_local_files(
    tmp_path: Path, monkeypatch
) -> None:
    target_dir = tmp_path / "show"
    target_dir.mkdir()
    metadata_cache_file = target_dir / ".metadata-cache.tsv"
    metadata_cache_file.write_text(
        "ep-single\t20260502\tNA\tRepeated Title\n",
        encoding="utf-8",
    )
    first = target_dir / "Show - 2026-05-04 - Repeated Title.m4a"
    second = target_dir / "Show - 2026-05-05 - Repeated Title.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    monkeypatch.setattr(outputs, "fetch_show_title", lambda _slug: "Show")

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "show",
        "https://www.raiplaysound.it/programmi/show",
        metadata_cache_file,
        "",
    )
    playlist_path = outputs.generate_playlist(target_dir, metadata_cache_file)
    feed_content = feed_path.read_text(encoding="utf-8")
    playlist_content = playlist_path.read_text(encoding="utf-8")

    assert feed_content.count("<item>") == 2
    assert '<guid isPermaLink="false">ep-single</guid>' not in feed_content
    assert f'<guid isPermaLink="false">{first.stem}</guid>' in feed_content
    assert f'<guid isPermaLink="false">{second.stem}</guid>' in feed_content
    assert playlist_content.count("#EXTINF:-1,Repeated Title") == 2


def test_download_index_icon_saves_bundled_apple_touch_icon(monkeypatch, tmp_path: Path) -> None:
    icon_path = outputs.download_index_icon(tmp_path)

    assert icon_path == tmp_path / "apple-touch-icon.png"
    assert icon_path.read_bytes().startswith(b"\x89PNG")
