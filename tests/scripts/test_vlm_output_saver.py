import json
from pathlib import Path

from aih_contexture.scripts.ui.vlm_output_saver import (
    save_vlm_generalized_outputs,
    save_vlm_specialized_outputs,
)


class GeneralizedConverter:
    _last_json_pages = [
        '{"regions": [{"type": "Title", "text": "A"}], "printed_page_number": "i"}',
        "{bad json",
    ]
    _last_json_diagnostics = {"invalid": 1}
    _last_response_metadata = {"model": "test-vlm"}
    _last_clean_html_pages = ["<h1>A</h1>"]


class SpecializedConverter:
    _last_chunks = [[{"label": "Text", "content": "A"}]]
    _last_clean_html_pages = ["<p>A</p>"]
    _last_xml_pages = ["<page>A</page>"]


def test_save_vlm_generalized_outputs_writes_markdown_json_html(tmp_path: Path):
    warnings = []

    output_files = save_vlm_generalized_outputs(
        converter=GeneralizedConverter(),
        markdown_text="{0}\n# A\n{1}",
        output_dir=str(tmp_path),
        fname_base="doc",
        file_name="doc.pdf",
        output_formats=["markdown", "json", "html"],
        warn=warnings.append,
    )

    assert {Path(path).name for path in output_files} == {"doc.md", "doc.json", "doc.html"}
    assert (tmp_path / "doc.md").read_text(encoding="utf-8") == "{0}\n# A\n{1}"
    payload = json.loads((tmp_path / "doc.json").read_text(encoding="utf-8"))
    assert payload["filename"] == "doc.pdf"
    assert payload["format"] == "vlm_generalized"
    assert payload["num_pages"] == 1
    assert payload["pages"][0]["page_index"] == 0
    assert payload["diagnostics"] == {"invalid": 1}
    assert payload["response_metadata"] == {"model": "test-vlm"}
    assert warnings == ["Failed to parse JSON for page 1"]
    assert "<h1>A</h1>" in (tmp_path / "doc.html").read_text(encoding="utf-8")


def test_save_vlm_generalized_outputs_uses_legacy_json_fallback(tmp_path: Path):
    class Converter:
        _last_json_pages = None
        _last_clean_html_pages = None

    save_vlm_generalized_outputs(
        converter=Converter(),
        markdown_text="{0}\nA\n{1}",
        output_dir=str(tmp_path),
        fname_base="doc",
        file_name="doc.pdf",
        output_formats=["json"],
    )

    payload = json.loads((tmp_path / "doc.json").read_text(encoding="utf-8"))
    assert payload == {
        "filename": "doc.pdf",
        "markdown": "{0}\nA\n{1}",
        "format": "vlm_generalized",
        "page_count": 1,
    }


def test_save_vlm_specialized_outputs_writes_official_protocol_artifacts(tmp_path: Path):
    output_files = save_vlm_specialized_outputs(
        converter=SpecializedConverter(),
        markdown_text="{0}\nA\n{1}",
        output_dir=str(tmp_path),
        fname_base="doc",
        file_name="doc.pdf",
        output_formats=["markdown", "json", "html", "xml"],
    )

    assert {Path(path).name for path in output_files} == {
        "doc.md",
        "doc.json",
        "doc.html",
        "doc.xml",
    }
    payload = json.loads((tmp_path / "doc.json").read_text(encoding="utf-8"))
    assert payload["filename"] == "doc.pdf"
    assert payload["format"] == "vlm_specialized"
    assert payload["num_pages"] == 1
    assert payload["pages"] == [[{"label": "Text", "content": "A"}]]
    assert (tmp_path / "doc.xml").read_text(encoding="utf-8") == "<page>A</page>"


def test_save_vlm_specialized_outputs_skips_xml_when_no_xml_pages(tmp_path: Path):
    class Converter:
        _last_chunks = None
        _last_xml_pages = None
        _last_clean_html_pages = None

    output_files = save_vlm_specialized_outputs(
        converter=Converter(),
        markdown_text="{0}\nA\n{1}",
        output_dir=str(tmp_path),
        fname_base="doc",
        file_name="doc.pdf",
        output_formats=["xml", "json"],
    )

    assert {Path(path).name for path in output_files} == {"doc.json"}
    payload = json.loads((tmp_path / "doc.json").read_text(encoding="utf-8"))
    assert payload["markdown"] == "{0}\nA\n{1}"
    assert payload["page_count"] == 1


def test_save_vlm_specialized_outputs_writes_churro_placeholder_xml_pages(tmp_path: Path):
    class Converter:
        _last_chunks = [{"metadata": {"Error": "failed"}, "content": []}]
        _last_xml_pages = ["<Page><Metadata><Error>failed</Error></Metadata><Body/></Page>"]
        _last_clean_html_pages = ["<p></p>"]

    output_files = save_vlm_specialized_outputs(
        converter=Converter(),
        markdown_text="{0}\n\n{1}",
        output_dir=str(tmp_path),
        fname_base="doc",
        file_name="doc.pdf",
        output_formats=["xml", "json"],
    )

    assert {Path(path).name for path in output_files} == {"doc.json", "doc.xml"}
    assert "Error" in (tmp_path / "doc.xml").read_text(encoding="utf-8")
