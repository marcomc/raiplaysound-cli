from __future__ import annotations

from pathlib import Path

from raiplaysound_cli.repair import apply_filename_repairs, plan_filename_repairs


def test_plan_filename_repairs_uses_metadata_title_and_date(tmp_path: Path) -> None:
    show_dir = tmp_path / "musicalbox"
    show_dir.mkdir()
    metadata_cache = show_dir / ".metadata-cache.tsv"
    metadata_cache.write_text(
        "ep-sat\t20260502\tNA\tMusical Box del 02/05/2026\n"
        "ep-sun\t20260503\tNA\tMusical Box del 03/05/2026\n",
        encoding="utf-8",
    )
    wrong = show_dir / "Musical Box - 2026-05-03 - Musical Box del 02⧸05⧸2026.m4a"
    wrong.write_bytes(b"audio")
    correct = show_dir / "Musical Box - 2026-05-04 - Musical Box del 03⧸05⧸2026.m4a"
    correct.write_bytes(b"audio")

    result = plan_filename_repairs(show_dir, metadata_cache)

    assert [(item.source.name, item.target.name) for item in result.repairs] == [
        (
            "Musical Box - 2026-05-03 - Musical Box del 02⧸05⧸2026.m4a",
            "Musical Box - 2026-05-02 - Musical Box del 02⧸05⧸2026.m4a",
        ),
        (
            "Musical Box - 2026-05-04 - Musical Box del 03⧸05⧸2026.m4a",
            "Musical Box - 2026-05-03 - Musical Box del 03⧸05⧸2026.m4a",
        ),
    ]
    assert result.ambiguous == []
    assert result.conflicts == []


def test_apply_filename_repairs_renames_only_planned_files(tmp_path: Path) -> None:
    show_dir = tmp_path / "musicalbox"
    show_dir.mkdir()
    metadata_cache = show_dir / ".metadata-cache.tsv"
    metadata_cache.write_text(
        "ep-sat\t20260502\tNA\tMusical Box del 02/05/2026\n",
        encoding="utf-8",
    )
    wrong = show_dir / "Musical Box - 2026-05-03 - Musical Box del 02⧸05⧸2026.m4a"
    wrong.write_bytes(b"audio")

    result = plan_filename_repairs(show_dir, metadata_cache)
    apply_filename_repairs(result.repairs)

    assert not wrong.exists()
    assert (
        show_dir / "Musical Box - 2026-05-02 - Musical Box del 02⧸05⧸2026.m4a"
    ).read_bytes() == (b"audio")


def test_plan_filename_repairs_skips_ambiguous_titles(tmp_path: Path) -> None:
    show_dir = tmp_path / "show"
    show_dir.mkdir()
    metadata_cache = show_dir / ".metadata-cache.tsv"
    metadata_cache.write_text(
        "ep-1\t20260502\tNA\tRepeated Title\n" "ep-2\t20260503\tNA\tRepeated Title\n",
        encoding="utf-8",
    )
    audio = show_dir / "Show - 2026-05-04 - Repeated Title.m4a"
    audio.write_bytes(b"audio")

    result = plan_filename_repairs(show_dir, metadata_cache)

    assert result.repairs == []
    assert result.ambiguous == [audio]


def test_plan_filename_repairs_falls_back_to_date_in_title_when_cache_is_partial(
    tmp_path: Path,
) -> None:
    show_dir = tmp_path / "musicalbox"
    show_dir.mkdir()
    metadata_cache = show_dir / ".metadata-cache.tsv"
    metadata_cache.write_text("", encoding="utf-8")
    wrong = show_dir / "Musical Box - 2026-04-13 - Musical Box del 12⧸04⧸2026.m4a"
    wrong.write_bytes(b"audio")

    result = plan_filename_repairs(show_dir, metadata_cache)

    assert [(item.source.name, item.target.name) for item in result.repairs] == [
        (
            "Musical Box - 2026-04-13 - Musical Box del 12⧸04⧸2026.m4a",
            "Musical Box - 2026-04-12 - Musical Box del 12⧸04⧸2026.m4a",
        )
    ]
