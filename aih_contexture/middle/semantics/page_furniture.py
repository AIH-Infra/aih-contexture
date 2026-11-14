from __future__ import annotations

import math
import re
from typing import Any

from aih_contexture.middle.classical_capabilities import classical_bbox_is_trustworthy
from aih_contexture.utils.footnote_markers import match_leading_footnote_marker

PAGE_FURNITURE_VERSION = "page-furniture/0.4"

_CITATION_INDICATOR_RE = re.compile(
    r"(?:\b(?:cf\.|vgl\.|see\b|ibid\.|ibidem|ebd\.?|ebenda|op\.?\s*cit|loc\.?\s*cit|passim|infra|supra|"
    r"p\.\s*\d|pp\.\s*\d|s\.\s*\d|ss\.\s*\d|folio|fol\.|chap\.|ch\.|anm\.|ed\.|trans\.|hrsg\.|"
    r"ff\.|f\.|v\.|vv\.|cap\.|art\.|sec\.|sect\.)|[\"“”«»])",
    re.IGNORECASE,
)

_SHEET_SIGNATURE_RE = re.compile(
    r"^(?P<num>\d{1,4}|[A-Z]{1,2})(?P<mark>[*+†])?\s+"
    r"(?P<title>(?:[A-Za-z\u00C0-\u024F'’.-]+\s+){1,6})"
    r"(?P<vol>(?:[IVXLCDM1li|]{1,12}(?:[./,\\]\s*\d+)*(?:/\d+[.,]\d+)?|(?:Vol|Bd|Band|Tom|Tome|Teil|T|Part|Pt)\.?\s*[IVXLCDMivxlcdm0-9]+(?:[./,\\]\s*\d+)*))\.?$",
    re.IGNORECASE,
)

_SHORT_SIGNATURE_RE = re.compile(
    r"^(?P<num>\d{1,4}|[A-Z]{1,2})(?P<mark>[*+†])$"
)


def parse_signature_mark(text: str) -> dict[str, str] | None:
    """Parse sheet signature marks without hardcoding specific book titles.

    Sheet signatures (Bogensignaturen) typically consist of:
    - A sheet / gathering number or letter (e.g. 41, 59, 35, B)
    - Optional mark indicating leaf (e.g. *, +)
    - Work title / abbreviation (e.g. Kant's Schriften, Opera Omnia)
    - Volume / series designation (e.g. XXVIII/2,1, Vol. II)
    """
    if not text or not isinstance(text, str):
        return None
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean or len(clean) > 80:
        return None
    if _CITATION_INDICATOR_RE.search(clean):
        return None

    m = _SHEET_SIGNATURE_RE.match(clean)
    if m:
        vol = m.group("vol")
        # In signature marks, parts are volume divisions (e.g. XXVIII/2,1).
        # A trailing comma followed by 2 or more digits indicates a page/verse citation (e.g. VII, 403 or 11,21).
        if re.search(r",\s*\d{2,}", vol):
            return None
        title = (m.group("title") or "").strip()
        # A short reference such as "10 Meditation II." is indistinguishable
        # from a one-word title here; leave its native footnote role intact.
        if len(title.split()) < 2 or not re.search(r"[A-Za-z\u00C0-\u024F]", title):
            return None
        return {
            "type": "full_signature",
            "sheet_number": m.group("num"),
            "mark": m.group("mark") or "",
            "title": title,
            "volume": vol.strip(),
        }

    m = _SHORT_SIGNATURE_RE.match(clean)
    if m:
        return {
            "type": "short_signature",
            "sheet_number": m.group("num"),
            "mark": m.group("mark") or "",
            "title": "",
            "volume": "",
        }
    return None


class DocumentFurnitureContext:
    """Document-wide layout and page-furniture context extracted across all pages."""

    def __init__(self, pages: list[dict[str, Any]]):
        self.known_footer_templates: list[dict[str, Any]] = []
        self.page_body_refs: dict[int, set[str]] = {}
        self.page_max_body_y1: dict[int, float] = {}

        for page in pages:
            if not isinstance(page, dict):
                continue
            p_idx = page.get("index", 0)
            blocks = page.get("blocks", [])
            body_refs: set[str] = set()
            max_y1 = 0.0

            for b in blocks:
                if not isinstance(b, dict):
                    continue
                b_type = str(b.get("type") or "")
                bbox = b.get("bbox")
                if bbox and len(bbox) == 4:
                    if b_type in ("Text", "SectionHeader", "Paragraph", "ListItem", "Table", "Form"):
                        if classical_bbox_is_trustworthy(bbox, page, b) and bbox[3] > max_y1:
                            max_y1 = bbox[3]

                t = str(b.get("text") or "")
                if b_type == "PageFooter":
                    sig = parse_signature_mark(t)
                    if sig and sig.get("title") and _bottom_signature_geometry(page, b, 0):
                        self.known_footer_templates.append({**sig, 'page_index': p_idx,
                            'relative_x': bbox[0] / page['width'], 'relative_y': bbox[1] / page['height']})
                elif b_type not in ("Footnote", "PageHeader", "PageNumber"):
                    for ref_m in re.finditer(r"<sup>\s*([0-9]{1,4}|[*†‡§¶#]+)\s*</sup>", t, re.IGNORECASE):
                        body_refs.add(ref_m.group(1).strip())
                    for ref_m in re.finditer(r"\[\^([0-9]{1,4})\]", t):
                        body_refs.add(ref_m.group(1).strip())
                    for span in b.get('spans') or []:
                        if (span.get('attrs') or {}).get('has_superscript'):
                            marker = str(span.get('text') or '').strip()
                            if marker:
                                body_refs.add(marker)

            self.page_body_refs[p_idx] = body_refs
            self.page_max_body_y1[p_idx] = max_y1


def _bottom_signature_geometry(page, block, body_bottom):
    box = block.get('bbox')
    if not classical_bbox_is_trustworthy(box, page, block):
        return False
    height = float(page['height'])
    return (box[1] >= height * .85 and box[3] - box[1] <= height * .033
            and box[1] >= body_bottom - height * .008)


def _volume_key(value):
    # Common OCR substitutions within a Roman volume token, not within parts.
    head, *parts = re.split(r'([/.,\\])', value.strip().upper())
    if re.search(r'[IVXLCDM]', head):
        head = head.replace('1', 'I').replace('|', 'I')
    return head + ''.join(parts).replace(' ', '')


def is_publication_imprint(text: str, page_text: str) -> bool:
    """Require an imprint prefix and two independent copyright-page cues."""
    return bool(
        re.match(r'^(?:Satz\s+und\s+Druck|Druck\s+und\s+Verlag|Printed\s+by)\b', text.strip(), re.I)
        and re.search(r'Alle\s+Rechte|all\s+rights\s+reserved', page_text, re.I)
        and re.search(r'Archiv[-\s]*Nr|©|\bcopyright\b|\bPrinted\s+in\b', page_text, re.I)
        and not match_leading_footnote_marker(text))


def review_page_furniture(
    page: dict[str, Any],
    doc_context: DocumentFurnitureContext,
    *,
    counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Review blocks within a page for page furniture misclassifications.

    Conservative rule:
    1. Footnotes that meet geometric, text pattern, and unanchored criteria,
       and match a document-wide footer template or recurring signature pattern,
       are reviewed and reclassified as PageFooter.
    2. Signature-shaped notes without a matching independent page footer are
       retained as pending verification; confidence alone never changes roles.
    3. True footnotes and coordinate-less inputs are preserved safely.
    """
    reviews: list[dict[str, Any]] = []
    p_idx = page.get("index", 0)
    blocks = page.get("blocks", [])

    for block in blocks:
        if not isinstance(block, dict):
            continue
        attrs = block.setdefault("attrs", {})
        orig_type = attrs.get("semantic_source_type") or block.get("type")
        if orig_type != "Footnote":
            continue

        text = str(block.get("text") or "").strip()
        bbox = block.get("bbox")
        conf = block.get("confidence")

        max_body_y1 = doc_context.page_max_body_y1.get(p_idx, 0.0)
        is_bottom_margin = _bottom_signature_geometry(page, block, max_body_y1)

        page_text = ' '.join(str(b.get('text') or '') for b in blocks if b is not block)
        if is_bottom_margin and is_publication_imprint(text, page_text):
            attrs.setdefault('semantic_source_type', orig_type)
            attrs['semantic_rendered_type'] = 'Text'
            attrs['semantic_role'] = 'publication_imprint'
            for key in ('marker','marker_normalized','footnote_status','footnote_confidence'):
                attrs.pop(key,None)
            block['type'] = 'Text'
            continue

        sig = parse_signature_mark(text)
        if not sig or not is_bottom_margin:
            continue
        sheet_num = sig.get("sheet_number") if sig else None
        marker = match_leading_footnote_marker(text)
        refs = doc_context.page_body_refs.get(p_idx, set())
        has_body_ref = bool(sheet_num in refs or marker and marker.normalized in refs)
        if has_body_ref:
            continue

        template_match = False
        if sig and sig.get("title"):
            for tpl in doc_context.known_footer_templates:
                if (tpl['page_index'] != p_idx
                        and tpl.get("title", "").strip().casefold() == sig["title"].strip().casefold()
                        and _volume_key(tpl['volume']) == _volume_key(sig['volume'])
                        and abs(tpl['relative_y'] - bbox[1] / page['height']) < .025
                        and abs(tpl['relative_x'] - bbox[0] / page['width']) < .08):
                    template_match = True
                    break

        low_conf = isinstance(conf, (int, float)) and math.isfinite(conf) and conf < .6

        evidence: list[str] = []
        if is_bottom_margin:
            evidence.append("bottom_margin_position")
        if sig:
            evidence.append(f"signature_mark_pattern({sig['type']})")
        if template_match:
            evidence.append("cross_page_footer_template_match")
        if not has_body_ref:
            evidence.append("unanchored_footnote_number")
        if low_conf:
            evidence.append(f"low_upstream_confidence({conf})")

        # Confirmed PageFooter
        original_attributes = {key: attrs[key] for key in ('footnote_confidence', 'footnote_status',
            'excluded_from') if key in attrs}
        if template_match:
            attrs.setdefault("semantic_source_type", orig_type)
            attrs["semantic_rendered_type"] = "PageFooter"
            attrs["page_furniture_review"] = {
                "version": PAGE_FURNITURE_VERSION,
                "original_type": orig_type,
                "reviewed_type": "PageFooter",
                "reason": "sheet_signature",
                "upstream_confidence": conf,
                "sheet_number": sig.get("sheet_number"),
                "mark": sig.get("mark"),
                "title": sig.get("title"),
                "volume": sig.get("volume"),
                "evidence": evidence,
                "status": "reviewed_as_page_footer",
                "original_attributes": original_attributes,
            }
            attrs["footnote_confidence"] = "resolved_as_footer"
            _append_unique(attrs, "excluded_from", "footnote_evidence")
            _append_unique(attrs, "excluded_from", "marginal_detection")
            block["type"] = "PageFooter"
            if counts is not None:
                counts["page_footers_reviewed"] = counts.get("page_footers_reviewed", 0) + 1
            reviews.append({"action": "reclassified_as_page_footer", "block_id": block.get("id"), "evidence": evidence})
            continue

        # Safe Pending Verification
        if not template_match:
            attrs["footnote_confidence"] = "pending_verification"
            attrs["footnote_status"] = "unconfirmed"
            attrs["page_furniture_review"] = {
                "version": PAGE_FURNITURE_VERSION,
                "original_type": orig_type,
                "reviewed_type": "Footnote",
                "reason": "unconfirmed_sheet_signature",
                "upstream_confidence": conf,
                "evidence": evidence,
                "status": "safe_pending_verification",
                "original_attributes": original_attributes,
            }
            if counts is not None:
                counts["footnotes_pending_verification"] = counts.get("footnotes_pending_verification", 0) + 1
            reviews.append({"action": "downgraded_to_pending", "block_id": block.get("id"), "evidence": evidence})

    return reviews


def _append_unique(attrs: dict[str, Any], key: str, value: str) -> None:
    values = attrs.get(key)
    if not isinstance(values, list):
        values = []
    if value not in values:
        values.append(value)
    attrs[key] = values
