import json

from click.testing import CliRunner

from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan
from aih_contexture.scripts.visualize_layout import visualize_layout_cli


def test_visualize_layout_cli_writes_overlay_files(tmp_path):
    middle_path = tmp_path / "sample_middle.json"
    output_dir = tmp_path / "overlay"
    output_pdf = tmp_path / "overlay.pdf"
    payload = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=100,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        bbox=[10, 10, 90, 50],
                        spans=[
                            MiddleSpan(
                                text="hello",
                                bbox=[12, 14, 42, 24],
                                provenance=[MiddleProvenance(backend="surya", stage="span")],
                            )
                        ],
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    )
                ],
            )
        ]
    ).to_dict()
    middle_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        visualize_layout_cli,
        [
            str(middle_path),
            "--output-dir",
            str(output_dir),
            "--output-pdf",
            str(output_pdf),
            "--dpi",
            "72",
        ],
    )

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["ok"] is True
    assert (output_dir / "page_0000_layout_overlay.png").exists()
    assert output_pdf.exists()


def test_visualize_layout_cli_can_write_span_overlay(tmp_path):
    middle_path = tmp_path / "sample_middle.json"
    output_dir = tmp_path / "span"
    output_pdf = tmp_path / "span.pdf"
    payload = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=100,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        bbox=[10, 10, 90, 50],
                        spans=[
                            MiddleSpan(
                                text="hello",
                                bbox=[12, 14, 42, 24],
                                provenance=[MiddleProvenance(backend="surya", stage="span")],
                            )
                        ],
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    )
                ],
            )
        ]
    ).to_dict()
    middle_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        visualize_layout_cli,
        [
            str(middle_path),
            "--kind",
            "span",
            "--output-dir",
            str(output_dir),
            "--output-pdf",
            str(output_pdf),
            "--dpi",
            "72",
        ],
    )

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["ok"] is True
    assert report["span_count"] == 1
    assert (output_dir / "page_0000_span_overlay.png").exists()
    assert output_pdf.exists()


def test_visualize_layout_cli_can_write_review_crops(tmp_path):
    middle_path = tmp_path / "sample_middle.json"
    output_dir = tmp_path / "review"
    payload = MiddleDocument(
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=100,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="ComplexRegion",
                        page_index=0,
                        order=0,
                        bbox=[5, 5, 12, 12],
                        provenance=[MiddleProvenance(backend="paddle", stage="layout")],
                    )
                ],
            )
        ]
    ).to_dict()
    middle_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        visualize_layout_cli,
        [
            str(middle_path),
            "--kind",
            "review",
            "--output-dir",
            str(output_dir),
            "--dpi",
            "72",
        ],
    )

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["ok"] is True
    assert report["crop_count"] == 1
    assert (output_dir / "review_crops.json").exists()
    assert (output_dir / "page_0000_block_0000_ComplexRegion_review.png").exists()
