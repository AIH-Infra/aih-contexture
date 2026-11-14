from __future__ import annotations

from typing import Any

from .errors import StructuredSourceError


ARRAY_KEYS = ("blocks", "structures", "navigations", "indexes", "anchors", "relations")


def validate_source_document(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != "contexture-source-document/0.1":
        errors.append("invalid schema_version")
    if not document.get("id"):
        errors.append("missing document id")
    if not isinstance(document.get("source"), dict):
        errors.append("missing source object")
    for key in ARRAY_KEYS:
        values = document.get(key)
        if not isinstance(values, list):
            errors.append(f"{key} must be an array")
            continue
        ids = [item.get("id") for item in values if isinstance(item, dict) and item.get("id")]
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate ids in {key}")
    orders = [item.get("order") for item in document.get("blocks", [])]
    if orders != list(range(len(orders))):
        errors.append("block order must be contiguous from zero")
    block_ids = {item.get("id") for item in document.get("blocks", [])}
    anchor_ids = {item.get("id") for item in document.get("anchors", [])}
    anchor_by_id = {item.get("id"): item for item in document.get("anchors", [])}
    structure_ids = {item.get("id") for item in document.get("structures", [])}
    structure_by_id = {item.get("id"): item for item in document.get("structures", [])}
    for block in document.get("blocks", []):
        parent_id = block.get("parent_id")
        if parent_id and parent_id not in structure_ids:
            errors.append(f"block references missing structure: {parent_id}")
    for anchor in document.get("anchors", []):
        page_range = anchor.get("range") or {}
        if page_range:
            if page_range.get("semantics") != "half_open":
                errors.append(f"anchor range must be half_open: {anchor.get('id')}")
            for key in ("start_anchor_id", "end_anchor_id"):
                if page_range.get(key) and page_range[key] not in anchor_ids:
                    errors.append(f"anchor range references missing anchor: {page_range[key]}")
            if anchor.get("kind") == "digital_page":
                start_id = page_range.get("start_anchor_id")
                end_id = page_range.get("end_anchor_id")
                if anchor.get("id") in {start_id, end_id}:
                    errors.append(f"digital_page must reference independent boundary anchors: {anchor.get('id')}")
                start = anchor_by_id.get(start_id, {})
                end = anchor_by_id.get(end_id, {})
                if start and start.get("kind") != "page_boundary":
                    errors.append(f"digital_page start must be page_boundary: {anchor.get('id')}")
                if end and end.get("kind") not in {"page_boundary", "document_end"}:
                    errors.append(f"digital_page end must be page_boundary or document_end: {anchor.get('id')}")
                if start and end and int(start.get("block_order", 0)) > int(end.get("block_order", 0)):
                    errors.append(f"digital_page range is reversed: {anchor.get('id')}")
        elif anchor.get("kind") == "digital_page":
            errors.append(f"digital_page must define a half-open range: {anchor.get('id')}")
    digital_labels = [anchor.get("label") for anchor in document.get("anchors", []) if anchor.get("kind") == "digital_page"]
    if digital_labels != [str(index) for index in range(1, len(digital_labels) + 1)]:
        errors.append("digital_page labels must be contiguous from one")
    for structure in document.get("structures", []):
        parent_id = structure.get("parent_id")
        if parent_id and parent_id not in structure_ids:
            errors.append(f"structure references missing parent: {parent_id}")
        if parent_id and structure.get("id") not in structure_by_id[parent_id].get("child_ids", []):
            errors.append(f"structure parent/child mismatch: {structure.get('id')}")
        for child_id in structure.get("child_ids", []):
            if child_id not in structure_ids:
                errors.append(f"structure references missing child: {child_id}")
            elif structure_by_id[child_id].get("parent_id") != structure.get("id"):
                errors.append(f"structure child/parent mismatch: {child_id}")
        for block_id in structure.get("title_block_ids", []):
            if block_id not in block_ids:
                errors.append(f"structure title references missing block: {block_id}")
        range_value = structure.get("range") or {}
        for key in ("start_anchor_id", "end_anchor_id"):
            if range_value.get(key) and range_value[key] not in anchor_ids:
                errors.append(f"structure references missing anchor: {range_value[key]}")
    navigation_entry_ids: set[str] = set()
    for navigation in document.get("navigations", []):
        for entry in navigation.get("entries", []):
            entry_id = entry.get("id")
            if entry_id in navigation_entry_ids:
                errors.append(f"duplicate navigation entry id: {entry_id}")
            navigation_entry_ids.add(entry_id)
            target = entry.get("target_anchor_id")
            if target and target not in anchor_ids:
                errors.append(f"navigation references missing anchor: {target}")
            if not target and not entry.get("unresolved", False):
                errors.append(f"navigation target lacks unresolved marker: {entry_id}")
    for relation in document.get("relations", []):
        source_block_id = relation.get("source_block_id")
        if source_block_id and source_block_id not in block_ids:
            errors.append(f"relation references missing source block: {source_block_id}")
        target_block_id = relation.get("target_block_id")
        if target_block_id and target_block_id not in block_ids:
            errors.append(f"relation references missing target block: {target_block_id}")
    for index in document.get("indexes", []):
        entry_ids = {entry.get("id") for entry in index.get("entries", [])}
        if len(entry_ids) != len(index.get("entries", [])):
            errors.append(f"duplicate index entry id in {index.get('id')}")
        for entry in index.get("entries", []):
            for locator in entry.get("locators", []):
                target = locator.get("target_anchor_id")
                if target and target not in anchor_ids:
                    errors.append(f"index locator references missing anchor: {target}")
                if not target and not locator.get("unresolved", False):
                    errors.append(f"index locator lacks unresolved marker: {entry.get('id')}")
    return errors


def assert_valid_source_document(document: dict[str, Any]) -> None:
    errors = validate_source_document(document)
    if errors:
        raise StructuredSourceError("Source Document validation failed: " + "; ".join(errors[:20]))
