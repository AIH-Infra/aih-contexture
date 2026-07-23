from __future__ import annotations

import copy
import html
import re
from typing import Any


FOOTNOTE_SEMANTIC_VERSION = "footnote-superscript/0.1"

_HTML_SUP_RE = re.compile(r"<sup>\s*(.*?)\s*</sup>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_MARKER_RE = re.compile(
    r"^(?:\d{1,4}|[A-Za-z]{1,3}|[IVXLCDMivxlcdm]{1,12}|[*†‡§¶#]+)(?:[)\].-])?$"
)
_LEADING_HTML_SUP_RE = re.compile(
    r"^\s*<sup>\s*([0-9]{1,4}|[A-Za-z]{1,3}|[ivxlcdmIVXLCDM]{1,12}|[*†‡§¶#]+)\s*</sup>\s*"
)
_LEADING_MARKER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\\\(\s*)?(?:\^\s*)?\{?([0-9]{1,4}|[ivxlcdmIVXLCDM]{1,12}|[*†‡§¶#]+)\}?(?:\s*\\\))?[.)]?\s+",
    re.IGNORECASE,
)
_REFERENCE_CONTEXT_RE = re.compile(
    r"(?:\bparagraph|\bpara\.?|\bchap\.?|\bchapter|\bbook|\bsec\.?|\bsection|§|\bpage|\bpp\.?|\bline|\bvol\.?|\bvolume|\bno\.?|\bnumber)\s*$",
    re.IGNORECASE,
)

_FOOTNOTE_EVIDENCE_EXCLUDED_TYPES = {
    "PageHeader",
    "PageFooter",
    "PageNumber",
    "TableOfContents",
    "Equation",
}
_INLINE_REFERENCE_EXCLUDED_TYPES = {
    "PageHeader",
    "PageFooter",
    "PageNumber",
    "TableOfContents",
    "Equation",
    "Table",
    "Code",
    "Form",
}


def resolve_middle_for_rendering(
    middle_json: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    config = config or {}
    return resolve_document_semantics(
        middle_json,
        footnote_enabled=bool(config.get("footnote_enabled", True)),
        marginal_detection_enabled=bool(config.get("marginal_detection_enabled", True)),
        superscript_policy=str(config.get("superscript_policy", "footnote_safe")),
        profile=str(config.get("semantic_profile", "humanities")),
        force=force,
    )


def resolve_document_semantics(
    middle_json: dict[str, Any],
    *,
    footnote_enabled: bool = True,
    marginal_detection_enabled: bool = True,
    superscript_policy: str = "footnote_safe",
    profile: str = "humanities",
    force: bool = False,
) -> dict[str, Any]:
    if not isinstance(middle_json, dict):
        return middle_json

    metadata = middle_json.get("metadata")
    if (
        not force
        and isinstance(metadata, dict)
        and isinstance(metadata.get("semantic_resolution"), dict)
        and metadata["semantic_resolution"].get("version") == FOOTNOTE_SEMANTIC_VERSION
        and metadata["semantic_resolution"].get("completed") is True
    ):
        return copy.deepcopy(middle_json)

    data = copy.deepcopy(middle_json)
    pages = data.get("pages")
    if not isinstance(pages, list):
        return data

    counts = {
        "footnote_definitions": 0,
        "footnote_references": 0,
        "visual_superscripts": 0,
        "visual_superscripts_unwrapped": 0,
        "marginal_line_numbers": 0,
        "toc_page_numbers_unwrapped": 0,
    }
    warnings: list[str] = []

    for page in pages:
        if not isinstance(page, dict):
            continue
        _resolve_page(
            page,
            footnote_enabled=footnote_enabled,
            marginal_detection_enabled=marginal_detection_enabled,
            counts=counts,
            warnings=warnings,
        )

    data.setdefault("metadata", {})["semantic_resolution"] = {
        "version": FOOTNOTE_SEMANTIC_VERSION,
        "completed": True,
        "profile": profile,
        "footnote_enabled": footnote_enabled,
        "marginal_detection_enabled": marginal_detection_enabled,
        "superscript_policy": superscript_policy,
        "footnote_reference_mode": "evidence_based",
        "alphabetic_marker_policy": "strong_only",
        "long_numeric_marker_policy": "strong_only",
        "resolved_counts": {key: value for key, value in counts.items() if value},
        "warnings": warnings,
    }
    return data


def _resolve_page(
    page: dict[str, Any],
    *,
    footnote_enabled: bool,
    marginal_detection_enabled: bool,
    counts: dict[str, int],
    warnings: list[str],
) -> None:
    blocks = [block for block in page.get("blocks", []) or [] if isinstance(block, dict)]
    footnotes = _prepare_blocks_and_collect_footnotes(
        blocks,
        marginal_detection_enabled=marginal_detection_enabled,
        counts=counts,
    )

    for block in blocks:
        block_type = str(block.get("type") or "")
        if block_type == "Footnote":
            continue
        if block_type in _INLINE_REFERENCE_EXCLUDED_TYPES:
            if block_type != "Equation":
                _unwrap_excluded_block_superscripts(block, block_type=block_type, counts=counts)
            continue
        _resolve_inline_superscripts(
            block,
            page_footnotes=footnotes,
            footnote_enabled=footnote_enabled,
            counts=counts,
            warnings=warnings,
        )


def _prepare_blocks_and_collect_footnotes(
    blocks: list[dict[str, Any]],
    *,
    marginal_detection_enabled: bool,
    counts: dict[str, int],
) -> dict[str, dict[str, Any]]:
    footnotes: dict[str, dict[str, Any]] = {}
    footnote_seq = 1
    for block in blocks:
        block_type = str(block.get("type") or "")
        attrs = _attrs(block)
        if block_type in _FOOTNOTE_EVIDENCE_EXCLUDED_TYPES:
            _append_unique(attrs, "excluded_from", "footnote_evidence")
            if block_type in {"PageHeader", "PageFooter", "PageNumber"}:
                _append_unique(attrs, "excluded_from", "marginal_detection")

        text = _block_text(block)
        if block_type == "Footnote":
            marker = _extract_leading_marker(text) or str(footnote_seq)
            marker_norm = _normalize_marker(marker)
            attrs["semantic_role"] = "footnote_definition"
            attrs["marker"] = marker
            attrs["marker_normalized"] = marker_norm
            attrs["footnote_confidence"] = "strong"
            attrs["footnote_evidence"] = _unique_list(
                list(attrs.get("footnote_evidence") or []) + ["block_type", "backend_label"]
            )
            footnotes.setdefault(marker_norm, block)
            footnote_seq += 1
            counts["footnote_definitions"] += 1
            continue

        if (
            marginal_detection_enabled
            and block_type == "MarginalNote"
            and re.fullmatch(r"\s*\d{1,4}\s*", text or "")
        ):
            marker = text.strip()
            attrs["semantic_role"] = "line_number"
            attrs["marker"] = marker
            attrs["marker_normalized"] = marker
            attrs["marginal_confidence"] = attrs.get("marginal_confidence", "medium")
            _append_unique(attrs, "excluded_from", "footnote_evidence")
            counts["marginal_line_numbers"] += 1
    return footnotes


def _unwrap_excluded_block_superscripts(
    block: dict[str, Any],
    *,
    block_type: str,
    counts: dict[str, int],
) -> None:
    text = block.get("text")
    if not isinstance(text, str) or "<sup" not in text.lower():
        return

    inline_marks: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        marker = _plain_marker(match.group(1))
        if not _is_marker(marker):
            return match.group(0)
        inline_marks.append(
            {
                "kind": "superscript",
                "text": marker,
                "semantic_role": "ordinary_text",
                "action": "unwrap_sup",
                "reason": f"{block_type.lower()}_excluded",
            }
        )
        counts["visual_superscripts_unwrapped"] += 1
        if block_type == "TableOfContents":
            counts["toc_page_numbers_unwrapped"] += 1
        return html.escape(marker, quote=False)

    new_text = _HTML_SUP_RE.sub(replace, text)
    if new_text != text:
        block["text"] = new_text
        _extend_inline_marks(block, inline_marks)


def _resolve_inline_superscripts(
    block: dict[str, Any],
    *,
    page_footnotes: dict[str, dict[str, Any]],
    footnote_enabled: bool,
    counts: dict[str, int],
    warnings: list[str],
) -> None:
    text = block.get("text")
    if not isinstance(text, str) or "<sup" not in text.lower():
        return

    inline_marks: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        marker = _plain_marker(match.group(1))
        if not _is_marker(marker):
            return match.group(0)

        marker_norm = _normalize_marker(marker)
        exact_footnote = page_footnotes.get(marker_norm)
        if not footnote_enabled:
            counts["visual_superscripts_unwrapped"] += 1
            inline_marks.append(_inline_mark(marker, "ordinary_text", "unwrap_sup", "footnote_disabled"))
            return html.escape(marker, quote=False)

        if exact_footnote is not None:
            counts["footnote_references"] += 1
            inline_marks.append(
                {
                    "kind": "superscript",
                    "text": marker,
                    "semantic_role": "footnote_reference",
                    "action": "preserve_sup",
                    "target_block_id": exact_footnote.get("id"),
                    "confidence": "strong",
                }
            )
            return match.group(0)

        if _looks_like_reference_context(text[: match.start()], marker):
            counts["visual_superscripts_unwrapped"] += 1
            inline_marks.append(_inline_mark(marker, "ordinary_text", "unwrap_sup", "reference_context"))
            return html.escape(marker, quote=False)

        if _is_single_alpha_marker(marker):
            counts["visual_superscripts_unwrapped"] += 1
            inline_marks.append(_inline_mark(marker, "ordinary_text", "unwrap_sup", "alphabetic_without_definition"))
            return html.escape(marker, quote=False)

        if _is_long_numeric_marker(marker):
            counts["visual_superscripts_unwrapped"] += 1
            inline_marks.append(_inline_mark(marker, "ordinary_text", "unwrap_sup", "long_numeric_without_definition"))
            return html.escape(marker, quote=False)

        counts["visual_superscripts"] += 1
        inline_marks.append(_inline_mark(marker, "visual_superscript", "preserve_sup", "no_matching_footnote"))
        return match.group(0)

    new_text = _HTML_SUP_RE.sub(replace, text)
    if inline_marks:
        _extend_inline_marks(block, inline_marks)
    if new_text != text:
        block["text"] = new_text
        warnings.append(
            f"Unwrapped superscript markers in block {block.get('id') or '(unknown)'}"
        )


def _inline_mark(marker: str, semantic_role: str, action: str, reason: str) -> dict[str, Any]:
    return {
        "kind": "superscript",
        "text": marker,
        "semantic_role": semantic_role,
        "action": action,
        "reason": reason,
    }


def _attrs(block: dict[str, Any]) -> dict[str, Any]:
    attrs = block.get("attrs")
    if not isinstance(attrs, dict):
        attrs = {}
        block["attrs"] = attrs
    return attrs


def _extend_inline_marks(block: dict[str, Any], marks: list[dict[str, Any]]) -> None:
    if not marks:
        return
    attrs = _attrs(block)
    existing = attrs.get("inline_marks")
    if not isinstance(existing, list):
        existing = []
    for mark in marks:
        if mark not in existing:
            existing.append(mark)
    attrs["inline_marks"] = existing


def _append_unique(attrs: dict[str, Any], key: str, value: str) -> None:
    values = attrs.get(key)
    if not isinstance(values, list):
        values = []
    if value not in values:
        values.append(value)
    attrs[key] = values


def _unique_list(values: list[Any]) -> list[Any]:
    output = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


def _block_text(block: dict[str, Any]) -> str:
    text = block.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    spans = block.get("spans")
    if isinstance(spans, list):
        pieces = [
            str(span.get("text") or "")
            for span in spans
            if isinstance(span, dict) and str(span.get("text") or "").strip()
        ]
        return " ".join(pieces).strip()
    return ""


def _extract_leading_marker(text: str) -> str | None:
    html_match = _LEADING_HTML_SUP_RE.match(text or "")
    if html_match:
        return html_match.group(1)
    match = _LEADING_MARKER_RE.match(text or "")
    if match:
        return match.group(1)
    return None


def _plain_marker(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", str(text or ""))).strip()


def _is_marker(value: str) -> bool:
    return bool(value and _MARKER_RE.fullmatch(value))


def _normalize_marker(value: str) -> str:
    marker = re.sub(r"[)\].-]+$", "", _plain_marker(value)).strip()
    if marker.isdigit():
        return str(int(marker)) if marker else marker
    return marker.lower()


def _is_single_alpha_marker(marker: str) -> bool:
    clean = _normalize_marker(marker)
    return len(clean) == 1 and clean.isalpha()


def _is_long_numeric_marker(marker: str) -> bool:
    clean = _normalize_marker(marker)
    return clean.isdigit() and len(clean) >= 3


def _looks_like_reference_context(prefix: str, marker: str) -> bool:
    clean = _normalize_marker(marker)
    if not clean.isdigit() or len(clean) < 2:
        return False
    context = _TAG_RE.sub("", prefix or "")[-80:]
    return bool(_REFERENCE_CONTEXT_RE.search(context))
