from pathlib import Path

from aih_contexture.scripts.ui.output_restore import (
    classify_output_file,
    output_file_records,
    scan_output_records_for_restore,
)


def test_classify_output_file_groups_middle_artifacts_under_source_base():
    assert classify_output_file("paper.postprocess_report.json") == ("paper", "postprocess_report")
    assert classify_output_file("paper_middle.json") == ("paper", "middle_json")
    assert classify_output_file("paper_middle_report.json") == ("paper", "middle_report")
    assert classify_output_file("paper_middle_debug.md") == ("paper", "middle_debug")
    assert classify_output_file("paper_middle_scholarly.md") == ("paper", "middle_scholarly")
    assert classify_output_file("paper_middle_scholarly_report.json") == (
        "paper",
        "middle_scholarly_report",
    )


def test_scan_output_records_for_restore_keeps_contexture_outputs_together(tmp_path: Path):
    names = [
        "sample.md",
        "sample.json",
        "sample_chunks.json",
        "sample_meta.json",
        "sample_middle.json",
        "sample_middle_report.json",
        "sample_middle_debug.md",
        "sample_middle_scholarly.md",
        "sample_middle_scholarly_report.json",
        "sample.postprocess_report.json",
        "sample_layout_overlay.pdf",
        "sample_span_overlay.pdf",
        "unrelated.md",
    ]
    for name in names:
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / "sample_layout_overlay").mkdir()

    restored = scan_output_records_for_restore(tmp_path)

    assert set(restored) == {"sample", "unrelated"}
    assert [record["format"] for record in restored["sample"]] == [
        "markdown",
        "json",
        "chunks",
        "meta",
        "middle_json",
        "middle_report",
        "middle_debug",
        "middle_scholarly",
        "middle_scholarly_report",
        "postprocess_report",
        "layout_overlay",
        "span_overlay",
    ]
    assert [record["name"] for record in restored["unrelated"]] == ["unrelated.md"]


def test_output_file_records_ignores_missing_paths(tmp_path: Path):
    existing = tmp_path / "doc_middle.json"
    missing = tmp_path / "missing_middle.json"
    existing.write_text("{}", encoding="utf-8")

    records = output_file_records([existing, missing])

    assert records == [
        {
            "format": "middle_json",
            "path": str(existing),
            "name": "doc_middle.json",
        }
    ]
