from __future__ import annotations

from pathlib import Path

from raiplaysound_cli import outputs


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

    feed_path = outputs.generate_rss_feed(
        target_dir,
        "america7",
        "https://www.raiplaysound.it/programmi/america7",
        metadata_cache_file,
        "https://example.test/audio",
    )
    content = feed_path.read_text(encoding="utf-8")

    assert feed_path == target_dir / "feed.xml"
    assert "<title>America &amp; Seven</title>" in content
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
