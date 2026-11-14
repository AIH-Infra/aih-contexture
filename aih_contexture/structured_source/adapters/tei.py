from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from lxml import etree

from ..errors import StructuredSourceError
from ..util import clean_text, local_name, sha256_bytes, stable_slug


BLOCK_TAGS = {"p", "head", "item", "l", "lg", "quote", "q", "note", "table", "figure", "ab", "argument", "epigraph", "label", "salute", "signed", "trailer"}
STRUCTURE_TAGS = {"front", "body", "back", "div", "div1", "div2", "div3", "div4", "div5", "div6", "div7"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _xpath(element: etree._Element) -> str:
    return element.getroottree().getpath(element)


def _profile(root: etree._Element) -> str:
    header_text = clean_text(" ".join(root.xpath('.//*[local-name()="teiHeader"]//text()'))).lower()
    if "deutsches textarchiv" in header_text or "deutschestextarchiv" in header_text:
        return "dta_tei"
    if "text creation partnership" in header_text or "tcp" in header_text:
        return "tcp_tei"
    return "tei_p5_generic"


def _block_type(element: etree._Element) -> str:
    tag = local_name(element.tag).lower()
    if tag == "head":
        return "SectionHeader"
    if tag == "item":
        return "ListItem"
    if tag in {"quote", "q", "epigraph"}:
        return "Quote"
    if tag == "table":
        return "Table"
    if tag == "figure":
        return "Figure"
    if tag == "note":
        place = (element.get("place") or "").lower()
        if place in {"foot", "bottom", "end"}:
            return "Footnote"
        if place in {"margin", "left", "right", "outer", "inner"}:
            return "MarginalNote"
    return "Text"


def _block_text(element: etree._Element) -> str:
    if local_name(element.tag).lower() == "note":
        return clean_text(" ".join(element.itertext()))

    def collect(node: etree._Element) -> list[str]:
        parts = [node.text or ""]
        for child in node:
            if isinstance(child.tag, str) and local_name(child.tag).lower() == "note":
                parts.append(child.get("n") or "")
            elif isinstance(child.tag, str):
                parts.extend(collect(child))
            parts.append(child.tail or "")
        return parts

    return clean_text(" ".join(collect(element)))


def _typed_values(elements: list[etree._Element], kind: str = "main") -> list[dict[str, Any]]:
    values = []
    for element in elements:
        value = clean_text(" ".join(element.itertext()))
        if value:
            values.append({
                "value": value,
                "type": element.get("type") or kind,
                "language": element.get(XML_ID.replace("id", "lang")) or element.get("{http://www.w3.org/XML/1998/namespace}lang"),
                "source_locator": {"xpath": _xpath(element)},
                "raw_value": value,
            })
    return values


def parse_tei_xml(data: bytes, source_name: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False, huge_tree=False, recover=False)
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise StructuredSourceError(f"Invalid or unsafe XML: {exc}") from exc
    if local_name(root.tag).lower() not in {"tei", "tei.2"}:
        raise StructuredSourceError("XML input is not a TEI document")

    digest = sha256_bytes(data)
    profile = _profile(root)
    identifiers = _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="idno"]'), "source")
    source_record = next((item["value"] for item in identifiers), Path(source_name).stem)
    namespace = stable_slug(source_record)
    document_id = f"source-document:tei:{namespace}"
    header = root.xpath('./*[local-name()="teiHeader"]')
    metadata = {
        "titles": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="titleStmt"]/*[local-name()="title"]')),
        "agents": [],
        "languages": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="language"]'), "content"),
        "dates": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="date"]'), "source"),
        "publication": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="publicationStmt"]/*'), "statement"),
        "subjects": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="term"]'), "keyword"),
        "classifications": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="classCode"]'), "classCode"),
        "rights": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="availability"]'), "availability"),
        "descriptions": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="sourceDesc"]'), "source"),
        "revision_history": _typed_values(root.xpath('.//*[local-name()="teiHeader"]//*[local-name()="revisionDesc"]/*'), "change"),
        "identifiers": identifiers,
    }
    for role in ("author", "editor", "respStmt", "principal", "funder"):
        for item in root.xpath(f'.//*[local-name()="teiHeader"]//*[local-name()="{role}"]'):
            value = clean_text(" ".join(item.itertext()))
            if value:
                metadata["agents"].append({"name": value, "role": role, "source_locator": {"xpath": _xpath(item)}})

    blocks: list[dict[str, Any]] = []
    structures: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    indexes: list[dict[str, Any]] = []
    pending_indexes: list[tuple[etree._Element, int]] = []
    page_boundaries: list[dict[str, Any]] = []
    xml_id_to_anchor: dict[str, str] = {}
    element_structure: dict[etree._Element, str] = {}
    element_block: dict[etree._Element, str] = {}
    structure_by_id: dict[str, dict[str, Any]] = {}
    structure_orders: defaultdict[str, list[int]] = defaultdict(list)
    counters: defaultdict[str, int] = defaultdict(int)
    text_roots = root.xpath('./*[local-name()="text"]')
    if not text_roots:
        raise StructuredSourceError("TEI document has no direct text element")

    for element in text_roots[0].iter():
        if not isinstance(element.tag, str):
            continue
        tag = local_name(element.tag).lower()
        if tag in STRUCTURE_TAGS:
            counters[tag] += 1
            sid = f"tei:{namespace}:structure-{tag}-{counters[tag]}"
            parent = next((element_structure[a] for a in element.iterancestors() if a in element_structure), None)
            child_ids: list[str] = []
            structure = {
                "id": sid, "kind": (element.get("type") or tag), "raw_kind": element.get("type") or tag,
                "title_block_ids": [], "parent_id": parent, "child_ids": child_ids,
                "range": {}, "source_locator": {"xpath": _xpath(element)}, "preorder": len(structures),
            }
            structures.append(structure)
            structure_by_id[sid] = structure
            element_structure[element] = sid
            if parent:
                structure_by_id[parent]["child_ids"].append(sid)

        if tag == "pb":
            counters["page_boundary"] += 1
            boundary_id = f"tei:{namespace}:anchor-page_boundary-{counters['page_boundary']}"
            boundary = {
                "id": boundary_id, "kind": "page_boundary", "label": None,
                "order": len(anchors), "block_order": len(blocks), "source_locator": {"xpath": _xpath(element)},
                "attrs": {local_name(key): value for key, value in element.attrib.items()},
            }
            anchors.append(boundary)
            page_boundaries.append(boundary)
            if element.get("n"):
                counters["printed_page"] += 1
                anchors.append({
                    "id": f"tei:{namespace}:anchor-printed_page-{counters['printed_page']}",
                    "kind": "printed_page", "label": element.get("n"), "order": len(anchors),
                    "block_order": len(blocks), "source_locator": {"xpath": _xpath(element)},
                    "attrs": {"boundary_anchor_id": boundary_id, "evidence": "tei_pb_n", "raw_label": element.get("n")},
                })
            if element.get(XML_ID):
                xml_id_to_anchor[element.get(XML_ID)] = boundary_id
        elif element.get(XML_ID):
            counters["fragment"] += 1
            aid = f"tei:{namespace}:anchor-fragment-{counters['fragment']}"
            anchors.append({
                "id": aid, "kind": "fragment", "label": element.get(XML_ID), "order": len(anchors),
                "block_order": len(blocks), "source_locator": {"xpath": _xpath(element)},
                "attrs": {local_name(key): value for key, value in element.attrib.items()},
            })
            xml_id_to_anchor[element.get(XML_ID)] = aid

        if tag == "index":
            pending_indexes.append((element, len(blocks)))

        block_ancestor = any(local_name(a.tag).lower() in BLOCK_TAGS for a in element.iterancestors() if isinstance(a.tag, str))
        if tag in BLOCK_TAGS and (tag == "note" or not block_ancestor):
            value = _block_text(element)
            if not value:
                continue
            counters[tag] += 1
            bid = f"tei:{namespace}:block-{tag}-{counters[tag]}"
            parent = next((element_structure[a] for a in element.iterancestors() if a in element_structure), None)
            depth = sum(1 for a in element.iterancestors() if isinstance(a.tag, str) and local_name(a.tag).lower() in STRUCTURE_TAGS)
            block = {
                "id": bid, "type": _block_type(element), "order": len(blocks), "parent_id": parent,
                "text": value, "attrs": {"raw_tag": tag, "source_depth": max(1, depth), **{local_name(k): v for k, v in element.attrib.items()}},
                "source_locator": {"xpath": _xpath(element)}, "provenance": [{"backend": profile, "stage": "document"}],
            }
            blocks.append(block)
            element_block[element] = bid
            for ancestor in element.iterancestors():
                if ancestor in element_structure:
                    structure_orders[element_structure[ancestor]].append(block["order"])
            if element in element_structure:
                structure_orders[element_structure[element]].append(block["order"])
            if tag == "head" and parent:
                structure_by_id[parent]["title_block_ids"].append(bid)
            if tag == "note":
                containing_block_id = next((element_block[a] for a in element.iterancestors() if a in element_block), None)
                if containing_block_id:
                    relations.append({
                        "id": f"tei:{namespace}:relation-{len(relations) + 1}", "kind": "footnote_reference",
                        "source_block_id": containing_block_id, "target_block_id": bid,
                        "label": element.get("n"), "source_locator": {"xpath": _xpath(element)},
                        "sequence": len(relations), "unresolved": False,
                    })

        if tag in {"ref", "ptr"} and element.get("target"):
            relations.append({
                "id": f"tei:{namespace}:relation-{len(relations) + 1}", "kind": "reference",
                "source_block_id": blocks[-1]["id"] if blocks else None, "raw_target": element.get("target"),
                "source_locator": {"xpath": _xpath(element)}, "sequence": len(relations),
            })

    for structure in structures:
        path = structure["source_locator"]["xpath"]
        descendant_orders = structure_orders[structure["id"]]
        start = min(descendant_orders) if descendant_orders else len(blocks)
        end = max(descendant_orders) + 1 if descendant_orders else start
        start_id = f"{structure['id']}:start"
        end_id = f"{structure['id']}:end"
        anchors.extend([
            {"id": start_id, "kind": "range_start", "order": len(anchors), "block_order": start, "source_locator": {"xpath": path}},
            {"id": end_id, "kind": "range_end", "order": len(anchors) + 1, "block_order": end, "source_locator": {"xpath": path}},
        ])
        structure["range"] = {"start_anchor_id": start_id, "end_anchor_id": end_id}

    if page_boundaries:
        document_end_id = f"tei:{namespace}:anchor-document-end"
        anchors.append({
            "id": document_end_id, "kind": "document_end", "order": len(anchors),
            "block_order": len(blocks), "source_locator": {"xpath": "/"},
        })
        printed_by_boundary = {
            anchor.get("attrs", {}).get("boundary_anchor_id"): anchor
            for anchor in anchors if anchor.get("kind") == "printed_page"
        }
        for index, boundary in enumerate(page_boundaries):
            printed = printed_by_boundary.get(boundary["id"])
            attrs = {
                "label_source": "derived_page_boundary_sequence",
                "start_boundary_id": boundary["id"],
            }
            if boundary.get("attrs", {}).get("facs"):
                attrs["facs"] = boundary["attrs"]["facs"]
            if printed:
                attrs["printed_page"] = printed["label"]
                attrs["printed_page_anchor_id"] = printed["id"]
            anchors.append({
                "id": f"tei:{namespace}:digital-page-{index + 1}", "kind": "digital_page",
                "label": str(index + 1), "order": len(anchors), "block_order": boundary["block_order"],
                "range": {
                    "start_anchor_id": boundary["id"],
                    "end_anchor_id": page_boundaries[index + 1]["id"] if index + 1 < len(page_boundaries) else document_end_id,
                    "semantics": "half_open",
                },
                "source_locator": dict(boundary["source_locator"]), "attrs": attrs,
            })

    index_groups: defaultdict[str, list[tuple[etree._Element, int]]] = defaultdict(list)
    for index_element, block_order in pending_indexes:
        index_groups[index_element.get("indexName") or index_element.get("type") or "default"].append((index_element, block_order))
    for group_name, group_items in index_groups.items():
        entries = []
        for index_element, block_order in group_items:
            terms = index_element.xpath('./*[local-name()="term"]') or [index_element]
            for term in terms:
                label = clean_text(" ".join(term.itertext()))
                if not label:
                    continue
                entry_id = f"tei:{namespace}:index-entry-{len(entries) + 1}-{stable_slug(label, 'term')}"
                prior_anchors = [a for a in anchors if a.get("block_order", -1) <= block_order and a.get("kind") in {"printed_page", "page_boundary", "fragment"}]
                nearest_anchor = prior_anchors[-1]["id"] if prior_anchors else None
                raw_targets = [value.lstrip("#") for value in index_element.xpath('.//@target | .//@corresp')]
                locators = []
                for raw_target in raw_targets:
                    locators.append({"label": raw_target, "target_anchor_id": xml_id_to_anchor.get(raw_target), "unresolved": raw_target not in xml_id_to_anchor})
                if not locators and nearest_anchor:
                    locators.append({"label": None, "target_anchor_id": nearest_anchor, "unresolved": False})
                entries.append({
                    "id": entry_id, "parent_id": None, "child_ids": [], "label": label,
                    "sort_key": term.get("sortKey") or label.casefold(), "locators": locators,
                    "see": [clean_text(" ".join(node.itertext())) for node in index_element.xpath('.//*[local-name()="see"]')],
                    "see_also": [clean_text(" ".join(node.itertext())) for node in index_element.xpath('.//*[local-name()="seeAlso"]')],
                    "source_locator": {"xpath": _xpath(term)}, "order": len(entries),
                })
        indexes.append({
            "id": f"tei:{namespace}:index-{len(indexes) + 1}-{stable_slug(group_name)}", "kind": "back_of_book",
            "source_evidence": "tei_index", "root_entry_ids": [entry["id"] for entry in entries],
            "entries": entries, "label": group_name, "sequence": len(indexes),
        })

    generated_entries = []
    block_by_id = {block["id"]: block for block in blocks}
    for structure in structures:
        title = next((block_by_id[block_id]["text"] for block_id in structure["title_block_ids"] if block_id in block_by_id), None)
        generated_entries.append({
            "id": f"nav-generated:{structure['id']}", "parent_id": f"nav-generated:{structure['parent_id']}" if structure["parent_id"] else None,
            "child_ids": [f"nav-generated:{item}" for item in structure["child_ids"]], "label": title,
            "order": len(generated_entries), "target_anchor_id": structure["range"].get("start_anchor_id"), "unresolved": False,
        })
    navigations = [{
        "id": f"nav:tei:{namespace}:generated", "kind": "generated_toc", "source_format": "tei_structure",
        "derived": True, "root_entry_ids": [e["id"] for e in generated_entries if not e["parent_id"]], "entries": generated_entries, "sequence": 0,
    }]
    raw_header = etree.tostring(header[0], encoding="utf-8", xml_declaration=True) if header else b""
    artifacts = {"raw_tei_header.xml": raw_header} if raw_header else {}
    document = {
        "schema_version": "contexture-source-document/0.1", "id": document_id,
        "source": {"name": source_name, "format": "xml", "profile": profile, "media_type": "application/tei+xml", "sha256": digest, "source_record_id": source_record, "original_artifact": f"sha256:{digest}"},
        "identity": {"work_id": None, "expression_id": None, "manifestation_id": f"manifestation:tei:{namespace}", "identifiers": identifiers, "merge_status": "unresolved"},
        "metadata": metadata, "raw_metadata": [{"path": "raw_tei_header.xml", "sha256": sha256_bytes(raw_header)}] if raw_header else [],
        "blocks": blocks, "structures": structures, "navigations": navigations, "indexes": indexes, "anchors": anchors,
        "relations": relations, "resources": [], "provenance": [{"backend": profile, "stage": "document"}], "extensions": {},
    }
    return document, artifacts
