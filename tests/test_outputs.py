from __future__ import annotations

from pathlib import Path

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
    assert "file://" not in feed_content
    assert "#EXTINF:-1,file-one" in playlist_content
    assert "#EXTINF:-1,file-two" in playlist_content


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
    assert "Oliviero Bergamini" in content
    assert "1 episodi" in content
    assert "Ultimo: 2024-01-01" in content
    assert "america7/cover.jpg" in content
    assert "https://example.test/audio" not in content
    assert "feed.xml" not in content

    (show_dir / "feed.xml").write_text("<rss></rss>\n", encoding="utf-8")

    content = outputs.generate_program_index(target_base, "https://example.test/audio").read_text(
        encoding="utf-8"
    )

    assert '<a class="feed" href="https://example.test/audio/america7/feed.xml">RSS</a>' in content
    assert "america7/cover.jpg" in content


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


def test_download_index_icon_saves_apple_touch_icon(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(outputs, "http_get_bytes", lambda *_args, **_kwargs: (b"png", "image/png"))

    icon_path = outputs.download_index_icon(tmp_path)

    assert icon_path == tmp_path / "apple-touch-icon.png"
    assert icon_path.read_bytes() == b"png"
