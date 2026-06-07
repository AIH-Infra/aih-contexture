import json

from click.testing import CliRunner

from aih_contexture.scripts import download_layout_smoke as module
from aih_contexture.scripts.download_layout_smoke import download_layout_smoke_cli


def test_download_layout_smoke_cli_writes_manifest_without_redownloading(tmp_path, monkeypatch):
    sources_path = tmp_path / "sources.json"
    existing_pdf = tmp_path / "downloads" / "sample.pdf"
    existing_pdf.parent.mkdir()
    existing_pdf.write_bytes(b"%PDF-1.4\n")
    sources_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "sample",
                        "url": "https://example.test/sample.pdf",
                        "filename": "sample.pdf",
                        "document_type": "modern_pdf",
                        "backend_targets": ["surya"],
                        "required_block_types": ["Text"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fail_download(*args, **kwargs):
        raise AssertionError("existing PDFs should not be downloaded without --force")

    monkeypatch.setattr(module, "_download", fail_download)

    result = CliRunner().invoke(
        download_layout_smoke_cli,
        [
            "--sources",
            str(sources_path),
            "--output-dir",
            str(existing_pdf.parent),
        ],
    )

    assert result.exit_code == 0
    manifest_path = tmp_path / "downloaded_layout_manifest.template.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["cases"][0]["id"] == "sample"
    assert payload["cases"][0]["required_block_types"] == ["Text"]
