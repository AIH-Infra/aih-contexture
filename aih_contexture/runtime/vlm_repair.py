from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from aih_contexture.converters.vlm_direct_async import PageResult, VlmDirectAsyncConverter
from aih_contexture.providers.registry import provider_from_filepath


def load_vlm_generalized_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("VLM JSON root must be an object")
    if data.get("format") != "vlm_generalized":
        raise ValueError("Only vlm_generalized JSON files are supported")
    if not isinstance(data.get("pages"), list):
        raise ValueError("VLM JSON must contain a pages list")
    return data


def extract_failed_pages(data: dict[str, Any]) -> list[int]:
    failed: set[int] = set()
    diagnostics = data.get("diagnostics")
    if isinstance(diagnostics, list):
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            page_num = item.get("page_number")
            if page_num is None:
                continue
            if not bool(item.get("ok")) or item.get("content_kind") != "json":
                failed.add(int(page_num))

    pages = data.get("pages") or []
    for idx, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            failed.add(idx)
            continue
        diagnostic = page.get("diagnostic")
        page_num = int(page.get("page_number") or idx)
        if page.get("error") or not page.get("regions"):
            if isinstance(diagnostic, dict):
                if not bool(diagnostic.get("ok")) or diagnostic.get("content_kind") != "json":
                    failed.add(page_num)
            elif page.get("error"):
                failed.add(page_num)

    return sorted(page for page in failed if page >= 1)


def page_jsons_to_page_results(data: dict[str, Any], provider: str = "imported") -> list[PageResult]:
    pages = data.get("pages") or []
    results: list[PageResult] = []
    diagnostics_by_page = {
        int(item.get("page_number")): item
        for item in data.get("diagnostics") or []
        if isinstance(item, dict) and item.get("page_number") is not None
    }

    for idx, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            results.append(
                PageResult(
                    page_num=idx,
                    ok=False,
                    raw_text="",
                    cleaned_text="",
                    content_kind="none",
                    error_kind="invalid_page_object",
                    provider=provider,
                    parse_stage="import",
                    parse_detail="page is not an object",
                )
            )
            continue

        page_num = int(page.get("page_number") or idx)
        diagnostic = diagnostics_by_page.get(page_num) or page.get("diagnostic") or {}
        ok = bool(diagnostic.get("ok", not page.get("error")))
        content_kind = str(diagnostic.get("content_kind") or ("json" if ok else "none"))
        error_kind = str(diagnostic.get("error_kind") or (page.get("error") or "none"))
        page_text = json.dumps(page, ensure_ascii=False)
        results.append(
            PageResult(
                page_num=page_num,
                ok=ok and content_kind == "json" and not page.get("error"),
                raw_text=page_text,
                cleaned_text=page_text,
                content_kind=content_kind,
                error_kind=error_kind,
                http_status=diagnostic.get("http_status"),
                finish_reason=diagnostic.get("finish_reason"),
                truncated=bool(diagnostic.get("truncated", False)),
                provider=str(diagnostic.get("provider") or provider),
                parse_stage=str(diagnostic.get("parse_stage") or "import"),
                parse_detail=diagnostic.get("parse_detail"),
                raw_json_text=page_text,
            )
        )
    return sorted(results, key=lambda item: item.page_num)


def merge_repaired_pages(
    original_results: list[PageResult],
    repaired_results: list[PageResult],
) -> list[PageResult]:
    merged = {int(result.page_num): result for result in original_results}
    for repaired in repaired_results:
        if repaired.ok and repaired.content_kind == "json":
            merged[int(repaired.page_num)] = repaired
    return [merged[page_num] for page_num in sorted(merged)]


def rerender_vlm_json(
    *,
    json_path: str | Path,
    converter_config: dict[str, Any],
    progress_callback=None,
) -> tuple[str, VlmDirectAsyncConverter, list[int]]:
    data = load_vlm_generalized_json(json_path)
    failed_pages = extract_failed_pages(data)
    converter = VlmDirectAsyncConverter(
        {
            **converter_config,
            "vlm_direct_allow_empty_api_key": True,
            "vlm_direct_streaming_batches": True,
            "vlm_direct_resume_checkpoint": False,
        },
        progress_callback=progress_callback,
    )
    page_results = page_jsons_to_page_results(data, provider=converter.api_provider)
    if progress_callback is not None:
        progress_callback(
            {
                "event": "pages_loaded",
                "total_pages": len(page_results),
                "stage": "rerendering",
            }
        )
    markdown_pages, printed_pages = converter._prepare_markdown_pages(page_results)
    markdown = converter._finalize_markdown_pages(markdown_pages, printed_pages, len(page_results))
    if progress_callback is not None:
        progress_callback({"event": "file_done", "stage": "saving"})
    return markdown, converter, failed_pages


async def repair_vlm_json_async(
    *,
    pdf_path: str | Path,
    json_path: str | Path,
    converter_config: dict[str, Any],
    progress_callback=None,
) -> tuple[str, VlmDirectAsyncConverter, list[int], list[int]]:
    data = load_vlm_generalized_json(json_path)
    failed_pages = extract_failed_pages(data)

    converter = VlmDirectAsyncConverter(
        {
            **converter_config,
            "vlm_direct_streaming_batches": True,
            "vlm_direct_resume_checkpoint": False,
        },
        progress_callback=progress_callback,
    )
    original_results = page_jsons_to_page_results(data, provider=converter.api_provider)

    provider_cls = provider_from_filepath(str(pdf_path))
    provider = provider_cls(str(pdf_path), {**converter.config, "force_ocr": True})
    num_pages = len(provider)
    if len(original_results) != num_pages:
        raise ValueError(f"PDF page count ({num_pages}) does not match JSON pages ({len(original_results)})")

    page_pairs = [(page_num - 1, page_num) for page_num in failed_pages if page_num <= num_pages]
    repaired_results = await converter._convert_sparse_pages_async(provider, page_pairs)
    merged_results = merge_repaired_pages(original_results, repaired_results)
    markdown_pages, printed_pages = converter._prepare_markdown_pages(merged_results)
    markdown = converter._finalize_markdown_pages(markdown_pages, printed_pages, len(merged_results))
    remaining_failed_pages = extract_failed_pages(
        {
            "format": "vlm_generalized",
            "pages": [json.loads(page) for page in converter._last_json_pages or []],
            "diagnostics": converter._last_json_diagnostics or [],
        }
    )
    return markdown, converter, failed_pages, remaining_failed_pages


def repair_vlm_json(
    *,
    pdf_path: str | Path,
    json_path: str | Path,
    converter_config: dict[str, Any],
    progress_callback=None,
) -> tuple[str, VlmDirectAsyncConverter, list[int], list[int]]:
    return asyncio.run(
        repair_vlm_json_async(
            pdf_path=pdf_path,
            json_path=json_path,
            converter_config=converter_config,
            progress_callback=progress_callback,
        )
    )
