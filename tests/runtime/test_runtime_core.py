import json
import os
import tempfile

import pytest

from aih_contexture.runtime import runner
from aih_contexture.runtime.artifacts import save_contexture_result
from aih_contexture.runtime.config_builder import config_from_ui_params
from aih_contexture.runtime.errors import ContextureConfigError
from aih_contexture.runtime.job import ContextureJob
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance
from aih_contexture.schema.blocks import Text
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.templates.template import DocumentTemplate, LayoutTemplateConfig


def test_contexture_job_normalizes_aliases_and_page_range():
    job = ContextureJob.from_dict(
        {
            "filepath": "sample.pdf",
            "conversion_mode": "pipeline",
            "output_format": "markdown",
            "page_range": "0-2,4",
            "config": {},
        }
    )

    assert job.input_path == "sample.pdf"
    assert job.mode == "pipeline"
    assert job.output_formats == ["markdown"]
    assert job.page_range == [0, 1, 2, 4]
    assert job.config["page_range"] == [0, 1, 2, 4]


def test_materialized_input_path_cleans_temp_file():
    job = ContextureJob(input_bytes=b"%PDF-1.4\n", input_name="sample.pdf")

    with runner._materialized_input_path(job) as input_path:
        assert input_path.endswith(".pdf")
        assert os.path.exists(input_path)
        with open(input_path, "rb") as f:
            assert f.read() == b"%PDF-1.4\n"

    assert not os.path.exists(input_path)


def test_run_job_rejects_office_mode_as_planned_unsupported_runtime_mode(tmp_path):
    input_path = tmp_path / "sample.txt"
    input_path.write_text("office input", encoding="utf-8")

    with pytest.raises(ContextureConfigError, match="Unsupported runtime mode: office"):
        runner.run_job(ContextureJob(input_path=str(input_path), mode="office"))


def test_run_job_uses_configured_converter_and_preserves_page_count(monkeypatch):
    class DummyConverter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.page_count = 5

        def __call__(self, input_path):
            assert input_path == "sample.pdf"
            return "converted"

    class DummyConfigParser:
        def __init__(self, options):
            self.options = options

        def generate_config_dict(self):
            return dict(self.options)

        def get_converter_cls(self):
            return DummyConverter

        def get_processors(self):
            return None

        def get_renderer(self):
            return "aih_contexture.renderers.markdown.MarkdownRenderer"

        def get_llm_service(self):
            return None

    monkeypatch.setattr(runner, "ConfigParser", DummyConfigParser)

    result = runner.run_job(
        ContextureJob(input_path="sample.pdf", mode="pipeline", output_formats=["markdown"]),
        artifact_dict={"model": "stub"},
    )

    assert result.markdown == "converted"
    assert result.page_count == 5


def test_run_job_can_emit_middle_json_from_pipeline_document(monkeypatch):
    class DummyConverter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.page_count = 1
            self.last_document = None

        def __call__(self, input_path):
            page = PageGroup(
                page_id=0,
                polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
                children=[],
            )
            block = Text(
                polygon=PolygonBox.from_bbox([10, 20, 90, 60]),
                block_id=0,
                page_id=0,
            )
            page.add_child(block)
            page.add_structure(block)
            self.last_document = Document(filepath=input_path, pages=[page])
            return "converted"

    class DummyConfigParser:
        def __init__(self, options):
            self.options = options

        def generate_config_dict(self):
            return dict(self.options)

        def get_converter_cls(self):
            return DummyConverter

        def get_processors(self):
            return None

        def get_renderer(self):
            return "aih_contexture.renderers.markdown.MarkdownRenderer"

        def get_llm_service(self):
            return None

    monkeypatch.setattr(runner, "ConfigParser", DummyConfigParser)

    result = runner.run_job(
        ContextureJob(
            input_path="sample.pdf",
            mode="pipeline",
            output_formats=["markdown"],
            config={"emit_middle_json": True, "layout_backend": "surya", "ocr_backend": "calamari"},
        ),
        artifact_dict={"model": "stub"},
    )

    assert result.markdown == "converted"
    assert result.middle_json["schema_version"] == "contexture-middle-json/0.1"
    assert result.middle_json["backends"] == {"layout": "surya", "ocr": "calamari"}
    assert result.middle_json["pages"][0]["blocks"][0]["type"] == "Text"


def test_run_job_can_emit_middle_json_from_vlm_json_pages(monkeypatch):
    class DummyVlmConverter:
        def __init__(self, config):
            self.config = config
            self.page_count = 1
            self.model = "dummy-vlm"
            self._last_json_pages = None

        def __call__(self, input_path):
            assert input_path == "sample.pdf"
            self._last_json_pages = [
                """{
                    "printed_page_number": "7",
                    "page_width": 100,
                    "page_height": 200,
                    "regions": [
                        {"label": "Page-Header", "bbox": [0, 0, 100, 10], "text": "Header"},
                        {"label": "Text", "bbox": [0, 20, 100, 50], "text": "Hello VLM"}
                    ]
                }"""
            ]
            return "converted"

    monkeypatch.setattr(runner, "VlmDirectAsyncConverter", DummyVlmConverter)

    result = runner.run_job(
        ContextureJob(
            input_path="sample.pdf",
            mode="vlm_generalized",
            output_formats=["markdown"],
            config={"emit_middle_json": True, "emit_span_overlay": True},
        )
    )

    assert result.markdown == "converted"
    assert result.middle_json["schema_version"] == "contexture-middle-json/0.1"
    assert result.middle_json["backends"] == {"vlm": "vlm_generalized", "vlm_model": "dummy-vlm"}
    assert result.middle_json["pages"][0]["printed_page"] == "7"
    assert [block["type"] for block in result.middle_json["pages"][0]["blocks"]] == ["PageHeader", "Text"]
    assert result.middle_json["pages"][0]["blocks"][1]["spans"][0]["text"] == "Hello VLM"
    assert result.debug_artifacts["emit_span_overlay"] is True


def test_run_job_skips_vlm_middle_json_when_converter_has_no_json_pages(monkeypatch):
    class DummyVlmConverter:
        def __init__(self, config):
            self.page_count = 1
            self.model = "dummy-vlm"
            self._last_json_pages = None

        def __call__(self, input_path):
            return "markdown only"

    monkeypatch.setattr(runner, "VlmDirectAsyncConverter", DummyVlmConverter)

    result = runner.run_job(
        ContextureJob(
            input_path="sample.pdf",
            mode="vlm_generalized",
            output_formats=["markdown"],
            config={"emit_middle_json": True},
        )
    )

    assert result.markdown == "markdown only"
    assert result.middle_json is None


def test_run_job_can_emit_middle_json_from_specialized_chandra_chunks(monkeypatch):
    class DummyOcrConverter:
        def __init__(self, config):
            self.backend = "chandra"
            self.model = "chandra-2"
            self.page_count = 1
            self._last_chunks = None
            self._last_printed_pages = None

        def __call__(self, input_path):
            self._last_printed_pages = ["3"]
            self._last_chunks = [
                {
                    "page_num": 0,
                    "img_size": [100, 200],
                    "chunks": [
                        {"label": "Text", "bbox": [0, 20, 100, 60], "content": "<p>Official chunks</p>"}
                    ],
                }
            ]
            return "converted"

    monkeypatch.setattr(runner, "OcrDirectAsyncConverter", DummyOcrConverter)

    result = runner.run_job(
        ContextureJob(
            input_path="sample.pdf",
            mode="vlm_specialized",
            output_formats=["markdown"],
            config={"emit_middle_json": True},
        )
    )

    assert result.middle_json["backends"] == {"vlm_specialized": "chandra", "vlm_specialized_model": "chandra-2"}
    assert result.middle_json["pages"][0]["printed_page"] == "3"
    assert result.middle_json["pages"][0]["blocks"][0]["text"] == "Official chunks"


def test_run_job_supports_markdown_postprocess_for_markdown_inputs(monkeypatch, tmp_path):
    class DummyPostprocessResult:
        def __init__(self, markdown):
            self.markdown = f"{markdown} [processed]"

        def summary(self):
            return {"status": "applied", "action_count": 1, "changed": True}

    class DummyPostprocessEngine:
        def __init__(self, config):
            self.config = config
            self.seen = None

        def process(self, markdown):
            self.seen = markdown
            return DummyPostprocessResult(markdown)

    monkeypatch.setattr(runner, "MarkdownPostprocessEngine", DummyPostprocessEngine)

    input_path = tmp_path / "note.md"
    input_path.write_text("# Title\n", encoding="utf-8")

    result = runner.run_job(
        ContextureJob(
            input_path=str(input_path),
            mode="markdown_postprocess",
            output_formats=["markdown"],
            config={
                "markdown_postprocess_enabled": True,
                "markdown_postprocess_review_only": False,
            },
        )
    )

    assert result.markdown == "# Title\n [processed]"
    assert result.page_count == 1
    assert result.metadata["markdown_postprocess"]["input_kind"] == "markdown"
    assert result.metadata["markdown_postprocess"]["status"] == "applied"


def test_run_job_supports_markdown_postprocess_for_middle_json_inputs(monkeypatch, tmp_path):
    class DummyPostprocessResult:
        def __init__(self, markdown):
            self.markdown = f"{markdown}\n[processed]"

        def summary(self):
            return {"status": "applied", "action_count": 2, "changed": True}

    class DummyPostprocessEngine:
        def __init__(self, config):
            self.config = config
            self.seen = None

        def process(self, markdown):
            self.seen = markdown
            return DummyPostprocessResult(markdown)

    monkeypatch.setattr(runner, "MarkdownPostprocessEngine", DummyPostprocessEngine)

    input_path = tmp_path / "doc_middle.json"
    middle_json = MiddleDocument(
        source_name="doc.pdf",
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=200,
                printed_page="7",
                blocks=[
                    MiddleBlock(
                        id="b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        bbox=[0, 0, 80, 40],
                        text="Hello middle",
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    ),
                    MiddleBlock(
                        id="m0",
                        type="MarginalNote",
                        page_index=0,
                        order=1,
                        bbox=[0, 50, 20, 90],
                        text="Side note",
                        attrs={"side": "left"},
                    )
                ],
            )
        ],
    ).to_dict()
    input_path.write_text(json.dumps(middle_json, ensure_ascii=False, indent=2), encoding="utf-8")

    result = runner.run_job(
        ContextureJob(
            input_path=str(input_path),
            mode="markdown_postprocess",
            output_formats=["markdown"],
            config={
                "markdown_postprocess_enabled": True,
                "markdown_postprocess_input_kind": "middle_json",
                "middle_rerender_include_provenance": True,
                "middle_rerender_include_printed_page_comments": False,
                "middle_rerender_include_margin_comments": False,
            },
        )
    )

    assert "Hello middle" in result.markdown
    assert "<!-- Page: 7 -->" not in result.markdown
    assert "<!-- Margin:" not in result.markdown
    assert "> Side note" not in result.markdown
    assert "Side note" in result.markdown
    assert result.markdown.endswith("[processed]")
    assert result.page_count == 1
    assert result.middle_json["schema_version"] == "contexture-middle-json/0.1"
    assert result.metadata["markdown_postprocess"]["input_kind"] == "middle_json"
    assert result.metadata["middle_validation"]["ok"] is True


def test_run_job_supports_markdown_postprocess_for_mineru_official_json_inputs(monkeypatch, tmp_path):
    class DummyPostprocessResult:
        def __init__(self, markdown):
            self.markdown = f"{markdown}\n[processed]"

        def summary(self):
            return {"status": "applied", "action_count": 1, "changed": True}

    class DummyPostprocessEngine:
        def __init__(self, config):
            self.config = config

        def process(self, markdown):
            return DummyPostprocessResult(markdown)

    monkeypatch.setattr(runner, "MarkdownPostprocessEngine", DummyPostprocessEngine)

    input_path = tmp_path / "paper_content_list.json"
    input_path.write_text(
        json.dumps(
            [
                {"type": "text", "text": "Imported Title", "text_level": 1, "bbox": [10, 20, 900, 80], "page_idx": 0},
                {"type": "text", "text": "Imported body", "bbox": [10, 100, 900, 180], "page_idx": 0},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.run_job(
        ContextureJob(
            input_path=str(input_path),
            mode="markdown_postprocess",
            output_formats=["markdown"],
            config={
                "markdown_postprocess_enabled": True,
                "markdown_postprocess_input_kind": "mineru_json",
            },
        )
    )

    assert "# Imported Title" in result.markdown
    assert result.middle_json["metadata"]["import_source"] == "mineru_official_json"
    assert result.metadata["markdown_postprocess"]["input_kind"] == "mineru_json"
    assert result.metadata["middle_validation"]["ok"] is True


def test_save_contexture_result_writes_core_middle_json_when_present():
    out_dir = tempfile.mkdtemp()
    result = runner.ContextureResult(
        markdown="converted",
        middle_json={"schema_version": "contexture-middle-json/0.1", "pages": []},
    )

    output = save_contexture_result(result, out_dir, "sample", "markdown")

    middle_path = os.path.join(out_dir, "sample_middle.json")
    assert os.path.exists(middle_path)
    assert not os.path.exists(os.path.join(out_dir, "sample_middle_report.json"))
    assert not os.path.exists(os.path.join(out_dir, "sample_middle_debug.md"))
    assert not os.path.exists(os.path.join(out_dir, "sample_middle_scholarly.md"))
    assert not os.path.exists(os.path.join(out_dir, "sample_middle_scholarly_report.json"))
    assert output["middle_json_path"] == middle_path
    assert set(output) >= {"format", "path", "name", "middle_json_path"}
    assert "middle_report_path" not in output


def test_save_contexture_result_writes_middle_derived_artifacts_when_enabled():
    out_dir = tempfile.mkdtemp()
    result = runner.ContextureResult(
        markdown="converted",
        middle_json={"schema_version": "contexture-middle-json/0.1", "pages": []},
        debug_artifacts={
            "emit_middle_report": True,
            "emit_middle_debug": True,
            "emit_middle_scholarly": True,
            "emit_middle_scholarly_report": True,
        },
    )

    output = save_contexture_result(result, out_dir, "sample", "markdown")

    report_path = os.path.join(out_dir, "sample_middle_report.json")
    debug_path = os.path.join(out_dir, "sample_middle_debug.md")
    scholarly_path = os.path.join(out_dir, "sample_middle_scholarly.md")
    scholarly_report_path = os.path.join(out_dir, "sample_middle_scholarly_report.json")
    assert os.path.exists(report_path)
    assert os.path.exists(debug_path)
    assert os.path.exists(scholarly_path)
    assert os.path.exists(scholarly_report_path)
    assert output["middle_report_path"] == report_path
    assert output["middle_debug_path"] == debug_path
    assert output["middle_scholarly_path"] == scholarly_path
    assert output["middle_scholarly_report_path"] == scholarly_report_path


def test_save_contexture_result_can_filter_middle_scholarly_page_comments():
    out_dir = tempfile.mkdtemp(dir=os.getcwd())
    result = runner.ContextureResult(
        markdown="converted",
        middle_json={
            "schema_version": "contexture-middle-json/0.1",
            "pages": [
                {
                    "index": 0,
                    "printed_page": "7",
                    "blocks": [
                        {"id": "h", "type": "PageHeader", "page_index": 0, "order": 0, "text": "Header"},
                        {"id": "t", "type": "Text", "page_index": 0, "order": 1, "text": "Body"},
                        {"id": "f", "type": "PageFooter", "page_index": 0, "order": 2, "text": "Footer"},
                    ],
                }
            ],
        },
        debug_artifacts={
            "emit_middle_scholarly": True,
            "include_printed_page_comments": False,
            "include_page_header_comments": False,
            "include_page_footer_comments": False,
        },
    )

    output = save_contexture_result(result, out_dir, "sample", "markdown")
    scholarly = open(output["middle_scholarly_path"], encoding="utf-8").read()

    assert "<!-- Page:" not in scholarly
    assert "<!-- PageHeader:" not in scholarly
    assert "<!-- PageFooter:" not in scholarly
    assert "Body" in scholarly


def test_middle_debug_artifact_flags_include_margin_comments():
    result = runner.ContextureResult()

    runner._copy_middle_debug_artifact_flags(
        {
            "include_page_header_comments": False,
            "include_page_footer_comments": False,
            "include_margin_comments": False,
        },
        result,
    )

    assert result.debug_artifacts["include_page_header_comments"] is False
    assert result.debug_artifacts["include_page_footer_comments"] is False
    assert result.debug_artifacts["include_margin_comments"] is False


def test_save_contexture_result_can_write_layout_overlay_artifacts():
    out_dir = tempfile.mkdtemp()
    result = runner.ContextureResult(
        markdown="converted",
        middle_json={
            "schema_version": "contexture-middle-json/0.1",
            "pages": [
                {
                    "index": 0,
                    "width": 100,
                    "height": 100,
                    "blocks": [
                        {
                            "id": "p0-b0",
                            "type": "Text",
                            "page_index": 0,
                            "order": 0,
                            "bbox": [10, 10, 90, 50],
                            "provenance": [{"backend": "surya", "stage": "layout"}],
                        }
                    ],
                }
            ],
        },
        debug_artifacts={"emit_layout_overlay": True},
    )

    output = save_contexture_result(result, out_dir, "sample", "markdown")

    assert os.path.isdir(os.path.join(out_dir, "sample_layout_overlay"))
    assert os.path.exists(os.path.join(out_dir, "sample_layout_overlay.pdf"))
    assert output["layout_overlay_dir"] == os.path.join(out_dir, "sample_layout_overlay")
    assert output["layout_overlay_pdf_path"] == os.path.join(out_dir, "sample_layout_overlay.pdf")


def test_save_contexture_result_can_write_span_overlay_artifacts():
    out_dir = tempfile.mkdtemp()
    result = runner.ContextureResult(
        markdown="converted",
        middle_json={
            "schema_version": "contexture-middle-json/0.1",
            "pages": [
                {
                    "index": 0,
                    "width": 100,
                    "height": 100,
                    "blocks": [
                        {
                            "id": "p0-b0",
                            "type": "Text",
                            "page_index": 0,
                            "order": 0,
                            "bbox": [10, 10, 90, 50],
                            "spans": [
                                {
                                    "text": "hello",
                                    "bbox": [12, 14, 42, 24],
                                    "provenance": [{"backend": "surya", "stage": "span"}],
                                }
                            ],
                            "provenance": [{"backend": "surya", "stage": "layout"}],
                        }
                    ],
                }
            ],
        },
        debug_artifacts={"emit_span_overlay": True},
    )

    output = save_contexture_result(result, out_dir, "sample", "markdown")

    assert os.path.isdir(os.path.join(out_dir, "sample_span_overlay"))
    assert os.path.exists(os.path.join(out_dir, "sample_span_overlay.pdf"))
    assert output["span_overlay_dir"] == os.path.join(out_dir, "sample_span_overlay")
    assert output["span_overlay_pdf_path"] == os.path.join(out_dir, "sample_span_overlay.pdf")


def test_removed_yolo_layout_backend_is_rejected():
    try:
        config_from_ui_params(
            {"conversion_mode": "pipeline", "layout_backend": "yolo", "ocr_backend": "none"}
        )
    except ValueError as exc:
        assert "yolo" in str(exc).lower()
    else:
        raise AssertionError("layout_backend='yolo' should be rejected")

    template = DocumentTemplate(name="legacy", layout=LayoutTemplateConfig(layout_backend="yolo"))
    try:
        template.to_config_dict()
    except ValueError as exc:
        assert "yolo" in str(exc).lower()
    else:
        raise AssertionError("template layout_backend='yolo' should be rejected")
