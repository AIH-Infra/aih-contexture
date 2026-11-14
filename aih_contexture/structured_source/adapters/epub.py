from __future__ import annotations

import io
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urldefrag

from lxml import etree, html

from ..errors import StructuredSourceError
from ..util import clean_text, local_name, safe_zip_member, sha256_bytes, stable_slug


MAX_ENTRIES = 20_000
MAX_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_RATIO = 200
CONTENT_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "table", "figure", "figcaption", "aside", "dt", "dd"}
FOOTNOTE_TOKENS = {"footnote", "footnotes", "fndef", "fn-def", "endnote", "endnotes"}
NOTEREF_TOKENS = {"fnanchor", "noteref", "note-ref", "footnote-ref"}


def _read_zip(zf: zipfile.ZipFile, name: str) -> bytes:
    normalized = posixpath.normpath(unquote(name)).lstrip("/")
    if not safe_zip_member(normalized):
        raise StructuredSourceError(f"Unsafe EPUB member path: {name}")
    try:
        return zf.read(normalized)
    except KeyError as exc:
        raise StructuredSourceError(f"Missing EPUB member: {normalized}") from exc


def _resolve(base: str, href: str) -> str:
    path, fragment = urldefrag(unquote(href))
    # A fragment-only reference (for example ``#Footnote_1``) targets an
    # element in the current spine document. Joining an empty path with the
    # directory would incorrectly resolve ``EPUB/c1.xhtml`` to ``EPUB``.
    if path:
        normalized = posixpath.normpath(posixpath.join(posixpath.dirname(base), path)).lstrip("/")
    else:
        normalized = posixpath.normpath(base).lstrip("/")
    if not safe_zip_member(normalized):
        raise StructuredSourceError(f"Unsafe EPUB reference: {href}")
    return normalized + (f"#{fragment}" if fragment else "")


def _typed_metadata(root: etree._Element, opf_path: str) -> dict[str, list[dict[str, Any]]]:
    mapping = {
        "title": "titles", "language": "languages", "date": "dates", "subject": "subjects",
        "rights": "rights", "description": "descriptions", "identifier": "identifiers",
    }
    result = {key: [] for key in ("titles", "agents", "languages", "dates", "publication", "subjects", "classifications", "rights", "descriptions", "revision_history", "identifiers")}
    for element in root.xpath('.//*[local-name()="metadata"]/*'):
        tag = local_name(element.tag).lower()
        value = clean_text(" ".join(element.itertext()))
        if not value:
            continue
        locator = {"href": opf_path, "xpath": element.getroottree().getpath(element)}
        if tag in {"creator", "contributor", "publisher"}:
            result["agents"].append({"name": value, "role": element.get("{http://www.idpf.org/2007/opf}role") or tag, "source_locator": locator})
        elif tag in mapping:
            result[mapping[tag]].append({"value": value, "type": element.get("{http://www.idpf.org/2007/opf}scheme") or tag, "source_locator": locator, "raw_value": value})
        else:
            result["publication"].append({"value": value, "type": tag, "source_locator": locator, "raw_value": value})
    return result


def _parse_ncx(data: bytes, ncx_path: str, namespace: str, href_to_anchor: dict[str, str]) -> list[dict[str, Any]]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=False)
    root = etree.fromstring(data, parser=parser)
    navigations = []
    specs = (("navMap", "source_toc"), ("pageList", "page_list"), ("navList", "other"))
    for container_name, kind in specs:
        containers = root.xpath(f'.//*[local-name()="{container_name}"]')
        for container_index, container in enumerate(containers):
            entries: list[dict[str, Any]] = []
            element_ids: dict[etree._Element, str] = {}
            candidates = container.xpath('.//*[local-name()="navPoint" or local-name()="pageTarget" or local-name()="navTarget"]')
            for node in candidates:
                entry_id = f"epub:{namespace}:nav-{kind}-{container_index + 1}-{len(entries) + 1}"
                element_ids[node] = entry_id
                label = clean_text(" ".join(node.xpath('./*[local-name()="navLabel"]//*[local-name()="text"]/text()')))
                src = next(iter(node.xpath('./*[local-name()="content"]/@src')), "")
                resolved = _resolve(ncx_path, src) if src else ""
                target = href_to_anchor.get(resolved) or href_to_anchor.get(urldefrag(resolved)[0])
                parent_node = next((a for a in node.iterancestors() if a in element_ids), None)
                entries.append({
                    "id": entry_id, "parent_id": element_ids.get(parent_node), "child_ids": [], "label": label or None,
                    "order": len(entries), "play_order": node.get("playOrder"), "target_anchor_id": target,
                    "raw_href": src, "resolved_href": resolved, "unresolved": target is None,
                })
            by_id = {entry["id"]: entry for entry in entries}
            for entry in entries:
                if entry["parent_id"] in by_id:
                    by_id[entry["parent_id"]]["child_ids"].append(entry["id"])
            if entries:
                navigations.append({
                    "id": f"nav:epub:{namespace}:{kind}-{container_index + 1}", "kind": kind, "source_format": "epub2_ncx",
                    "derived": False, "root_entry_ids": [e["id"] for e in entries if not e["parent_id"]], "entries": entries,
                    "sequence": len(navigations),
                })
    return navigations


def _epub_type(element: etree._Element) -> str:
    for key, value in element.attrib.items():
        if local_name(key).lower() == "type":
            return value.lower()
    return (element.get("role") or "").lower()


def _semantic_tokens(element: etree._Element, *, include_ancestors: bool = False) -> set[str]:
    nodes = [element, *element.iterancestors()] if include_ancestors else [element]
    tokens: set[str] = set()
    for node in nodes:
        values = [node.get("class") or "", node.get("id") or "", _epub_type(node)]
        for value in values:
            tokens.update(part.lower() for part in re.split(r"[^A-Za-z0-9_-]+", value) if part)
    return tokens


def _parse_epub3_nav(data: bytes, nav_path: str, namespace: str, href_to_anchor: dict[str, str]) -> list[dict[str, Any]]:
    try:
        doc = html.fromstring(data, base_url=nav_path)
    except (etree.ParserError, ValueError) as exc:
        raise StructuredSourceError(f"Cannot parse EPUB navigation document {nav_path}: {exc}") from exc
    navigations = []
    for nav_index, nav in enumerate(doc.xpath('.//*[local-name()="nav"]')):
        nav_type = _epub_type(nav)
        if "page-list" in nav_type or "pagebreak" in nav_type:
            kind = "page_list"
        elif "landmark" in nav_type:
            kind = "landmarks"
        elif "toc" in nav_type:
            kind = "source_toc"
        elif "index" in nav_type:
            kind = "index"
        else:
            kind = "other"
        entries: list[dict[str, Any]] = []
        li_ids: dict[etree._Element, str] = {}
        for li in nav.xpath('.//*[local-name()="li"]'):
            entry_id = f"epub:{namespace}:nav3-{nav_index + 1}-{len(entries) + 1}"
            li_ids[li] = entry_id
            link = next(iter(li.xpath('./*[local-name()="a" or local-name()="span"]')), None)
            raw_href = link.get("href") if link is not None and local_name(link.tag).lower() == "a" else ""
            resolved = _resolve(nav_path, raw_href) if raw_href else ""
            target = href_to_anchor.get(resolved) or href_to_anchor.get(urldefrag(resolved)[0])
            parent_li = next((a for a in li.iterancestors() if local_name(a.tag).lower() == "li" and a in li_ids), None)
            entries.append({
                "id": entry_id, "parent_id": li_ids.get(parent_li), "child_ids": [],
                "label": clean_text(" ".join(link.itertext())) if link is not None else None,
                "order": len(entries), "target_anchor_id": target, "raw_href": raw_href,
                "resolved_href": resolved, "unresolved": target is None,
            })
        by_id = {entry["id"]: entry for entry in entries}
        for entry in entries:
            if entry["parent_id"] in by_id:
                by_id[entry["parent_id"]]["child_ids"].append(entry["id"])
        if entries:
            navigations.append({
                "id": f"nav:epub:{namespace}:epub3-{nav_index + 1}", "kind": kind,
                "source_format": "epub3_nav", "derived": False,
                "root_entry_ids": [e["id"] for e in entries if not e["parent_id"]],
                "entries": entries, "sequence": len(navigations),
            })
    return navigations


def parse_epub(data: bytes, source_name: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise StructuredSourceError(f"Invalid EPUB ZIP: {exc}") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise StructuredSourceError("EPUB contains too many ZIP entries")
        total = 0
        for info in infos:
            if not safe_zip_member(info.filename):
                raise StructuredSourceError(f"Unsafe EPUB member path: {info.filename}")
            if info.flag_bits & 0x1:
                raise StructuredSourceError(f"Encrypted EPUB entry is unsupported: {info.filename}")
            total += info.file_size
            if info.file_size > 0 and info.compress_size == 0:
                raise StructuredSourceError("Suspicious EPUB compression metadata")
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
                raise StructuredSourceError(f"Suspicious EPUB compression ratio: {info.filename}")
        if total > MAX_UNCOMPRESSED:
            raise StructuredSourceError("EPUB uncompressed size exceeds safety limit")

        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=False)
        container = etree.fromstring(_read_zip(zf, "META-INF/container.xml"), parser=parser)
        opf_path = next(iter(container.xpath('.//*[local-name()="rootfile"]/@full-path')), None)
        if not opf_path:
            raise StructuredSourceError("EPUB container has no rootfile")
        opf_path = posixpath.normpath(opf_path).lstrip("/")
        opf_data = _read_zip(zf, opf_path)
        opf = etree.fromstring(opf_data, parser=parser)
        metadata = _typed_metadata(opf, opf_path)
        identifiers = metadata["identifiers"]
        source_record = next((item["value"] for item in identifiers), PurePosixPath(source_name).stem)
        namespace = stable_slug(source_record)
        digest = sha256_bytes(data)

        manifest: dict[str, dict[str, str]] = {}
        for item in opf.xpath('.//*[local-name()="manifest"]/*[local-name()="item"]'):
            item_id = item.get("id")
            href = item.get("href")
            if item_id and href:
                resolved = _resolve(opf_path, href).split("#", 1)[0]
                manifest[item_id] = {"href": resolved, "media_type": item.get("media-type") or "", "properties": item.get("properties") or ""}
        spine = opf.xpath('.//*[local-name()="spine"]')[0]
        spine_ids = [value for value in spine.xpath('./*[local-name()="itemref"]/@idref') if value in manifest]
        ncx_id = spine.get("toc")

        blocks: list[dict[str, Any]] = []
        structures: list[dict[str, Any]] = []
        structure_by_id: dict[str, dict[str, Any]] = {}
        anchors: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        href_to_anchor: dict[str, str] = {}
        for spine_index, item_id in enumerate(spine_ids):
            item = manifest[item_id]
            href = item["href"]
            content = _read_zip(zf, href)
            try:
                doc = html.fromstring(content, base_url=href)
            except (etree.ParserError, ValueError) as exc:
                raise StructuredSourceError(f"Cannot parse spine item {href}: {exc}") from exc
            sid = f"epub:{namespace}:spine-{spine_index + 1}"
            start_id = f"{sid}:start"
            end_id = f"{sid}:end"
            structures.append({
                "id": sid, "kind": "spine_item", "raw_kind": "spine_item", "title_block_ids": [], "parent_id": None,
                "child_ids": [], "range": {"start_anchor_id": start_id, "end_anchor_id": end_id},
                "source_locator": {"href": href}, "preorder": len(structures), "attrs": {"idref": item_id, "linear": True},
            })
            spine_structure = structures[-1]
            structure_by_id[sid] = spine_structure
            anchors.append({"id": start_id, "kind": "spine_start", "order": len(anchors), "block_order": len(blocks), "source_locator": {"href": href}})
            href_to_anchor[href] = start_id
            heading_nodes: list[tuple[str, int, int, str]] = []
            for element in doc.iter():
                if not isinstance(element.tag, str):
                    continue
                tag = local_name(element.tag).lower()
                element_id = element.get("id") or (element.get("name") if tag == "a" else None)
                if element_id:
                    fragment_hash = sha256_bytes(element_id.encode("utf-8"))[:10]
                    aid = f"epub:{namespace}:fragment-{spine_index + 1}-{stable_slug(element_id, 'anchor')}-{fragment_hash}"
                    anchors.append({"id": aid, "kind": "fragment", "label": element_id, "order": len(anchors), "block_order": len(blocks), "source_locator": {"href": href, "fragment": element_id}})
                    href_to_anchor[f"{href}#{element_id}"] = aid
                if tag not in CONTENT_TAGS or any(local_name(a.tag).lower() in CONTENT_TAGS for a in element.iterancestors() if isinstance(a.tag, str)):
                    continue
                value = clean_text(" ".join(element.itertext()))
                if not value:
                    continue
                if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
                    block_type = "SectionHeader"
                elif tag == "li":
                    block_type = "ListItem"
                elif tag == "blockquote":
                    block_type = "Quote"
                elif tag == "table":
                    block_type = "Table"
                elif tag == "figure":
                    block_type = "Figure"
                elif tag == "figcaption":
                    block_type = "Caption"
                elif _semantic_tokens(element, include_ancestors=True) & FOOTNOTE_TOKENS:
                    block_type = "Footnote"
                else:
                    block_type = "Text"
                bid = f"epub:{namespace}:block-{spine_index + 1}-{len(blocks) + 1}"
                depth = int(tag[1]) if block_type == "SectionHeader" else 1
                label_nodes = element.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " label ")]') if block_type == "Footnote" else []
                note_label = clean_text(" ".join(label_nodes[0].itertext())) if label_nodes else None
                blocks.append({
                    "id": bid, "type": block_type, "order": len(blocks), "parent_id": sid, "text": value,
                    "attrs": {"raw_tag": tag, "source_depth": depth, "class": element.get("class"), "note_label": note_label},
                    "source_locator": {"href": href, "fragment": element_id, "xpath": element.getroottree().getpath(element)},
                    "provenance": [{"backend": "epub-native", "stage": "document"}],
                })
                if block_type == "SectionHeader":
                    if not spine_structure["title_block_ids"]:
                        spine_structure["title_block_ids"].append(bid)
                    heading_nodes.append((bid, depth, blocks[-1]["order"], element.getroottree().getpath(element)))
                for link in element.xpath('.//a[@href]'):
                    raw_target = link.get("href")
                    resolved_target = _resolve(href, raw_target)
                    link_tokens = _semantic_tokens(link)
                    relations.append({
                        "id": f"epub:{namespace}:relation-{len(relations) + 1}",
                        "kind": "footnote_reference" if link_tokens & NOTEREF_TOKENS or "footnote_" in raw_target.lower() else "hyperlink",
                        "source_block_id": bid, "raw_target": raw_target, "resolved_target": resolved_target,
                        "target_anchor_id": None, "unresolved": True, "label": clean_text(" ".join(link.itertext())) or None,
                        "sequence": len(relations),
                    })
            spine_end_order = len(blocks)
            anchors.append({"id": end_id, "kind": "spine_end", "order": len(anchors), "block_order": spine_end_order, "source_locator": {"href": href}})
            heading_structure_ids: list[str] = []
            level_stack: list[tuple[int, str]] = []
            for heading_index, (bid, depth, block_order, xpath) in enumerate(heading_nodes):
                while level_stack and level_stack[-1][0] >= depth:
                    level_stack.pop()
                parent_id = level_stack[-1][1] if level_stack else sid
                heading_sid = f"epub:{namespace}:section-{spine_index + 1}-{heading_index + 1}"
                heading_structure_ids.append(heading_sid)
                next_order = next((order for _, next_depth, order, _ in heading_nodes[heading_index + 1:] if next_depth <= depth), spine_end_order)
                heading_start = f"{heading_sid}:start"
                heading_end = f"{heading_sid}:end"
                structures.append({
                    "id": heading_sid, "kind": "section", "raw_kind": f"h{depth}", "title_block_ids": [bid],
                    "parent_id": parent_id, "child_ids": [], "range": {"start_anchor_id": heading_start, "end_anchor_id": heading_end},
                    "source_locator": {"href": href, "xpath": xpath}, "preorder": len(structures),
                })
                structure_by_id[heading_sid] = structures[-1]
                structure_by_id[parent_id]["child_ids"].append(heading_sid)
                anchors.extend([
                    {"id": heading_start, "kind": "range_start", "order": len(anchors), "block_order": block_order, "source_locator": {"href": href, "xpath": xpath}},
                    {"id": heading_end, "kind": "range_end", "order": len(anchors) + 1, "block_order": next_order, "source_locator": {"href": href, "xpath": xpath}},
                ])
                level_stack.append((depth, heading_sid))

        navigations: list[dict[str, Any]] = []
        if ncx_id and ncx_id in manifest:
            ncx_path = manifest[ncx_id]["href"]
            navigations.extend(_parse_ncx(_read_zip(zf, ncx_path), ncx_path, namespace, href_to_anchor))
        nav_items = [item for item in manifest.values() if "nav" in item.get("properties", "").split()]
        for nav_item in nav_items:
            for navigation in _parse_epub3_nav(_read_zip(zf, nav_item["href"]), nav_item["href"], namespace, href_to_anchor):
                navigation["sequence"] = len(navigations)
                navigations.append(navigation)
        guide_entries = []
        for ref in opf.xpath('.//*[local-name()="guide"]/*[local-name()="reference"]'):
            raw_href = ref.get("href") or ""
            resolved = _resolve(opf_path, raw_href) if raw_href else ""
            guide_entries.append({
                "id": f"epub:{namespace}:guide-{len(guide_entries) + 1}", "parent_id": None, "child_ids": [],
                "label": ref.get("title") or ref.get("type"), "order": len(guide_entries), "raw_href": raw_href,
                "target_anchor_id": href_to_anchor.get(resolved) or href_to_anchor.get(urldefrag(resolved)[0]),
                "unresolved": not (href_to_anchor.get(resolved) or href_to_anchor.get(urldefrag(resolved)[0])), "type": ref.get("type"),
            })
        if guide_entries:
            navigations.append({"id": f"nav:epub:{namespace}:landmarks", "kind": "landmarks", "source_format": "epub2_guide", "derived": False, "root_entry_ids": [e["id"] for e in guide_entries], "entries": guide_entries, "sequence": len(navigations)})

        anchor_by_id = {anchor["id"]: anchor for anchor in anchors}
        for relation in relations:
            resolved_target = relation.get("resolved_target") or ""
            target_anchor = href_to_anchor.get(resolved_target) or href_to_anchor.get(urldefrag(resolved_target)[0])
            relation["target_anchor_id"] = target_anchor
            relation["unresolved"] = target_anchor is None
        for navigation in navigations:
            if navigation.get("kind") != "page_list":
                continue
            for page_number, entry in enumerate(navigation.get("entries", []), 1):
                target_anchor = anchor_by_id.get(entry.get("target_anchor_id"))
                if not target_anchor:
                    continue
                page_label = entry.get("label") or target_anchor.get("label")
                if not page_label:
                    continue
                printed_id = f"epub:{namespace}:printed-page-{page_number}"
                printed_anchor = {
                    "id": printed_id, "kind": "printed_page", "label": page_label,
                    "order": len(anchors), "block_order": target_anchor.get("block_order"),
                    "source_locator": dict(target_anchor.get("source_locator") or {}),
                    "attrs": {
                        "evidence": navigation.get("source_format"),
                        "target_anchor_id": target_anchor["id"],
                        "raw_label": entry.get("label"),
                    },
                }
                anchors.append(printed_anchor)
                anchor_by_id[printed_id] = printed_anchor
                entry["target_anchor_id"] = printed_id

        block_by_id = {block["id"]: block for block in blocks}
        generated_entries = []
        section_ids = {structure["id"] for structure in structures if structure["kind"] == "section"}
        for structure in structures:
            if structure["id"] not in section_ids:
                continue
            title = block_by_id[structure["title_block_ids"][0]]["text"]
            parent_entry_id = f"nav-generated:{structure['parent_id']}" if structure["parent_id"] in section_ids else None
            generated_entries.append({
                "id": f"nav-generated:{structure['id']}", "parent_id": parent_entry_id,
                "child_ids": [f"nav-generated:{child}" for child in structure["child_ids"] if child in section_ids],
                "label": title, "order": len(generated_entries), "target_anchor_id": structure["range"]["start_anchor_id"],
                "raw_href": None, "unresolved": False,
            })
        if generated_entries:
            navigations.append({
                "id": f"nav:epub:{namespace}:generated", "kind": "generated_toc", "source_format": "xhtml_headings",
                "derived": True, "root_entry_ids": [entry["id"] for entry in generated_entries if not entry["parent_id"]],
                "entries": generated_entries, "sequence": len(navigations),
            })

        resources = [{"id": item_id, **value} for item_id, value in sorted(manifest.items())]
        artifacts = {"raw_opf.xml": opf_data}
        document = {
            "schema_version": "contexture-source-document/0.1", "id": f"source-document:epub:{namespace}",
            "source": {"name": source_name, "format": "epub", "profile": "gutenberg_epub2" if ncx_id else "epub_native", "media_type": "application/epub+zip", "sha256": digest, "source_record_id": source_record, "original_artifact": f"sha256:{digest}"},
            "identity": {"work_id": None, "expression_id": None, "manifestation_id": f"manifestation:epub:{namespace}", "identifiers": identifiers, "merge_status": "unresolved"},
            "metadata": metadata, "raw_metadata": [{"path": "raw_opf.xml", "sha256": sha256_bytes(opf_data)}],
            "blocks": blocks, "structures": structures, "navigations": navigations, "indexes": [], "anchors": anchors,
            "relations": relations, "resources": resources, "provenance": [{"backend": "epub-native", "stage": "document"}], "extensions": {"opf_version": opf.get("version")},
        }
        return document, artifacts
