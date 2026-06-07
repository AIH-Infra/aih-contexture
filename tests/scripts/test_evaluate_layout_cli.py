import json

from click.testing import CliRunner

from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance
from aih_contexture.scripts.evaluate_layout import evaluate_layout_cli


def _write_middle(path):
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
                        bbox=[0, 0, 100, 50],
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    )
                ],
            )
        ]
    ).to_dict()
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evaluate_layout_cli_writes_report(tmp_path):
    middle_path = tmp_path / "sample_middle.json"
    report_path = tmp_path / "layout_eval.json"
    _write_middle(middle_path)

    result = CliRunner().invoke(
        evaluate_layout_cli,
        [
            str(middle_path),
            "--require-block-type",
            "Text",
            "--output",
            str(report_path),
            "--strict",
        ],
    )

    assert result.exit_code == 0
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["results"][0]["metrics"]["block_types"] == {"Text": 1}


def test_evaluate_layout_cli_strict_fails_for_missing_required_type(tmp_path):
    middle_path = tmp_path / "sample_middle.json"
    _write_middle(middle_path)

    result = CliRunner().invoke(
        evaluate_layout_cli,
        [str(middle_path), "--require-block-type", "Table", "--strict"],
    )

    assert result.exit_code != 0
    assert "Layout Middle evaluation failed" in result.output


def test_evaluate_layout_cli_accepts_manifest(tmp_path):
    middle_path = tmp_path / "sample_middle.json"
    manifest_path = tmp_path / "manifest.json"
    _write_middle(middle_path)
    manifest_path.write_text(
        json.dumps(
            {
                "name": "smoke-layout",
                "cases": [
                    {
                        "id": "case-1",
                        "path": "sample_middle.json",
                        "backend": "external_layout_sidecar",
                        "required_block_types": ["Text"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(evaluate_layout_cli, ["--manifest", str(manifest_path), "--strict"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["results"][0]["case"]["id"] == "case-1"
