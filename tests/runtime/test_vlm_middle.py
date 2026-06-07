import os
import uuid

from aih_contexture.runtime.vlm_middle import (
    middle_json_from_vlm_generalized_converter,
    middle_json_from_vlm_specialized_converter,
    save_vlm_middle_artifacts_for_converter,
)


class DummyGeneralizedConverter:
    config = {}
    model = "dummy-vlm"
    _last_json_pages = [
        """{
            "printed_page_number": "1",
            "page_width": 100,
            "page_height": 120,
            "regions": [
                {"label": "Text", "bbox": [0, 0, 80, 40], "text": "Generalized"}
            ]
        }"""
    ]


class DummyFilteredGeneralizedConverter:
    config = {"vlm_filter_page_header": True, "vlm_filter_page_footer": True, "vlm_filter_margin_notes": True}
    model = "dummy-vlm"
    _last_json_pages = [
        """{
            "page_width": 100,
            "page_height": 120,
            "regions": [
                {"label": "PageHeader", "bbox": [0, 0, 80, 10], "text": "Header"},
                {"label": "Marginal-Note-Left", "bbox": [0, 20, 10, 40], "text": "Side note"},
                {"label": "Text", "bbox": [0, 20, 80, 40], "text": "Body"},
                {"label": "PageFooter", "bbox": [0, 100, 80, 120], "text": "Footer"}
            ]
        }"""
    ]


class DummySpecializedConverter:
    backend = "chandra"
    model = "chandra-2"
    filter_page_header = False
    filter_page_footer = False
    _last_printed_pages = ["2"]
    _last_chunks = [
        {
            "page_num": 0,
            "img_size": [100, 120],
            "chunks": [
                {"label": "Text", "bbox": [0, 0, 80, 40], "content": "<p>Specialized</p>"}
            ],
        }
    ]


class DummyFilteredSpecializedConverter:
    backend = "churro"
    model = "churro-3b"
    filter_page_header = False
    filter_page_footer = False
    filter_margin_notes = True
    _last_printed_pages = ["2"]
    _last_chunks = [
        {
            "content": [
                {
                    "page_number": "2",
                    "elements": [
                        {"type": "marginal_note", "placement": "left_margin", "text": "Side note"},
                        {"type": "paragraph", "text": "Body"},
                    ],
                }
            ]
        }
    ]


def _workspace_tmp_dir(name: str) -> str:
    path = os.path.join(os.getcwd(), ".codex_tmp_test_vlm_middle", f"{name}-{uuid.uuid4().hex}")
    os.makedirs(path, exist_ok=True)
    return path


def test_vlm_middle_helper_builds_generalized_middle_json():
    data = middle_json_from_vlm_generalized_converter(
        DummyGeneralizedConverter(),
        source_name="sample.pdf",
        source="sample.pdf",
    )

    assert data["backends"]["vlm"] == "vlm_generalized"
    assert data["pages"][0]["blocks"][0]["text"] == "Generalized"


def test_vlm_middle_helper_builds_specialized_middle_json():
    data = middle_json_from_vlm_specialized_converter(
        DummySpecializedConverter(),
        source_name="sample.pdf",
        source="sample.pdf",
    )

    assert data["backends"]["vlm_specialized"] == "chandra"
    assert data["pages"][0]["printed_page"] == "2"
    assert data["pages"][0]["blocks"][0]["text"] == "Specialized"


def test_save_vlm_middle_artifacts_for_converter_writes_core_file_by_default():
    out_dir = _workspace_tmp_dir("core")
    outputs = save_vlm_middle_artifacts_for_converter(
        DummyGeneralizedConverter(),
        mode="vlm_generalized",
        output_dir=out_dir,
        fname_base="sample",
        source_name="sample.pdf",
        source="sample.pdf",
    )

    assert os.path.exists(outputs["middle_json_path"])
    assert set(outputs) == {"middle_json_path"}


def test_save_vlm_middle_artifacts_for_converter_writes_derived_files_when_enabled():
    out_dir = _workspace_tmp_dir("derived")
    outputs = save_vlm_middle_artifacts_for_converter(
        DummyGeneralizedConverter(),
        mode="vlm_generalized",
        output_dir=out_dir,
        fname_base="sample",
        source_name="sample.pdf",
        source="sample.pdf",
        emit_middle_report=True,
        emit_middle_debug=True,
        emit_middle_scholarly=True,
        emit_middle_scholarly_report=True,
    )

    assert os.path.exists(outputs["middle_json_path"])
    assert os.path.exists(outputs["middle_report_path"])
    assert os.path.exists(outputs["middle_debug_path"])
    assert os.path.exists(outputs["middle_scholarly_path"])
    assert os.path.exists(outputs["middle_scholarly_report_path"])


def test_save_vlm_middle_artifacts_respects_generalized_page_marker_filters():
    out_dir = _workspace_tmp_dir("generalized-filter")
    outputs = save_vlm_middle_artifacts_for_converter(
        DummyFilteredGeneralizedConverter(),
        mode="vlm_generalized",
        output_dir=out_dir,
        fname_base="sample",
        source_name="sample.pdf",
        source="sample.pdf",
        emit_middle_scholarly=True,
    )

    scholarly = open(outputs["middle_scholarly_path"], encoding="utf-8").read()
    assert "<!-- PageHeader:" not in scholarly
    assert "<!-- PageFooter:" not in scholarly
    assert "<!-- Margin:" not in scholarly
    assert "> Side note" not in scholarly
    assert "Side note" in scholarly
    assert "Body" in scholarly


def test_save_vlm_middle_artifacts_respects_specialized_margin_filter():
    out_dir = _workspace_tmp_dir("specialized-margin")
    outputs = save_vlm_middle_artifacts_for_converter(
        DummyFilteredSpecializedConverter(),
        mode="vlm_specialized",
        output_dir=out_dir,
        fname_base="sample",
        source_name="sample.pdf",
        source="sample.pdf",
        emit_middle_scholarly=True,
    )

    scholarly = open(outputs["middle_scholarly_path"], encoding="utf-8").read()
    assert "<!-- Margin:" not in scholarly
    assert "> Side note" not in scholarly
    assert "Side note" in scholarly
    assert "Body" in scholarly
