from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from aih_contexture.middle.heading_levels import normalize_middle_heading_levels
from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan
from aih_contexture.vendor.paddleocr_vl_compat import (
    extract_paddle_pruned_blocks,
    find_paddle_layout_results,
    looks_like_running_header_text,
    paddle_heading_attrs,
)

_PAGE_NUMBER_TEXT_RE = re.compile(r"^\s*\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?\s*$", re.IGNORECASE)
_FOOTNOTE_LEADING_MARKER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\\\(\s*)?(?:\^\s*)?\{?([0-9]{1,4}|[ivxlcdm]{1,12})\}?(?:\s*\\\))?[.)]?\s+",
    re.IGNORECASE,
)
_UNICODE_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_UNICODE_SUPERSCRIPT_LEADING_MARKER_RE = re.compile(r"^\s*([⁰¹²³⁴⁵⁶⁷⁸⁹]+)\s+")
_PADDLE_PAGE_NUMBER_RE = re.compile(r"^\s*([0-9]{1,4}|[ivxlcdm]{1,12})\s*$", re.IGNORECASE)
_PADDLE_LEFT_PAGE_HEADER_RE = re.compile(r"^\s*([0-9]{1,4}|[ivxlcdm]{1,12})\s+(.+?)\s*$", re.IGNORECASE)
_PADDLE_RIGHT_PAGE_HEADER_RE = re.compile(r"^\s*(.+?)\s+([0-9]{1,4}|[ivxlcdm]{1,12})\s*$", re.IGNORECASE)
_PADDLE_PUBLISHER_FOOTER_RE = re.compile(
    r"^\s*(?:[⁰¹²³⁴⁵⁶⁷⁸⁹]+\s+)?(?:[^\w<>{}\[\]()]{1,4}\s*)?(springer)\s*$",
    re.IGNORECASE,
)


def ocr_direct_outputs_to_middle_document(
    payload: list[Any],
    *,
    backend: str,
    model: str | None = None,
    source_name: str | None = None,
    source: str | None = None,
    printed_pages: list[str | None] | None = None,
) -> MiddleDocument:
    """Normalize official specialized OCR/VLM outputs into Contexture Middle.

    This adapter deliberately consumes the upstream model's expected output
    artifacts instead of asking specialized models to speak Contexture JSON:

    - Chandra: official HTML parsed through ``parse_chunks()``.
    - Churro: official XML parsed through ``xml_to_json()``.
    - PaddleOCR-VL: task-prompt output shaped as page blocks.
    - MinerU-VL: official-compatible structured page blocks.
    """
    normalized_backend = backend.strip().lower()
    if normalized_backend == "churro":
        pages = _churro_json_pages_to_middle_pages(
            payload,
            backend=backend,
            model=model,
            source=source,
            printed_pages=printed_pages,
        )
    elif normalized_backend in {"paddleocr_vl", "mineru_vl", "mineru_vl_page"}:
        pages = _specialized_vlm_pages_to_middle_pages(
            payload,
            backend=backend,
            model=model,
            source=source,
            printed_pages=printed_pages,
        )
    else:
        pages = _chandra_chunks_to_middle_pages(
            payload,
            backend=backend,
            model=model,
            source=source,
            printed_pages=printed_pages,
        )

    document = MiddleDocument(
        source_name=source_name,
        pages=pages,
        metadata={
            "import_source": "ocr_direct_official_output",
            "source": source,
            "specialized_protocol": "official_upstream_output",
        },
        backends={"vlm_specialized": backend, "vlm_specialized_model": model},
    )
    return normalize_middle_heading_levels(document)


def _chandra_chunks_to_middle_pages(
    payload: list[Any],
    *,
    backend: str,
    model: str | None,
    source: str | None,
    printed_pages: list[str | None] | None,
) -> list[MiddlePage]:
    pages: list[MiddlePage] = []
    for fallback_index, page_data in enumerate(payload):
        if not isinstance(page_data, dict):
            continue
        page_index = int(page_data.get("page_num", fallback_index))
        img_size = page_data.get("img_size")
        width, height = _page_size(img_size)
        page = MiddlePage(
            index=page_index,
            width=width,
            height=height,
            printed_page=_printed_page(printed_pages, page_index),
            provenance=[MiddleProvenance(backend=backend, stage="official_chunks", model=model, source=source)],
        )

        chunks = page_data.get("chunks")
        if not isinstance(chunks, list):
            chunks = []
        for order, chunk in enumerate(chunks):
            if isinstance(chunk, dict):
                page.blocks.append(
                    _chandra_chunk_to_block(
                        chunk,
                        page_index=page_index,
                        order=order,
                        backend=backend,
                        model=model,
                        source=source,
                    )
                )
        pages.append(page)
    return sorted(pages, key=lambda page: page.index)


def _chandra_chunk_to_block(
    chunk: dict[str, Any],
    *,
    page_index: int,
    order: int,
    backend: str,
    model: str | None,
    source: str | None,
) -> MiddleBlock:
    raw_label = chunk.get("label")
    content = str(chunk.get("content") or "")
    canonical_type = normalize_block_type(str(raw_label) if raw_label is not None else None)
    bbox = _bbox(chunk.get("bbox"))
    text = _html_to_text(content, canonical_type=canonical_type)
    provenance = MiddleProvenance(
        backend=backend,
        stage="official_chunks",
        raw_label=str(raw_label) if raw_label is not None else None,
        model=model,
        source=source,
    )
    spans = []
    if text:
        spans.append(
            MiddleSpan(
                text=text,
                bbox=bbox,
                attrs={"source": "official_chunk_content"},
                provenance=[MiddleProvenance(backend=backend, stage="official_text", raw_label=str(raw_label) if raw_label is not None else None, model=model, source=source)],
            )
        )

    return MiddleBlock(
        id=f"p{page_index}-ocr{order}",
        type=canonical_type,
        page_index=page_index,
        order=order,
        text=text,
        bbox=bbox,
        spans=spans,
        attrs={
            "raw_label": raw_label,
            "official_protocol": "chandra_chunks",
            "html": content,
        },
        provenance=[provenance],
    )


def _churro_json_pages_to_middle_pages(
    payload: list[Any],
    *,
    backend: str,
    model: str | None,
    source: str | None,
    printed_pages: list[str | None] | None,
) -> list[MiddlePage]:
    pages: list[MiddlePage] = []
    for fallback_index, page_payload in enumerate(payload):
        if not isinstance(page_payload, dict):
            continue
        if isinstance(page_payload.get("json"), dict):
            page_payload = page_payload["json"]
        page_entries = page_payload.get("content")
        if not isinstance(page_entries, list):
            page_entries = [{"elements": []}]
        for local_page_index, page_entry in enumerate(page_entries):
            if not isinstance(page_entry, dict):
                continue
            page_index = fallback_index + local_page_index
            printed_page = page_entry.get("page_number") or _printed_page(printed_pages, page_index)
            page = MiddlePage(
                index=page_index,
                printed_page=str(printed_page) if printed_page is not None else None,
                provenance=[MiddleProvenance(backend=backend, stage="official_xml_json", model=model, source=source)],
            )
            elements = page_entry.get("elements")
            if not isinstance(elements, list):
                elements = []
            for order, element in enumerate(elements):
                if isinstance(element, dict):
                    page.blocks.append(
                        _churro_element_to_block(
                            element,
                            page_index=page_index,
                            order=order,
                            backend=backend,
                            model=model,
                            source=source,
                        )
                    )
            pages.append(page)
    return sorted(pages, key=lambda page: page.index)


def _churro_element_to_block(
    element: dict[str, Any],
    *,
    page_index: int,
    order: int,
    backend: str,
    model: str | None,
    source: str | None,
) -> MiddleBlock:
    raw_type = str(element.get("type") or "paragraph")
    canonical_type = {
        "paragraph": "Text",
        "blockquote": "Text",
        "marginal_note": "MarginalNote",
        "heading": "SectionHeader",
        "page_header": "PageHeader",
        "page_footer": "PageFooter",
        "page_number": "PageNumber",
        "footnote": "Footnote",
        "list_item": "ListItem",
        "table": "Table",
        "equation": "Equation",
        "caption": "Caption",
        "figure": "Figure",
        "inline_annotation": "InlineAnnotation",
        "complex_region": "ComplexRegion",
    }.get(raw_type, normalize_block_type(raw_type))
    text = str(element.get("text") or "")
    attrs = {
        "raw_label": raw_type,
        "official_protocol": "churro_xml_json",
        "raw": element,
    }
    if raw_type == "marginal_note" and element.get("placement"):
        attrs["placement"] = element.get("placement")
    if raw_type == "footnote" and element.get("placement"):
        attrs["placement"] = element.get("placement")
    if raw_type == "blockquote":
        attrs["style"] = "blockquote"
    if raw_type == "heading" and element.get("heading_level"):
        attrs["heading_level"] = element.get("heading_level")
    if element.get("region"):
        attrs["region"] = element.get("region")
    provenance = MiddleProvenance(
        backend=backend,
        stage="official_xml_json",
        raw_label=raw_type,
        model=model,
        source=source,
    )
    spans = []
    if text:
        spans.append(
            MiddleSpan(
                text=text,
                attrs={"source": "official_xml_json_text"},
                provenance=[MiddleProvenance(backend=backend, stage="official_text", raw_label=raw_type, model=model, source=source)],
            )
        )

    return MiddleBlock(
        id=f"p{page_index}-ocr{order}",
        type=canonical_type,
        page_index=page_index,
        order=order,
        text=text,
        spans=spans,
        attrs=attrs,
        provenance=[provenance],
    )


def _specialized_vlm_pages_to_middle_pages(
    payload: list[Any],
    *,
    backend: str,
    model: str | None,
    source: str | None,
    printed_pages: list[str | None] | None,
) -> list[MiddlePage]:
    pages: list[MiddlePage] = []
    normalized_payload = _expand_specialized_official_pages(payload, backend=backend)
    for fallback_index, page_data in enumerate(normalized_payload):
        if not isinstance(page_data, dict):
            continue
        page_index = int(page_data.get("page_num", fallback_index))
        width, height = _page_size(page_data.get("img_size"))
        protocol = str(page_data.get("official_protocol") or f"{backend}_official_output")
        page = MiddlePage(
            index=page_index,
            width=width,
            height=height,
            printed_page=_printed_page(printed_pages, page_index),
            attrs={
                "official_protocol": protocol,
                "raw": page_data.get("raw", {}),
            },
            provenance=[MiddleProvenance(backend=backend, stage=protocol, model=model, source=source)],
        )
        if page_data.get("markdown_images") is not None:
            page.attrs["markdown_images"] = page_data.get("markdown_images")
        if page_data.get("output_images") is not None:
            page.attrs["output_images"] = page_data.get("output_images")
        if page_data.get("error") is not None:
            page.attrs["error"] = page_data.get("error")

        blocks = page_data.get("blocks")
        if not isinstance(blocks, list):
            blocks = []
        if not blocks:
            fallback_text = _specialized_markdown_text(page_data)
            if fallback_text:
                blocks = [
                    {
                        "label": "text",
                        "type": "text",
                        "text": fallback_text,
                        "official_markdown_fallback": True,
                    }
                ]
        if backend.strip().lower() == "paddleocr_vl":
            blocks = _split_paddleocr_vl_ocr_text_blocks(blocks)
        for order, block in enumerate(blocks):
            if isinstance(block, dict):
                page.blocks.append(
                    _specialized_vlm_block_to_middle_block(
                        block,
                        page_index=page_index,
                        order=_order_value(block, order),
                        backend=backend,
                        model=model,
                        source=source,
                        protocol=protocol,
                        id_suffix=f"ocr{order}",
                        page_height=height,
                    )
                )
        _promote_specialized_page_number_blocks(page)
        pages.append(page)
    return sorted(pages, key=lambda page: page.index)


def _split_paddleocr_vl_ocr_text_blocks(blocks: list[Any]) -> list[Any]:
    """Recover basic scholarly structure from PaddleOCR-VL's plain OCR prompt.

    LM Studio/API mode currently mirrors PaddleOCR-VL's upstream task prompt
    and returns a whole-page OCR transcription. For scholarly Markdown we still
    need obvious page furniture and footnote zones to enter Middle as separate
    canonical blocks.
    """
    if len(blocks) != 1 or not isinstance(blocks[0], dict):
        return blocks
    block = blocks[0]
    label = str(block.get("label") or block.get("type") or "").strip().lower()
    if label not in {"text", "ocr", ""}:
        return blocks
    text = str(block.get("text") or block.get("markdown") or "").strip()
    if not text:
        return blocks

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return blocks

    source = dict(block)
    source.pop("text", None)
    source.pop("markdown", None)
    new_blocks: list[dict[str, Any]] = []
    consumed_first = 0
    structural = False

    def add(kind: str, value: str, *, order: int, raw_role: str) -> None:
        nonlocal structural
        cleaned = value.strip()
        if not cleaned:
            return
        structural = structural or kind != "text"
        new_blocks.append(
            {
                "label": kind,
                "type": kind,
                "text": cleaned,
                "bbox": block.get("bbox"),
                "raw_prompt_label": block.get("raw_prompt_label"),
                "raw_query": block.get("raw_query"),
                "raw": {**source, "paddle_ocr_split_role": raw_role},
            }
        )

    first = paragraphs[0]
    left_header = _PADDLE_LEFT_PAGE_HEADER_RE.match(first)
    right_header = _PADDLE_RIGHT_PAGE_HEADER_RE.match(first)
    if left_header and _is_valid_roman_page(left_header.group(1)) or (left_header and left_header.group(1).isdigit()):
        add("page_number", left_header.group(1), order=0, raw_role="running_header_page_number")
        add("page_header", left_header.group(2), order=1, raw_role="running_header")
        consumed_first = 1
    elif right_header and _is_paddle_running_header(right_header.group(1)):
        add("page_header", right_header.group(1), order=0, raw_role="running_header")
        add("page_number", right_header.group(2), order=1, raw_role="running_header_page_number")
        consumed_first = 1
    elif _PADDLE_PAGE_NUMBER_RE.match(first):
        marker = _PADDLE_PAGE_NUMBER_RE.match(first).group(1)
        add("page_number", marker, order=0, raw_role="printed_page_number")
        consumed_first = 1
        if len(paragraphs) > 1 and _is_paddle_running_header(paragraphs[1]):
            add("page_header", paragraphs[1], order=1, raw_role="running_header")
            consumed_first = 2

    tail = len(paragraphs)
    while tail > consumed_first and _PADDLE_PUBLISHER_FOOTER_RE.match(paragraphs[tail - 1]):
        footer_text = _PADDLE_PUBLISHER_FOOTER_RE.match(paragraphs[tail - 1]).group(1)
        add("page_footer", footer_text, order=10_000 + tail, raw_role="publisher_footer")
        tail -= 1

    body_parts: list[str] = []
    footnote_order = 0
    in_footnotes = False
    for paragraph in paragraphs[consumed_first:tail]:
        marker = _unicode_footnote_marker(paragraph)
        if marker:
            if body_parts:
                add("text", "\n\n".join(body_parts), order=100, raw_role="body_text")
                body_parts = []
            add("footnote", paragraph, order=1_000 + footnote_order, raw_role="footnote")
            footnote_order += 1
            in_footnotes = True
            continue
        if in_footnotes and new_blocks and str(new_blocks[-1].get("label")).lower() == "footnote":
            new_blocks[-1]["text"] = f"{new_blocks[-1]['text']}\n\n{paragraph}"
        else:
            body_parts.append(paragraph)

    if body_parts:
        add("text", "\n\n".join(body_parts), order=100, raw_role="body_text")

    if not structural:
        return blocks
    for order, item in enumerate(new_blocks):
        item.setdefault("order", order)
    return new_blocks


def _unicode_footnote_marker(text: str) -> str | None:
    match = _UNICODE_SUPERSCRIPT_LEADING_MARKER_RE.match(text or "")
    if not match:
        return None
    return match.group(1).translate(_UNICODE_SUPERSCRIPT_DIGITS)


def _is_paddle_running_header(text: str) -> bool:
    return looks_like_running_header_text(text)


def _expand_specialized_official_pages(payload: list[Any], *, backend: str) -> list[Any]:
    normalized_backend = backend.strip().lower()
    expanded: list[Any] = []
    for fallback_index, item in enumerate(payload):
        if not isinstance(item, dict):
            expanded.append(item)
            continue

        if normalized_backend == "paddleocr_vl":
            layout_results = _find_paddle_layout_results(item)
            if layout_results:
                for local_index, result in enumerate(layout_results):
                    if not isinstance(result, dict):
                        continue
                    markdown = result.get("markdown")
                    markdown_images = markdown.get("images") if isinstance(markdown, dict) else None
                    expanded.append(
                        {
                            "page_num": int(item.get("page_num", fallback_index + local_index)),
                            "img_size": item.get("img_size") or item.get("page_size") or [],
                            "backend": backend,
                            "official_protocol": item.get("official_protocol") or "paddleocr_vl_layout_parsing",
                            "markdown": markdown if isinstance(markdown, (dict, str)) else {},
                            "markdown_images": markdown_images,
                            "output_images": result.get("outputImages"),
                            "blocks": _extract_paddle_pruned_blocks(result.get("prunedResult")),
                            "raw": {
                                "layoutParsingResult": result,
                                "source": item,
                            },
                        }
                    )
                continue

        if normalized_backend in {"mineru_vl", "mineru_vl_page"}:
            pdf_info = _find_mineru_pdf_info(item)
            if pdf_info:
                for local_index, page_info in enumerate(pdf_info):
                    if not isinstance(page_info, dict):
                        continue
                    expanded.append(
                        {
                            "page_num": int(page_info.get("page_idx", item.get("page_num", local_index))),
                            "img_size": page_info.get("page_size") or item.get("img_size") or [],
                            "backend": backend,
                            "official_protocol": item.get("official_protocol") or "mineru_middle_json",
                            "blocks": _extract_mineru_page_blocks(page_info),
                            "raw": {
                                "page_info": page_info,
                                "source": {key: value for key, value in item.items() if key != "pdf_info"},
                            },
                        }
                    )
                continue

        expanded.append(item)
    return expanded


def _find_paddle_layout_results(data: dict[str, Any]) -> list[Any]:
    return find_paddle_layout_results(data)


def _paddle_layout_results_from_candidate(candidate: Any) -> list[Any]:
    from aih_contexture.vendor.paddleocr_vl_compat import paddle_layout_results_from_candidate

    return paddle_layout_results_from_candidate(candidate)


def _extract_paddle_pruned_blocks(pruned_result: Any) -> list[dict[str, Any]]:
    return extract_paddle_pruned_blocks(pruned_result)


def _find_mineru_pdf_info(data: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = [data, data.get("raw")]
    if isinstance(data.get("raw"), dict):
        candidates.extend([data["raw"].get("middle_json"), data["raw"].get("result")])
    for candidate in candidates:
        if isinstance(candidate, dict):
            pdf_info = candidate.get("pdf_info")
            if isinstance(pdf_info, list):
                return pdf_info
    return []


def _extract_mineru_page_blocks(page_info: dict[str, Any]) -> list[dict[str, Any]]:
    primary = page_info.get("para_blocks")
    if isinstance(primary, list) and primary:
        blocks = [dict(item, block_source=item.get("block_source", "para_blocks")) for item in primary if isinstance(item, dict)]
        discarded = page_info.get("discarded_blocks")
        if isinstance(discarded, list):
            blocks.extend(
                dict(item, block_source=item.get("block_source", "discarded_blocks"))
                for item in discarded
                if isinstance(item, dict)
            )
        return blocks

    for key in ("preproc_blocks", "blocks", "discarded_blocks"):
        value = page_info.get(key)
        if isinstance(value, list):
            return [dict(item, block_source=item.get("block_source", key)) for item in value if isinstance(item, dict)]
    return []


def _specialized_markdown_text(page_data: dict[str, Any]) -> str:
    markdown = page_data.get("markdown")
    if isinstance(markdown, str):
        return markdown.strip()
    if isinstance(markdown, dict):
        for key in ("text", "markdown_texts", "content"):
            value = markdown.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raw = page_data.get("raw")
    if isinstance(raw, dict):
        raw_markdown = raw.get("markdown")
        if isinstance(raw_markdown, str):
            return raw_markdown.strip()
        if isinstance(raw_markdown, dict):
            value = raw_markdown.get("text") or raw_markdown.get("markdown_texts")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _specialized_vlm_block_to_middle_block(
    block: dict[str, Any],
    *,
    page_index: int,
    order: int,
    backend: str,
    model: str | None,
    source: str | None,
    protocol: str,
    id_suffix: str,
    page_height: float | None = None,
) -> MiddleBlock:
    raw_label = _specialized_vlm_raw_label(block, backend=backend)
    canonical_type = normalize_block_type(str(raw_label) if raw_label is not None else None)
    spans = _nested_spans_to_middle_spans(
        block,
        backend=backend,
        model=model,
        source=source,
        raw_label=str(raw_label) if raw_label is not None else None,
        protocol=protocol,
    )
    children: list[MiddleBlock] = []
    child_blocks = block.get("blocks")
    if isinstance(child_blocks, list):
        for child_index, child in enumerate(child_blocks):
            if not isinstance(child, dict):
                continue
            child_order = _order_value(child, child_index)
            children.append(
                _specialized_vlm_block_to_middle_block(
                    child,
                    page_index=page_index,
                    order=child_order,
                    backend=backend,
                    model=model,
                    source=source,
                    protocol=protocol,
                    id_suffix=f"{id_suffix}-c{child_index}",
                    page_height=page_height,
                )
            )
    text = _specialized_block_text(block, spans=spans, children=children)
    if _mineru_ref_text_should_be_footnote(block, raw_label=raw_label, text=text, page_height=page_height):
        canonical_type = "Footnote"
    bbox = _bbox(block.get("bbox") or block.get("block_bbox") or block.get("coordinate"))
    confidence = _confidence(block)
    attrs = {
        "raw_label": raw_label,
        "official_protocol": protocol,
        "raw": dict(block),
    }
    if isinstance(block.get("attrs"), dict):
        attrs.update(block["attrs"])
    if canonical_type == "SectionHeader":
        attrs.update(paddle_heading_attrs(raw_label, text=text, bbox=bbox, page_height=page_height))
    if block.get("normalized_bbox") is not None:
        attrs["normalized_bbox"] = block.get("normalized_bbox")
    if block.get("loc_bbox_1000") is not None:
        attrs["loc_bbox_1000"] = block.get("loc_bbox_1000")
    for heading_key in ("heading_level", "heading_level_source", "raw_heading_level", "title_role"):
        if block.get(heading_key) is not None:
            attrs[heading_key] = block.get(heading_key)
    if block.get("raw_prompt") is not None:
        attrs["raw_prompt"] = block.get("raw_prompt")
    if block.get("raw_prompt_label") is not None:
        attrs["raw_prompt_label"] = block.get("raw_prompt_label")
    if block.get("raw_query") is not None:
        attrs["raw_query"] = block.get("raw_query")

    provenance = MiddleProvenance(
        backend=backend,
        stage=protocol,
        raw_label=str(raw_label) if raw_label is not None else None,
        model=model,
        source=source,
    )
    if not spans and text:
        spans.append(
            MiddleSpan(
                text=text,
                bbox=bbox,
                confidence=confidence,
                attrs={"source": protocol},
                provenance=[MiddleProvenance(backend=backend, stage="official_text", raw_label=str(raw_label) if raw_label is not None else None, model=model, source=source)],
            )
        )

    return MiddleBlock(
        id=f"p{page_index}-{id_suffix}",
        type=canonical_type,
        page_index=page_index,
        order=order,
        text=text,
        bbox=bbox,
        confidence=confidence,
        spans=spans,
        children=children,
        attrs=attrs,
        provenance=[provenance],
    )


def _specialized_vlm_raw_label(block: dict[str, Any], *, backend: str) -> Any:
    raw_label = block.get("label") or block.get("block_label") or block.get("type") or block.get("layout_label")
    if backend.strip().lower() in {"mineru_vl", "mineru_vl_page"} and str(raw_label).strip().lower() == "document":
        block_type = block.get("type")
        if isinstance(block_type, str) and block_type.strip():
            return block_type
    return raw_label


def _mineru_ref_text_should_be_footnote(
    block: dict[str, Any],
    *,
    raw_label: Any,
    text: str,
    page_height: float | None,
) -> bool:
    if str(raw_label or "").strip().lower() != "ref_text":
        return False
    if not _FOOTNOTE_LEADING_MARKER_RE.match(text or ""):
        return False
    bbox = _bbox(block.get("bbox") or block.get("block_bbox") or block.get("coordinate"))
    if isinstance(page_height, (int, float)) and page_height > 0 and bbox:
        return float(bbox[1]) >= float(page_height) * 0.5
    return True


def _specialized_block_text(
    block: dict[str, Any],
    *,
    spans: list[MiddleSpan],
    children: list[MiddleBlock] | None = None,
) -> str:
    for key in ("text", "block_content", "content", "html", "markdown"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if spans:
        return " ".join(span.text for span in spans if span.text).strip()
    if children:
        return "\n".join(child.text for child in children if child.text).strip()
    pieces: list[str] = []
    for line in block.get("lines", []) or []:
        if not isinstance(line, dict):
            continue
        direct = line.get("text") or line.get("content")
        if isinstance(direct, str) and direct.strip():
            pieces.append(direct.strip())
            continue
        line_pieces = []
        for span in line.get("spans", []) or []:
            if isinstance(span, dict):
                text = span.get("text") or span.get("content") or span.get("html")
                if isinstance(text, str) and text.strip():
                    line_pieces.append(text.strip())
        if line_pieces:
            pieces.append("".join(line_pieces))
    return "\n".join(pieces).strip()


def _nested_spans_to_middle_spans(
    block: dict[str, Any],
    *,
    backend: str,
    model: str | None,
    source: str | None,
    raw_label: str | None,
    protocol: str,
) -> list[MiddleSpan]:
    spans: list[MiddleSpan] = []
    for line in block.get("lines", []) or []:
        if not isinstance(line, dict):
            continue
        for span in line.get("spans", []) or []:
            if not isinstance(span, dict):
                continue
            text = span.get("text") or span.get("content") or span.get("html")
            if not isinstance(text, str) or not text.strip():
                continue
            span_label = span.get("label") or span.get("block_label") or span.get("type") or raw_label
            spans.append(
                MiddleSpan(
                    text=text.strip(),
                    bbox=_bbox(span.get("bbox") or span.get("block_bbox") or span.get("coordinate")),
                    confidence=_confidence(span),
                    attrs={
                        "source": protocol,
                        "raw_label": span_label,
                        "raw": dict(span),
                    },
                    provenance=[
                        MiddleProvenance(
                            backend=backend,
                            stage="official_span",
                            raw_label=str(span_label) if span_label is not None else None,
                            model=model,
                            source=source,
                        )
                    ],
                )
            )
    return spans


def _confidence(value: dict[str, Any]) -> float | None:
    for key in ("confidence", "score", "prob"):
        item = value.get(key)
        if isinstance(item, (int, float)):
            return float(item)
    return None


def _order_value(value: dict[str, Any], fallback: int) -> int:
    for key in ("order", "block_order", "index", "block_id"):
        item = value.get(key)
        if isinstance(item, int):
            return item
    return fallback


def _promote_specialized_page_number_blocks(page: MiddlePage) -> None:
    edge_top = float(page.height) * 0.14 if page.height else None
    edge_bottom = float(page.height) * 0.86 if page.height else None
    for block in page.blocks:
        if block.type not in {"Text", "PageNumber"}:
            continue
        text = (block.text or "").strip()
        marker = _page_number_marker(text)
        if marker is None:
            continue
        if block.type == "PageNumber":
            if not page.printed_page:
                page.printed_page = marker
            continue
        if not block.bbox or edge_top is None or edge_bottom is None:
            continue
        y0, y1 = block.bbox[1], block.bbox[3]
        if y0 > edge_top and y1 < edge_bottom:
            continue
        block.type = "PageNumber"
        block.attrs["inferred_type"] = "PageNumber"
        block.attrs["raw_label_before_inference"] = block.attrs.get("raw_label")
        if not page.printed_page:
            page.printed_page = marker


def _page_number_marker(text: str) -> str | None:
    match = _PAGE_NUMBER_TEXT_RE.match(text)
    if not match:
        return None
    marker = match.group(1)
    if marker.isdigit() or _is_valid_roman_page(marker):
        return marker
    return None


def _is_valid_roman_page(value: str) -> bool:
    text = value.strip().upper()
    if not text:
        return False
    return re.fullmatch(r"M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", text) is not None


def _html_to_text(content: str, *, canonical_type: str) -> str:
    if not content:
        return ""
    if canonical_type == "Table" and "<table" in content.lower():
        return content.strip()
    soup = BeautifulSoup(content, "html.parser")
    if canonical_type in {"Figure", "Picture"}:
        img = soup.find("img")
        if img and img.get("alt"):
            return str(img.get("alt")).strip()
    return soup.get_text(" ", strip=True)


def _page_size(value: Any) -> tuple[float | None, float | None]:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value):
        return float(value[0]), float(value[1])
    return None, None


def _bbox(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        return [float(item) for item in value]
    return None


def _printed_page(value: list[str | None] | None, page_index: int) -> str | None:
    if not value or page_index >= len(value):
        return None
    page = value[page_index]
    return str(page) if page is not None else None
