import json
from pathlib import Path

from PIL import Image

from aih_contexture.converters.vlm_direct_async import PageResult, VlmDirectAsyncConverter
from aih_contexture.runtime.vlm_repair import (
    extract_failed_pages,
    merge_repaired_pages,
    page_jsons_to_page_results,
    rerender_vlm_json,
)


def test_extract_failed_pages_uses_diagnostics_and_error_pages():
    data = {
        "format": "vlm_generalized",
        "pages": [
            {"page_number": 1, "regions": [{"label": "Text", "text": "ok"}]},
            {"page_number": 2, "error": "retry_exhausted", "regions": [], "diagnostic": {"ok": False, "content_kind": "none"}},
            {"page_number": 3, "regions": []},
        ],
        "diagnostics": [
            {"page_number": 1, "ok": True, "content_kind": "json"},
            {"page_number": 3, "ok": False, "content_kind": "none"},
        ],
    }

    assert extract_failed_pages(data) == [2, 3]


def test_page_jsons_to_page_results_and_merge_preserve_absolute_page_numbers():
    data = {
        "format": "vlm_generalized",
        "pages": [
            {"page_number": 1, "regions": [{"label": "Text", "text": "one"}]},
            {"page_number": 2, "error": "retry_exhausted", "regions": []},
        ],
        "diagnostics": [
            {"page_number": 1, "ok": True, "content_kind": "json", "error_kind": "none"},
            {"page_number": 2, "ok": False, "content_kind": "none", "error_kind": "retry_exhausted"},
        ],
    }

    original = page_jsons_to_page_results(data)
    repaired = PageResult(
        page_num=2,
        ok=True,
        raw_text='{"page_number": 2, "regions": [{"label": "Text", "text": "two"}]}',
        cleaned_text='{"page_number": 2, "regions": [{"label": "Text", "text": "two"}]}',
        content_kind="json",
        error_kind="none",
    )

    merged = merge_repaired_pages(original, [repaired])

    assert [result.page_num for result in merged] == [1, 2]
    assert merged[1].ok is True
    assert json.loads(merged[1].cleaned_text)["page_number"] == 2


class FakeProvider:
    def get_images(self, indices, dpi):
        return [Image.new("RGB", (4, 4), "white") for _ in indices]


def test_sparse_page_conversion_preserves_logical_page_numbers(monkeypatch):
    converter = VlmDirectAsyncConverter(
        {
            "vlm_api_provider": "openai_compatible",
            "vlm_direct_base_url": "http://localhost:1234/v1",
            "vlm_direct_model": "fake",
            "vlm_direct_api_key": "fake",
            "vlm_repair_max_concurrent": 2,
        }
    )
    seen_pages = []

    async def fake_convert(session, img, page_num):
        seen_pages.append(page_num)
        return PageResult(
            page_num=page_num,
            ok=True,
            raw_text=f'{{"page_number": {page_num}, "regions": []}}',
            cleaned_text=f'{{"page_number": {page_num}, "regions": []}}',
            content_kind="json",
            error_kind="none",
        )

    monkeypatch.setattr(converter, "_convert_page_async_no_semaphore", fake_convert)

    import asyncio

    results = asyncio.run(
        converter._convert_sparse_pages_async(
            FakeProvider(),
            [(37, 38), (177, 178)],
        )
    )

    assert seen_pages == [38, 178]
    assert [result.page_num for result in results] == [38, 178]


def test_rerender_vlm_json_uses_current_rendering_rules_without_pdf(tmp_path):
    json_path = tmp_path / "previous.json"
    json_path.write_text(
        json.dumps(
            {
                "format": "vlm_generalized",
                "pages": [
                    {
                        "page_number": 1,
                        "printed_page_number": "88",
                        "page_width": 100,
                        "page_height": 200,
                        "regions": [
                            {"label": "Text", "bbox": [10, 10, 90, 80], "text": "main text", "confidence": None},
                            {
                                "label": "Marginal-Left",
                                "bbox": [0, 20, 8, 80],
                                "text": "0. lib. 27.",
                                "confidence": None,
                            },
                        ],
                    }
                ],
                "diagnostics": [{"page_number": 1, "ok": True, "content_kind": "json", "error_kind": "none"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    markdown, converter, failed_pages = rerender_vlm_json(
        json_path=json_path,
        converter_config={
            "vlm_api_provider": "openai_compatible",
            "vlm_direct_base_url": "http://localhost:1234/v1",
            "vlm_direct_model": "fake",
            "vlm_direct_output_mode": "json",
            "final_output_formats": ["markdown", "json", "html"],
            "vlm_direct_marginal_note_enabled": True,
            "vlm_direct_prompt_params": {"handwriting_mode": "none"},
            "vlm_direct_enable_page_anchors": True,
            "vlm_direct_extract_printed_pages": True,
        },
    )

    assert failed_pages == []
    assert "<!-- Margin:left -->" in markdown
    assert "> 0. lib. 27." in markdown
    assert "<!-- /Margin -->" in markdown
    assert markdown.startswith("{0}")
    assert markdown.rstrip().endswith("{1}\n\n---")
    assert "<!-- Page: 88 -->" in markdown
    assert len(converter._last_json_pages) == 1
