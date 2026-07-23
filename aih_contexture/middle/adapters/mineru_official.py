from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from aih_contexture.middle.heading_levels import normalize_middle_heading_levels
from aih_contexture.middle.labels import normalize_block_type
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan

MINERU_COORDINATE_SPACE = "mineru_0_1000_normalized"


def detect_mineru_official_json_kind(payload: Any, *, file_name: str | None = None) -> str:
    """Identify supported MinerU official JSON artifacts.

    This deliberately does not treat Contexture Middle JSON as MinerU JSON. The
    two formats both use the word "middle" in places, but they are separate
    protocols.
    """
    name = (file_name or "").lower()
    if isinstance(payload, dict) and payload.get("schema_version") == "contexture-middle-json/0.1":
        return "contexture_middle_json"
    if isinstance(payload, dict) and isinstance(payload.get("pdf_info"), list):
        return "mineru_middle_json"
    if isinstance(payload, dict):
        for key in ("content_list_v2", "content_list", "result", "data"):
            nested = payload.get(key)
            nested_kind = detect_mineru_official_json_kind(nested, file_name=file_name)
            if nested_kind != "unknown":
                return nested_kind
    if isinstance(payload, list):
        if payload and all(isinstance(item, list) for item in payload):
            return "mineru_content_list_v2"
        if name.endswith("_content_list_v2.json"):
            return "mineru_content_list_v2"
        if all(isinstance(item, dict) for item in payload):
            return "mineru_content_list"
    return "unknown"


def mineru_official_json_to_middle_document(
    payload: Any,
    *,
    source_name: str | None = None,
    source: str | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    kind = detect_mineru_official_json_kind(payload, file_name=file_name)
    if kind == "contexture_middle_json":
        raise ValueError("这是 Contexture Middle JSON；请使用“Middle JSON 重渲染”，不要走 MinerU 官方 JSON 导入。")
    if kind == "mineru_middle_json":
        document = _mineru_middle_json_to_middle_document(payload, source_name=source_name, source=source)
    elif kind in {"mineru_content_list", "mineru_content_list_v2"}:
        document = _mineru_content_list_to_middle_document(payload, kind=kind, source_name=source_name, source=source)
    else:
        raise ValueError("无法识别 MinerU 官方 JSON。当前支持 *_content_list.json、*_content_list_v2.json 和 MinerU 官方 *_middle.json。")
    return normalize_middle_heading_levels(document).to_dict()


def _mineru_content_list_to_middle_document(
    payload: Any,
    *,
    kind: str,
    source_name: str | None,
    source: str | None,
) -> MiddleDocument:
    pages_payload = _content_list_pages(payload, kind=kind)
    pages: list[MiddlePage] = []
    for page_index in sorted(pages_payload):
        items = pages_payload[page_index]
        page = MiddlePage(
            index=page_index,
            width=1000.0,
            height=1000.0,
            attrs={
                "official_protocol": kind,
                "coordinate_space": MINERU_COORDINATE_SPACE,
            },
            provenance=[MiddleProvenance(backend="mineru_official_json", stage=kind, source=source)],
        )
        order = 0
        for item in items:
            for block in _content_item_to_blocks(
                item,
                page_index=page_index,
                order_base=order,
                source=source,
                protocol=kind,
            ):
                page.blocks.append(block)
                order += 1
        _promote_printed_page_from_page_number_blocks(page)
        pages.append(page)

    return MiddleDocument(
        source_name=source_name,
        pages=pages,
        metadata={
            "import_source": "mineru_official_json",
            "official_protocol": kind,
            "coordinate_space": MINERU_COORDINATE_SPACE,
            "source": source,
        },
        backends={"external_document": "mineru_official_json"},
    )


def _mineru_middle_json_to_middle_document(
    payload: dict[str, Any],
    *,
    source_name: str | None,
    source: str | None,
) -> MiddleDocument:
    pages: list[MiddlePage] = []
    for fallback_index, page_info in enumerate(payload.get("pdf_info") or []):
        if not isinstance(page_info, dict):
            continue
        page_index = _int_value(page_info.get("page_idx"), fallback_index)
        width, height = _page_size(page_info.get("page_size"))
        page = MiddlePage(
            index=page_index,
            width=width,
            height=height,
            attrs={
                "official_protocol": "mineru_middle_json",
                "raw_backend": payload.get("_backend"),
                "raw_version_name": payload.get("_version_name"),
            },
            provenance=[MiddleProvenance(backend="mineru_official_json", stage="mineru_middle_json", source=source)],
        )
        blocks = _mineru_middle_page_blocks(page_info)
        for order, block_payload in enumerate(blocks):
            page.blocks.append(
                _mineru_middle_block_to_middle_block(
                    block_payload,
                    page_index=page_index,
                    order=order,
                    id_suffix=f"b{order}",
                    source=source,
                )
            )
        _promote_printed_page_from_page_number_blocks(page)
        pages.append(page)

    return MiddleDocument(
        source_name=source_name,
        pages=sorted(pages, key=lambda page: page.index),
        metadata={
            "import_source": "mineru_official_json",
            "official_protocol": "mineru_middle_json",
            "source": source,
            "raw_backend": payload.get("_backend"),
            "raw_version_name": payload.get("_version_name"),
        },
        backends={"external_document": "mineru_official_json"},
    )


def _content_list_pages(payload: Any, *, kind: str) -> dict[int, list[dict[str, Any]]]:
    if isinstance(payload, dict):
        for key in ("content_list_v2", "content_list", "result", "data"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return _content_list_pages(nested, kind=detect_mineru_official_json_kind(nested))

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if kind == "mineru_content_list_v2" and isinstance(payload, list):
        for page_index, page_items in enumerate(payload):
            if isinstance(page_items, list):
                grouped[page_index].extend(item for item in page_items if isinstance(item, dict))
        return grouped

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            page_index = _int_value(item.get("page_idx"), 0)
            grouped[page_index].append(item)
    return grouped


def _content_item_to_blocks(
    item: dict[str, Any],
    *,
    page_index: int,
    order_base: int,
    source: str | None,
    protocol: str,
) -> list[MiddleBlock]:
    raw_type = str(item.get("type") or "text")
    if raw_type == "list":
        list_items = _content_list_item_texts(item)
        if list_items:
            block_type = "Reference" if _is_reference_list(item) else "ListItem"
            return [
                _content_block(
                    item,
                    page_index=page_index,
                    order=order_base + index,
                    text=text,
                    block_type=block_type,
                    id_suffix=f"b{order_base}-{index}",
                    source=source,
                    protocol=protocol,
                    raw_type=raw_type,
                )
                for index, text in enumerate(list_items)
            ]

    return [
        _content_block(
            item,
            page_index=page_index,
            order=order_base,
            text=_content_item_text(item),
            block_type=_content_item_block_type(item),
            id_suffix=f"b{order_base}",
            source=source,
            protocol=protocol,
            raw_type=raw_type,
        )
    ]


def _content_block(
    item: dict[str, Any],
    *,
    page_index: int,
    order: int,
    text: str,
    block_type: str,
    id_suffix: str,
    source: str | None,
    protocol: str,
    raw_type: str,
) -> MiddleBlock:
    bbox = _bbox(item.get("bbox"))
    provenance = MiddleProvenance(
        backend="mineru_official_json",
        stage=protocol,
        raw_label=raw_type,
        source=source,
    )
    spans = []
    if text:
        spans.append(
            MiddleSpan(
                text=text,
                bbox=bbox,
                attrs={"source": protocol, "raw_label": raw_type},
                provenance=[MiddleProvenance(backend="mineru_official_json", stage="official_text", raw_label=raw_type, source=source)],
            )
        )
    attrs = {
        "raw_label": raw_type,
        "official_protocol": protocol,
        "coordinate_space": MINERU_COORDINATE_SPACE,
        "raw": dict(item),
    }
    if item.get("text_level") is not None:
        attrs["text_level"] = item.get("text_level")
        attrs["heading_level"] = item.get("text_level")
        attrs["heading_level_source"] = "mineru_text_level"
        attrs["raw_heading_level"] = item.get("text_level")
    if item.get("img_path") is not None:
        attrs["image_path"] = item.get("img_path")

    return MiddleBlock(
        id=f"p{page_index}-{id_suffix}",
        type=block_type,
        page_index=page_index,
        order=order,
        text=text,
        bbox=bbox,
        spans=spans,
        attrs=attrs,
        provenance=[provenance],
    )


def _content_item_block_type(item: dict[str, Any]) -> str:
    raw_type = str(item.get("type") or "").strip().lower()
    if raw_type in {"title"}:
        return "SectionHeader"
    if raw_type == "text" and _int_value(item.get("text_level"), 0) > 0:
        return "SectionHeader"
    if raw_type == "paragraph":
        return "Text"
    if raw_type in {"header", "page_header"}:
        return "PageHeader"
    if raw_type in {"footer", "page_footer"}:
        return "PageFooter"
    if raw_type == "page_number":
        return "PageNumber"
    if raw_type == "page_footnote":
        return "Footnote"
    if raw_type in {"equation", "equation_interline", "interline_equation"}:
        return "Equation"
    if raw_type == "table":
        return "Table"
    if raw_type == "chart":
        return "Figure"
    if raw_type == "image":
        return "Figure" if str(item.get("sub_type") or "").lower() == "seal" else "Picture"
    if raw_type in {"code", "algorithm"}:
        return "Code"
    if raw_type in {"page_aside_text", "aside_text"}:
        return "MarginalNote"
    return normalize_block_type(raw_type)


def _content_item_text(item: dict[str, Any]) -> str:
    raw_type = str(item.get("type") or "").strip().lower()
    for key in ("text", "table_body", "code_body", "algorithm_body"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    content = item.get("content")
    if isinstance(content, dict):
        if raw_type == "table" and isinstance(content.get("html"), str):
            return content["html"].strip()
        return _content_dict_text(content, raw_type=raw_type)
    if raw_type in {"image", "chart"}:
        captions = _string_list(item.get("image_caption") or item.get("chart_caption"))
        footnotes = _string_list(item.get("image_footnote") or item.get("chart_footnote"))
        return "\n".join(captions + footnotes).strip()
    return _extract_text(item)


def _content_dict_text(content: dict[str, Any], *, raw_type: str) -> str:
    key_candidates = [
        f"{raw_type}_content",
        "title_content",
        "paragraph_content",
        "page_header_content",
        "page_footer_content",
        "page_number_content",
        "page_footnote_content",
        "page_aside_text_content",
        "math_content",
        "code_content",
        "algorithm_content",
    ]
    for key in key_candidates:
        if key in content:
            text = _extract_text(content[key])
            if text:
                return text
    if raw_type in {"image", "chart"}:
        captions = _extract_text(content.get(f"{raw_type}_caption"))
        footnotes = _extract_text(content.get(f"{raw_type}_footnote"))
        return "\n".join(part for part in (captions, footnotes) if part).strip()
    return _extract_text(content)


def _content_list_item_texts(item: dict[str, Any]) -> list[str]:
    direct = item.get("list_items")
    if isinstance(direct, list):
        return [text for text in (_extract_text(value) for value in direct) if text]
    content = item.get("content")
    if isinstance(content, dict) and isinstance(content.get("list_items"), list):
        return [text for text in (_extract_text(value) for value in content["list_items"]) if text]
    return []


def _is_reference_list(item: dict[str, Any]) -> bool:
    candidates = [
        item.get("sub_type"),
        item.get("list_type"),
    ]
    content = item.get("content")
    if isinstance(content, dict):
        candidates.append(content.get("list_type"))
    return any("ref" in str(value or "").lower() or "reference" in str(value or "").lower() for value in candidates)


def _mineru_middle_page_blocks(page_info: dict[str, Any]) -> list[dict[str, Any]]:
    para_blocks = page_info.get("para_blocks")
    if isinstance(para_blocks, list) and para_blocks:
        blocks = [dict(item, block_source=item.get("block_source", "para_blocks")) for item in para_blocks if isinstance(item, dict)]
        discarded = page_info.get("discarded_blocks")
        if isinstance(discarded, list):
            blocks.extend(dict(item, block_source=item.get("block_source", "discarded_blocks")) for item in discarded if isinstance(item, dict))
        return blocks

    for key in ("preproc_blocks", "blocks", "discarded_blocks"):
        value = page_info.get(key)
        if isinstance(value, list):
            return [dict(item, block_source=item.get("block_source", key)) for item in value if isinstance(item, dict)]
    return []


def _mineru_middle_block_to_middle_block(
    payload: dict[str, Any],
    *,
    page_index: int,
    order: int,
    id_suffix: str,
    source: str | None,
) -> MiddleBlock:
    raw_label = str(payload.get("type") or payload.get("label") or "text")
    children = []
    for child_index, child in enumerate(payload.get("blocks") or []):
        if isinstance(child, dict):
            children.append(
                _mineru_middle_block_to_middle_block(
                    child,
                    page_index=page_index,
                    order=child_index,
                    id_suffix=f"{id_suffix}-c{child_index}",
                    source=source,
                )
            )
    spans = _mineru_middle_spans(payload, raw_label=raw_label, source=source)
    text = _mineru_middle_text(payload, spans=spans, children=children)
    bbox = _bbox(payload.get("bbox"))
    confidence = _confidence(payload)
    provenance = MiddleProvenance(
        backend="mineru_official_json",
        stage="mineru_middle_json",
        raw_label=raw_label,
        confidence=confidence,
        source=source,
    )
    if not spans and text:
        spans.append(
            MiddleSpan(
                text=text,
                bbox=bbox,
                confidence=confidence,
                attrs={"source": "mineru_middle_json", "raw_label": raw_label},
                provenance=[MiddleProvenance(backend="mineru_official_json", stage="official_text", raw_label=raw_label, source=source)],
            )
        )
    attrs = {
        "raw_label": raw_label,
        "official_protocol": "mineru_middle_json",
        "raw": dict(payload),
    }
    if payload.get("text_level") is not None:
        attrs["text_level"] = payload.get("text_level")
        attrs["heading_level"] = payload.get("text_level")
        attrs["heading_level_source"] = "mineru_text_level"
        attrs["raw_heading_level"] = payload.get("text_level")
    return MiddleBlock(
        id=f"p{page_index}-{id_suffix}",
        type=normalize_block_type(raw_label),
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


def _mineru_middle_spans(payload: dict[str, Any], *, raw_label: str, source: str | None) -> list[MiddleSpan]:
    spans: list[MiddleSpan] = []
    for line in payload.get("lines") or []:
        if not isinstance(line, dict):
            continue
        for span in line.get("spans") or []:
            if not isinstance(span, dict):
                continue
            text = span.get("text") or span.get("content") or span.get("html")
            if not isinstance(text, str) or not text.strip():
                continue
            span_label = str(span.get("type") or raw_label)
            spans.append(
                MiddleSpan(
                    text=text.strip(),
                    bbox=_bbox(span.get("bbox")),
                    confidence=_confidence(span),
                    attrs={"source": "mineru_middle_json", "raw_label": span_label, "raw": dict(span)},
                    provenance=[MiddleProvenance(backend="mineru_official_json", stage="official_span", raw_label=span_label, source=source)],
                )
            )
    return spans


def _mineru_middle_text(
    payload: dict[str, Any],
    *,
    spans: list[MiddleSpan],
    children: list[MiddleBlock],
) -> str:
    for key in ("text", "content", "html", "markdown"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if spans:
        return "\n".join(span.text for span in spans if span.text).strip()
    if children:
        return "\n".join(child.text for child in children if child.text).strip()
    return ""


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _clean_inline_artifact(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        if isinstance(value.get("children"), list):
            child_text = _extract_text(value["children"])
            if child_text:
                return child_text
        if isinstance(value.get("content"), str):
            return _clean_inline_artifact(value["content"])
        for key in ("item_content", "text", "html", "markdown", "title", "caption"):
            text = _extract_text(value.get(key))
            if text:
                return text
        text_parts = []
        for key, nested in value.items():
            if key in {"bbox", "img_path", "image_source", "path", "url", "type", "sub_type", "attribute", "level"}:
                continue
            nested_text = _extract_text(nested)
            if nested_text:
                text_parts.append(nested_text)
        return "\n".join(text_parts).strip()
    return ""


def _clean_inline_artifact(value: str) -> str:
    text = value.strip()
    if text.startswith("@{") and "content=" in text and text.endswith("}"):
        marker = "content="
        start = text.find(marker) + len(marker)
        end = text.rfind("}")
        return text[start:end].strip()
    return text


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _page_size(value: Any) -> tuple[float | None, float | None]:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value):
        return float(value[0]), float(value[1])
    return None, None


def _bbox(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
        return [float(item) for item in value]
    return None


def _confidence(value: dict[str, Any]) -> float | None:
    for key in ("confidence", "score", "prob"):
        item = value.get(key)
        if isinstance(item, (int, float)):
            return float(item)
    return None


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _promote_printed_page_from_page_number_blocks(page: MiddlePage) -> None:
    for block in page.blocks:
        if block.type == "PageNumber" and block.text.strip():
            page.printed_page = block.text.strip()
            return


def default_source_name_from_json_path(path: str | Path) -> str:
    name = Path(path).name
    for suffix in ("_content_list_v2.json", "_content_list.json", "_middle.json"):
        if name.endswith(suffix):
            return name[: -len(suffix)] or name
    return Path(name).stem
