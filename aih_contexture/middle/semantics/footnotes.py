from __future__ import annotations

from aih_contexture.middle.storage import decode_middle_storage

import copy
import html
import re
import hashlib
import json
from typing import Any
from aih_contexture.utils.markdown_regions import transform_prose_regions
from aih_contexture.utils.storage_numbers import storage_numbers

from aih_contexture.utils.footnote_markers import (
    match_leading_footnote_marker,
    normalize_footnote_marker,
)
from aih_contexture.middle.semantics.page_furniture import (
    PAGE_FURNITURE_VERSION,
    DocumentFurnitureContext,
    review_page_furniture,
)


FOOTNOTE_SEMANTIC_VERSION = "footnote-superscript/0.8"

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
    resolved = resolve_document_semantics(
        middle_json,
        footnote_enabled=bool(config.get("footnote_enabled", True)),
        marginal_detection_enabled=bool(config.get("marginal_detection_enabled", True)),
        superscript_policy=str(config.get("superscript_policy", "footnote_safe")),
        profile=str(config.get("semantic_profile", "humanities")),
        force=force,
    )
    if isinstance(resolved, dict):
        from aih_contexture.middle.page_folios import annotate_observed_folios
        annotate_observed_folios(resolved)
    return resolved


def resolve_document_semantics(
    middle_json: dict[str, Any],
    *,
    footnote_enabled: bool = True,
    marginal_detection_enabled: bool = True,
    superscript_policy: str = "footnote_safe",
    profile: str = "humanities",
    force: bool = False,
) -> dict[str, Any]:
    middle_json = decode_middle_storage(middle_json)
    if not isinstance(middle_json, dict):
        return middle_json

    from aih_contexture.middle.semantics.recorded_annotations import normalize_recorded_annotations
    middle_json = storage_numbers(middle_json)
    normalize_recorded_annotations(middle_json)
    metadata = middle_json.get("metadata")
    source_fingerprint = _semantic_source_fingerprint(middle_json)
    requested = {
        'profile': profile, 'footnote_enabled': footnote_enabled,
        'marginal_detection_enabled': marginal_detection_enabled,
        'superscript_policy': superscript_policy,
    }
    if (
        not force
        and isinstance(metadata, dict)
        and isinstance(metadata.get("semantic_resolution"), dict)
        and metadata["semantic_resolution"].get("version") == FOOTNOTE_SEMANTIC_VERSION
        and metadata['semantic_resolution'].get('page_furniture_version') == PAGE_FURNITURE_VERSION
        and metadata["semantic_resolution"].get("completed") is True
        and all(metadata['semantic_resolution'].get(key) == value for key, value in requested.items())
        and metadata['semantic_resolution'].get('source_fingerprint') == source_fingerprint
    ):
        return middle_json  # Numeric normalization already owns a private tree.

    data = middle_json  # Already a private copy, normalized above.
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
        "page_footers_reviewed": 0,
        "footnotes_pending_verification": 0,
    }
    warnings: list[str] = []
    previous_resolution = metadata.get('semantic_resolution') if isinstance(metadata, dict) else None

    def source_blocks(blocks):
        for block in blocks or []:
            if not isinstance(block, dict):
                continue
            attrs = _attrs(block)
            furniture = attrs.get('semantic_furniture_source') or attrs.get('page_furniture_review')
            if isinstance(furniture, dict):
                originals = furniture.get('original_attributes') or {}
                for key in ('footnote_confidence', 'footnote_status', 'excluded_from'):
                    if key in originals:
                        attrs[key] = copy.deepcopy(originals[key])
                    else:
                        attrs.pop(key, None)
                attrs.pop('page_furniture_review', None)
                attrs.pop('semantic_furniture_source', None)
            previous_marks = attrs.get('inline_marks') or []
            if 'semantic_source_text' in attrs:
                if block.get('text') == attrs.get('semantic_rendered_text'):
                    block['text'] = attrs['semantic_source_text']
                else:
                    # A caller edited the source text since the previous read.
                    attrs['semantic_source_text'] = str(block.get('text') or '')
                attrs.pop('inline_marks', None)
            elif footnote_enabled and any(mark.get('reason') == 'footnote_disabled'
                    for mark in previous_marks if isinstance(mark, dict)):
                warnings.append('historical_superscript_source_unavailable')
            if 'semantic_source_type' in attrs:
                if block.get('type') == attrs.get('semantic_rendered_type'):
                    block['type'] = attrs['semantic_source_type']
                else:
                    attrs['semantic_source_type'] = str(block.get('type') or '')
                attrs.pop('page_furniture_review', None)
            if isinstance(previous_resolution, dict) and previous_resolution.get('completed'):
                attrs.pop('inline_marks', None)
            yield block
            yield from source_blocks(block.get('children'))

    for page in pages:
        if isinstance(page, dict):
            list(source_blocks(page.get('blocks')))

    doc_context = DocumentFurnitureContext(pages)

    for page in pages:
        if not isinstance(page, dict):
            continue
        _resolve_page(
            page,
            doc_context=doc_context,
            footnote_enabled=footnote_enabled,
            marginal_detection_enabled=marginal_detection_enabled,
            counts=counts,
            warnings=warnings,
        )
        for block in _walk_semantic_blocks(page.get('blocks')):
            attrs = _attrs(block)
            if 'semantic_source_text' in attrs:
                attrs['semantic_rendered_text'] = str(block.get('text') or '')

    data.setdefault("metadata", {})["semantic_resolution"] = {
        "version": FOOTNOTE_SEMANTIC_VERSION,
        "page_furniture_version": PAGE_FURNITURE_VERSION,
        "completed": True,
        "source_fingerprint": _semantic_source_fingerprint(data),
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


def _walk_semantic_blocks(blocks):
    for block in blocks or []:
        if isinstance(block, dict):
            yield block
            yield from _walk_semantic_blocks(block.get('children'))


def _semantic_source_fingerprint(data: dict[str, Any]) -> str:
    def source_block(block):
        attrs = block.get('attrs') or {}
        text = _block_text(block)
        if block.get('text') == attrs.get('semantic_rendered_text') and 'semantic_source_text' in attrs:
            text = attrs['semantic_source_text']
        block_type = attrs.get('semantic_source_type') if (
            'semantic_source_type' in attrs and block.get('type') == attrs.get('semantic_rendered_type')
        ) else block.get('type')
        from aih_contexture.middle.native_geometry import compact_native_spans
        # Layout is now semantic evidence too: edited geometry or upstream
        # confidence must invalidate the furniture decision after a reload.
        return {'id': block.get('id'), 'type': block_type, 'text': text,
                'bbox': block.get('bbox'), 'confidence': block.get('confidence'),
                'coordinate_space': attrs.get('coordinate_space'),
                'spans': compact_native_spans({**block, 'text': text}),
                'children': [source_block(child) for child in block.get('children') or [] if isinstance(child, dict)]}
    pages = data.get('pages')
    payload = [{'index': page.get('index'), 'width': page.get('width'), 'height': page.get('height'),
                'blocks': [source_block(b) for b in page.get('blocks') or [] if isinstance(b, dict)]}
               for page in (pages if isinstance(pages, list) else []) if isinstance(page, dict)]
    return hashlib.sha256(json.dumps(storage_numbers(payload), ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _retain_semantic_source(block: dict[str, Any], text: str) -> None:
    _attrs(block).setdefault('semantic_source_text', text)


def normalize_legacy_markdown_footnote_definitions(
    markdown: str,
    middle_json: dict[str, Any],
) -> str:
    """Repair legacy Markdown markers using resolved Middle footnote evidence.

    The legacy HTML renderer can preserve a PDF's visual ``<b>25</b>`` marker
    even when Middle semantics has already identified the block as a Footnote.
    Convert only a bold marker whose following body matches a resolved
    footnote definition; unrelated bold numbered prose remains untouched.
    """
    definitions: dict[str, list[str]] = {}
    for page in (middle_json or {}).get("pages", []):
        for block in page.get("blocks", []):
            if str(block.get("type") or "") != "Footnote":
                continue
            text = str(block.get("text") or "")
            marker_match = match_leading_footnote_marker(text)
            attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
            marker = attrs.get("marker_normalized") or (
                marker_match.normalized if marker_match else None
            )
            if not marker:
                continue
            body = text[marker_match.body_start :] if marker_match else text
            definitions.setdefault(str(marker), []).append(_normalize_legacy_text(body))

    if not definitions:
        return markdown

    line_re = re.compile(r"^(?P<indent>\s*)\*\*(?P<marker>[^*\n]+)\*\*(?P<rest>\s+.+?)\s*$", re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        marker = normalize_footnote_marker(match.group("marker"))
        if marker is None or marker not in definitions:
            return match.group(0)
        rest = _normalize_legacy_text(match.group("rest"))
        if not rest:
            return match.group(0)
        if not any(_legacy_prefix_matches(rest, body) for body in definitions[marker]):
            return match.group(0)
        return f"{match.group('indent')}<sup>{marker}</sup>{match.group('rest')}"

    return line_re.sub(replace, str(markdown or ""))


def _normalize_legacy_text(value: str) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[*_`]+", "", value)
    return re.sub(r"\s+", " ", value).strip().casefold()


def _legacy_prefix_matches(left: str, right: str) -> bool:
    if not left or not right:
        return False
    sample_left = left[:120]
    sample_right = right[:120]
    return sample_left.startswith(sample_right) or sample_right.startswith(sample_left)

def _resolve_page(
    page: dict[str, Any],
    *,
    doc_context: DocumentFurnitureContext | None = None,
    footnote_enabled: bool,
    marginal_detection_enabled: bool,
    counts: dict[str, int],
    warnings: list[str],
) -> None:
    if doc_context is not None:
        review_page_furniture(page, doc_context, counts=counts)
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
            if block_type in {'PageHeader', 'PageFooter', 'PageNumber', 'TableOfContents'}:
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
    for block in blocks:
        block_type = str(block.get("type") or "")
        attrs = _attrs(block)
        if block_type in _FOOTNOTE_EVIDENCE_EXCLUDED_TYPES:
            _append_unique(attrs, "excluded_from", "footnote_evidence")
            if block_type in {"PageHeader", "PageFooter", "PageNumber"}:
                _append_unique(attrs, "excluded_from", "marginal_detection")

        text = _block_text(block)
        if block_type == "Footnote":
            if attrs.get('footnote_status') == 'unconfirmed':
                attrs['semantic_role'] = 'footnote_pending_verification'
                # An uncertain note cannot establish a made-up numeric call.
                continue
            candidate = match_leading_footnote_marker(text, allow_ambiguous_alpha=True)
            alpha_evidence = False
            if candidate and candidate.style in {'alpha', 'roman'}:
                reference = re.compile(r'<sup>\s*' + re.escape(candidate.original) + r'\s*</sup>', re.I)
                alpha_evidence = any(reference.search(_block_text(other)) for other in blocks
                                     if other.get('type') in {'Text', 'ListItem'})
                if not alpha_evidence:
                    from aih_contexture.middle.native_geometry import compact_native_spans
                    spans = compact_native_spans(block)
                    alpha_evidence = bool(spans and (spans[0].get('attrs') or {}).get('has_superscript'))
            match = match_leading_footnote_marker(text, allow_ambiguous_alpha=alpha_evidence)
            marker = match.original if match else None
            if not marker:
                attrs['footnote_status'] = 'unconfirmed'
                attrs['semantic_role'] = 'footnote_pending_verification'
                attrs.pop('marker', None)
                attrs.pop('marker_normalized', None)
                continue
            marker_norm = _normalize_marker(marker)
            attrs["semantic_role"] = "footnote_definition"
            attrs["marker"] = marker
            attrs["marker_normalized"] = marker_norm
            if attrs.get("footnote_confidence") != "pending_verification":
                attrs["footnote_confidence"] = "strong"
                attrs["footnote_evidence"] = _unique_list(
                    list(attrs.get("footnote_evidence") or []) + ["block_type", "backend_label"]
                )
            footnotes.setdefault(marker_norm, block)
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
        _retain_semantic_source(block, text)
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
    context = [text]

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

        if _looks_like_reference_context(context[0][: match.start()], marker):
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

    def process(segment):
        context[0] = segment
        return _HTML_SUP_RE.sub(replace, segment)
    new_text = transform_prose_regions(text, process)
    if inline_marks:
        _extend_inline_marks(block, inline_marks)
    if new_text != text:
        _retain_semantic_source(block, text)
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
    marker = match_leading_footnote_marker(text or "")
    return marker.original if marker is not None else None


def _plain_marker(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", str(text or ""))).strip()


def _is_marker(value: str) -> bool:
    return normalize_footnote_marker(value) is not None


def _normalize_marker(value: str) -> str:
    marker = normalize_footnote_marker(value)
    return marker if marker is not None else _plain_marker(value).lower()


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
