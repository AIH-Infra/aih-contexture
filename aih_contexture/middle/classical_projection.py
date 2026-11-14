"""Derived projections for classical marginalia rendering and semantic reads.

The input Middle JSON remains untouched. Edit plans are checked against their
recorded source text before they are applied to a rendering copy.
"""
from __future__ import annotations

from aih_contexture.middle.storage import decode_middle_storage

import copy
import re
from typing import Any, Mapping


def _text(block: Mapping[str, Any]) -> str:
    value = block.get("text")
    if isinstance(value, str):
        return value
    spans = block.get("spans")
    if isinstance(spans, list):
        return " ".join(str(s.get("text") or "") for s in spans if isinstance(s, Mapping))
    return ""


def prepare_classical_render_view(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy and apply validated character edits for the reading view."""
    data = decode_middle_storage(data)
    view = copy.deepcopy(data)
    for page in view.get("pages", []) if isinstance(view.get("pages"), list) else []:
        if not isinstance(page, dict):
            continue
        attrs = page.get("attrs") if isinstance(page.get("attrs"), dict) else {}
        analysis = attrs.get("classical_marginalia")
        if not isinstance(analysis, dict):
            continue
        blocks = {str(b.get("id") or ""): b for b in page.get("blocks", []) if isinstance(b, dict)}
        from aih_contexture.middle.native_geometry import native_edit_supported
        for item in analysis.get('native_body_prefixes', []):
            source, target = item.get('source') or {}, item.get('target') or {}
            valid = all(word.get('block_id') in blocks and native_edit_supported(blocks[word['block_id']],
                        {'original':word.get('raw'),'char_range':word.get('char_range'),'bbox':word.get('bbox')})
                        for word in (source,target))
            if valid and target.get('char_range', [None])[0] == 0:
                blocks[target['block_id']].setdefault('attrs', {})['classical_body_prefix'] = source['raw']
        edits_by_block: dict[str, list[dict[str, Any]]] = {}
        for edit in analysis.get("edits", []) or []:
            if isinstance(edit, dict) and edit.get("action") in {"remove_locator_token", "remove_text", "separate_native_margin"}:
                edits_by_block.setdefault(str(edit.get("block_id") or ""), []).append(edit)

        diagnostics: list[dict[str, Any]] = []
        expected_source_fingerprint = str(analysis.get("source_fingerprint") or "")
        applied_native_spans = set()
        blocked_native_spans = set()
        native_notes = []
        for number, note in enumerate(analysis.get('native_footnotes') or []):
            from aih_contexture.middle.native_geometry import native_edit_supported
            fragments = note.get('fragments') or []
            source_matches = fragments and all(
                f.get('block_id') in blocks and native_edit_supported(blocks[f['block_id']],
                    {'original':f.get('raw'),'char_range':f.get('char_range'),'bbox':f.get('bbox')})
                for f in fragments)
            edits_match = all(any(
                edit.get('action')=='separate_native_margin'
                and edit.get('char_range')==f.get('char_range')
                and edit.get('original')==f.get('raw') and edit.get('bbox')==f.get('bbox')
                and edit.get('source_fingerprint')==expected_source_fingerprint
                for edit in edits_by_block.get(f.get('block_id'),[])) for f in fragments)
            if not source_matches or not edits_match:
                blocked_native_spans.update((f.get('block_id'), *f['char_range']) for f in fragments
                    if isinstance(f.get('char_range'),list) and len(f['char_range'])==2)
                diagnostics.append({'kind':'native_footnote_source_mismatch'})
                continue
            source = blocks[fragments[0]['block_id']]
            restored = copy.deepcopy(source)
            restored.update(id=f"{source['id']}::native-footnote-{number}",type='Footnote',
                text=' '.join(f['raw'] for f in fragments),bbox=note['bbox'],
                order=float(source.get('order') or 0)+.5)
            restored.pop('spans', None)
            restored['attrs'] = {'semantic_role':'footnote_definition',
                'footnote_evidence':list(note.get('evidence') or []),'native_source_fragments':fragments}
            native_notes.append(restored)
        for block_id, edits in edits_by_block.items():
            block = blocks.get(block_id)
            if block is None:
                diagnostics.append({"kind": "missing_source_block", "block_id": block_id})
                continue
            original = _text(block)
            valid: list[tuple[int, int, int]] = []
            for edit in edits:
                evidence = edit.get("evidence")
                evidence = [str(value) for value in evidence] if isinstance(evidence, list) else []
                has_supported_evidence = any(
                    value in {"human_page_audit", "pdf_word:margin_position"}
                    or value.startswith("position:")
                    or value.startswith("geometry:")
                    or value.startswith("shape:")
                    or value.startswith("sequence:")
                    or value.startswith("pitch_match:")
                    for value in evidence
                )
                action = str(edit.get("action") or "")
                if action == 'separate_native_margin':
                    if (block_id, *(edit.get('char_range') or [])) in blocked_native_spans:
                        continue
                    from aih_contexture.middle.native_geometry import native_edit_supported
                    if not native_edit_supported(block, edit):
                        diagnostics.append({'kind':'native_span_edit_mismatch','block_id':block_id})
                        continue
                if action == "remove_text" and "human_page_audit" not in evidence:
                    diagnostics.append({"kind": "human_text_edit_without_human_evidence", "block_id": block_id, "edit": edit})
                    continue
                if action not in {"remove_locator_token", "remove_text", "separate_native_margin"}:
                    diagnostics.append({"kind": "unsupported_edit_action", "block_id": block_id, "edit": edit})
                    continue
                if (
                    not expected_source_fingerprint
                    or str(edit.get("source_fingerprint") or "") != expected_source_fingerprint
                ):
                    diagnostics.append({"kind": "edit_source_fingerprint_missing_or_mismatched", "block_id": block_id, "edit": edit})
                    continue
                if not evidence or not has_supported_evidence:
                    diagnostics.append({"kind": "edit_evidence_missing_or_unsupported", "block_id": block_id, "edit": edit})
                    continue
                span = edit.get("char_range")
                expected = str(edit.get("original") or "")
                if not isinstance(span, (list, tuple)) or len(span) != 2:
                    diagnostics.append({"kind": "invalid_char_range", "block_id": block_id, "edit": edit})
                    continue
                try:
                    start, end = int(span[0]), int(span[1])
                except (TypeError, ValueError):
                    diagnostics.append({"kind": "invalid_char_range", "block_id": block_id, "edit": edit})
                    continue
                if start < 0 or end <= start or end > len(original) or original[start:end] != expected:
                    diagnostics.append({"kind": "source_text_mismatch", "block_id": block_id, "char_range": [start, end], "expected": expected})
                    continue
                valid.append((start, end, len(valid)))
            # Ignore exact duplicate rows, but reject every member of any
            # overlapping group so the outcome never depends on row order.
            unique: list[tuple[int, int, int]] = []
            seen_spans: set[tuple[int, int]] = set()
            for start, end, idx in valid:
                if (start, end) in seen_spans:
                    continue
                seen_spans.add((start, end))
                unique.append((start, end, idx))
            unique.sort(key=lambda item: (item[0], item[1], item[2]))
            overlapping: set[int] = set()
            for i, (start, end, idx) in enumerate(unique):
                for other_start, other_end, other_idx in unique[i + 1:]:
                    if other_start >= end:
                        break
                    if start < other_end and other_start < end:
                        overlapping.update((idx, other_idx))
            for idx in sorted(overlapping):
                start, end, _ = valid[idx]
                diagnostics.append({"kind": "overlapping_edits", "block_id": block_id, "char_range": [start, end]})
            accepted = [(start, end) for start, end, idx in unique if idx not in overlapping]
            char_list = list(enumerate(original))
            for start, end in reversed(accepted):
                actual_start, actual_end = start, end
                curr_str = "".join(c for _, c in char_list)
                if (
                    actual_start > 0
                    and curr_str[actual_start - 1] == "\n"
                    and actual_end < len(curr_str)
                    and curr_str[actual_end] == "\n"
                ):
                    actual_end += 1
                elif (
                    actual_end < len(curr_str)
                    and curr_str[actual_end] == " "
                    and (actual_start == 0 or curr_str[actual_start - 1] in {"\n", " "})
                ):
                    actual_end += 1
                del char_list[actual_start:actual_end]
                applied_native_spans.add((block_id, start, end))
            rendered = "".join(c for _, c in char_list)
            if rendered != original:
                lstrip_count = len(rendered) - len(rendered.lstrip(" \t\r\n"))
                rstrip_count = len(rendered) - len(rendered.rstrip(" \t\r\n"))
                end_idx = len(char_list) - rstrip_count if rstrip_count else len(char_list)
                surviving_chars = char_list[lstrip_count:end_idx]
                block["text"] = "".join(c for _, c in surviving_chars)

                # Keep word spans and character ranges in sync without collapsing
                # the whole block into a single token box or losing prose geometry.
                if isinstance(block.get("spans"), list):
                    orig_to_new = {orig_idx: new_idx for new_idx, (orig_idx, _) in enumerate(surviving_chars)}
                    cursor = 0
                    for span in block["spans"]:
                        if not isinstance(span, dict):
                            continue
                        raw = str(span.get("text") or "")
                        attrs = span.setdefault("attrs", {})
                        claimed = attrs.get("char_range")
                        has_claim = claimed is not None
                        if isinstance(claimed, (list, tuple)) and len(claimed) == 2:
                            try:
                                s_orig, e_orig = int(claimed[0]), int(claimed[1])
                                if not (0 <= s_orig < e_orig <= len(original)
                                        and original[s_orig:e_orig] == raw):
                                    s_orig, e_orig = -1, -1
                            except (ValueError, TypeError):
                                s_orig, e_orig = -1, -1
                        else:
                            s_orig, e_orig = -1, -1
                        if s_orig < 0 and raw and not has_claim:
                            clean_raw = raw.rstrip("\r\n")
                            s_orig = original.find(clean_raw, cursor) if clean_raw else -1
                            e_orig = s_orig + len(clean_raw) if s_orig >= 0 else -1
                        if s_orig >= 0:
                            cursor = e_orig
                            surviving_indices = [orig_to_new[k] for k in range(s_orig, e_orig) if k in orig_to_new]
                            if surviving_indices and len(surviving_indices) == e_orig - s_orig:
                                new_s = surviving_indices[0]
                                new_e = surviving_indices[-1] + 1
                                span_text = block["text"][new_s:new_e]
                                if span_text.strip():
                                    span["text"] = span_text
                                    attrs["char_range"] = [new_s, new_e]
                                else:
                                    span["text"] = ""
                                    attrs.pop("char_range", None)
                            else:
                                span["text"] = ""
                                attrs.pop("char_range", None)
                        else:
                            span["text"] = ""
                            attrs.pop("char_range", None)

        _insert_restored_fragments(page, analysis, blocks, diagnostics)
        for note in native_notes:
            if all((f['block_id'], *f['char_range']) in applied_native_spans
                   for f in note['attrs']['native_source_fragments']):
                page['blocks'].append(note)
            else:
                diagnostics.append({'kind':'native_footnote_edit_not_applied'})

        if diagnostics:
            analysis["render_diagnostics"] = diagnostics
    return view


def _insert_restored_fragments(
    page: dict[str, Any],
    analysis: Mapping[str, Any],
    blocks_by_id: Mapping[str, dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> None:
    blocks = page.get("blocks", [])
    existing_ids = {str(block.get("id") or "") for block in blocks if isinstance(block, Mapping)}
    existing_restore_keys = {
        (
            str((block.get("attrs") or {}).get("classical_restore_source_id") or ""),
            tuple((block.get("attrs") or {}).get("classical_restore_char_range") or ()),
        )
        for block in blocks
        if isinstance(block, Mapping) and isinstance(block.get("attrs"), Mapping)
    }
    candidates: list[dict[str, Any]] = []
    for item in analysis.get("restores", []) or []:
        if not isinstance(item, Mapping):
            continue
        source_id = str(item.get("block_id") or "")
        source = blocks_by_id.get(source_id)
        span = item.get("char_range")
        if source is None or not isinstance(span, (list, tuple)) or len(span) != 2:
            continue
        try:
            start, end = int(span[0]), int(span[1])
        except (TypeError, ValueError):
            continue
        original = _text(source)
        raw = str(item.get("raw") or "")
        if start < 0 or end <= start or end > len(original) or original[start:end] != raw:
            diagnostics.append({"kind": "restore_source_text_mismatch", "block_id": source_id, "char_range": list(span)})
            continue
        if (source_id, (start, end)) in existing_restore_keys:
            continue
        bbox = item.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            diagnostics.append({"kind": "restore_missing_bbox", "block_id": source_id, "char_range": [start, end]})
            continue
        try:
            center_y = (float(bbox[1]) + float(bbox[3])) / 2
        except (TypeError, ValueError):
            diagnostics.append({"kind": "restore_invalid_bbox", "block_id": source_id, "char_range": [start, end]})
            continue

        body_blocks = [
            block for block in blocks
            if isinstance(block, dict)
            and str(block.get("type") or "") not in {"MarginalNote", "PageHeader", "PageFooter", "PageNumber"}
            and isinstance(block.get("bbox"), (list, tuple)) and len(block["bbox"]) == 4
        ]
        positioned = []
        for block in body_blocks:
            try:
                y = (float(block["bbox"][1]) + float(block["bbox"][3])) / 2
                order = float(block.get("order", 0))
            except (TypeError, ValueError):
                continue
            positioned.append((y, order, block))
        before = max((entry for entry in positioned if entry[0] <= center_y), key=lambda e: e[0], default=None)
        after = min((entry for entry in positioned if entry[0] > center_y), key=lambda e: e[0], default=None)
        source_order = float(source.get("order", 0) or 0)
        if before and after and after[1] > before[1]:
            order = (before[1] + after[1]) / 2
        elif before:
            order = before[1] + 0.5
        elif after:
            order = after[1] - 0.5
        else:
            order = source_order
        synthetic_id = f"{source_id}::classical-restore-{start}-{end}"
        suffix = 1
        while synthetic_id in existing_ids:
            suffix += 1
            synthetic_id = f"{source_id}::classical-restore-{start}-{end}-{suffix}"
        existing_ids.add(synthetic_id)
        restored = copy.deepcopy(source)
        restored.update({"id": synthetic_id, "type": "Text", "order": order, "text": raw, "bbox": list(bbox)})
        restored.pop("spans", None)
        attrs = restored.get("attrs") if isinstance(restored.get("attrs"), dict) else {}
        attrs["classical_restore_source_id"] = source_id
        attrs["classical_restore_char_range"] = [start, end]
        attrs["classical_restore_evidence"] = list(item.get("evidence", []) or [])
        restored["attrs"] = attrs
        candidates.append(restored)
        existing_restore_keys.add((source_id, (start, end)))
    blocks.extend(candidates)


def semantic_body_projection(
    data: dict[str, Any], *, include_text_marginalia: bool = False
) -> dict[str, Any]:
    """Return a Middle JSON projection for semantic consumers.

    Page locators and running furniture are excluded; page/index mappings and
    original blocks remain available. ComplexRegion and Footnote content are
    retained. Text marginalia is opt-in and never concatenated by default.
    """
    result = copy.deepcopy(data)
    result = prepare_classical_render_view(result)
    for page in result.get("pages", []) if isinstance(result.get("pages"), list) else []:
        if not isinstance(page, dict):
            continue
        attrs = page.get("attrs") if isinstance(page.get("attrs"), dict) else {}
        analysis = attrs.get("classical_marginalia")
        marginal_by_id: dict[str, list[Mapping[str, Any]]] = {}
        if isinstance(analysis, Mapping):
            for item in analysis.get("text_marginalia", []) or []:
                if isinstance(item, Mapping) and item.get("block_id"):
                    marginal_by_id.setdefault(str(item["block_id"]), []).append(item)
        kept = []
        for block in page.get("blocks", []) or []:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "")
            block_id = str(block.get("id") or "")
            if kind in {"PageHeader", "PageFooter", "PageNumber", "LineNumber"}:
                continue
            if kind == "MarginalNote":
                # Restores are already inserted as ordered Text blocks by the
                # shared derived-view projection above.
                if include_text_marginalia:
                    for item in sorted(marginal_by_id.get(block_id, []), key=lambda i: _reading_item_key(i)):
                        raw = str(item.get("raw") or "").strip()
                        if raw:
                            margin = copy.deepcopy(block)
                            margin["text"] = raw
                            margin.pop("spans", None)
                            kept.append(margin)
                continue
            if block_id and str(block.get("type") or "") == "Text" and not _text(block).strip():
                locator_ids = {
                    str(item.get("block_id") or "")
                    for item in (analysis.get("locators", []) or [])
                    if isinstance(item, Mapping) and item.get("block_id")
                } if isinstance(analysis, Mapping) else set()
                if block_id in locator_ids:
                    continue
            if isinstance(block.get("text"), str):
                block["text"] = re.sub(r"<!--[\s\S]*?-->", "", block["text"]).strip()
            if isinstance(block.get("spans"), list):
                for span in block["spans"]:
                    if isinstance(span, dict) and isinstance(span.get("text"), str):
                        span["text"] = re.sub(r"<!--[\s\S]*?-->", "", span["text"]).strip()
            kept.append(block)
        page["blocks"] = sorted(kept, key=lambda b: (float(b.get("order", 0)), str(b.get("id") or "")))
    # HTML comments are presentation metadata, never semantic body content.
    if isinstance(result.get("markdown"), str):
        result["markdown"] = re.sub(r"<!--[\s\S]*?-->", "", result["markdown"])
    return result


def _reading_item_key(item: Mapping[str, Any]) -> tuple[float, int]:
    bbox = item.get("bbox")
    y = float(bbox[1]) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else float("inf")
    span = item.get("char_range")
    start = int(span[0]) if isinstance(span, (list, tuple)) and len(span) == 2 else 0
    return y, start


def semantic_body_text(data: dict[str, Any], *, include_text_marginalia: bool = False) -> str:
    """Flatten the semantic body projection while preserving physical page labels."""
    projection = semantic_body_projection(data, include_text_marginalia=include_text_marginalia)
    pieces: list[str] = []
    for page in projection.get("pages", []) or []:
        if not isinstance(page, Mapping):
            continue
        page_index = page.get("index")
        pieces.append(f"[page:{page_index}]")
        for block in page.get("blocks", []) or []:
            if isinstance(block, Mapping):
                value = _text(block).strip()
                if value:
                    pieces.append(value)
    return "\n".join(pieces)
