"""Classical marginalia analysis: locator codes, text marginalia, body restore.

An evidence-driven analysis phase for classical-edition rendering (Loeb and
similar). Given a Middle JSON document it classifies margin-region candidates
into semantic roles, parses locator systems (Bekker page/column/line, section
and paragraph numbers, bracketed old-edition pages), assembles per-page
locator ranges with boundary states, plans body-text edits for locators that
leaked into Text blocks, and identifies body text misclassified as
MarginalNote. All findings are recorded per page under
``attrs.classical_marginalia`` with version + config signature so repeated
rendering is deterministic and idempotent.

Evidence rules (see MIDDLE_JSON_SCHOLARLY_MARKDOWN_CONTRACT.md):
- Upstream ``MarginalNote`` labels and the legacy ``semantic_role=line_number``
  are clues only; they never classify on their own.
- Classification combines per-page body band estimation, geometry, text
  shape, reading order, printed-page equality and (optional) word-level
  coordinates from the source OCR PDF or a human audit file.
- Anything insufficiently evidenced stays ``undetermined`` and is reported
  for review; deletion or normalization never happens without evidence.
"""

from __future__ import annotations

from aih_contexture.middle.storage import decode_middle_storage

import copy
import hashlib
import math
import re
import statistics
from pathlib import Path
from typing import Any, Mapping
from aih_contexture.middle.classical_capabilities import classical_bbox_is_trustworthy, classical_marginalia_capabilities, classical_margin_side
from aih_contexture.utils.storage_numbers import storage_number, storage_numbers

CLASSICAL_MARGINALIA_VERSION = "classical-marginalia/0.18"

CLASSICAL_MARGINALIA_MODES = ("off", "page_locators")
CLASSICAL_TEXT_MARGINALIA_MODES = ("separate", "drop")

PAGE_ATTR_KEY = "classical_marginalia"
METADATA_KEY = "classical_marginalia_resolution"

_BEKKER_RE = re.compile(r"^(\d{3})\s*([ab]?)$")
_BRACKETED_RE = re.compile(r"^\[(\d{1,4})\]$")
_DECIMAL_SECTION_RE = re.compile(r"^(\d{1,3})(?:\.(\d{1,3}))?$")
_ROMAN_RE = re.compile(r"^[ivxlcdm]{1,8}$", re.IGNORECASE)
_DIGITS_RE = re.compile(r"^\d{1,4}$")
_SHORT_WORD_RE = re.compile(r"^[a-zà-ÿ]{1,4}$")

_PROSE_BLOCK_TYPES = {"Text", "ListItem"}
_PROSE_WIDE_TYPE_PREFIXES = ("Text", "Footnote", "SectionHeader", "ListItem")


def _is_footnote_block(block: Mapping[str, Any]) -> bool:
    block_type = str(block.get("type") or "").lower()
    attrs = block.get("attrs") if isinstance(block.get("attrs"), Mapping) else {}
    role = str(attrs.get("semantic_role") or "").lower()
    return "footnote" in block_type or "footnote" in role or bool(attrs.get("footnote_id"))


def normalize_classical_marginalia_mode(value: Any) -> str:
    mode = str(value or "").strip().lower().replace("-", "_")
    return mode if mode in CLASSICAL_MARGINALIA_MODES else "off"


def normalize_classical_text_marginalia_mode(value: Any) -> str:
    mode = str(value or "").strip().lower().replace("-", "_")
    return mode if mode in CLASSICAL_TEXT_MARGINALIA_MODES else "separate"


def classical_marginalia_config_signature(config: Mapping[str, Any] | None) -> str:
    payload = {
        "version": CLASSICAL_MARGINALIA_VERSION,
        "classical_marginalia_mode": normalize_classical_marginalia_mode(
            (config or {}).get("classical_marginalia_mode")
        ),
    }
    raw = json_dumps_compact(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _fingerprint(value: Any) -> str:
    """Return a stable SHA-256 for JSON-compatible source/evidence data."""

    raw = json_dumps_compact(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _source_payload(middle_json: Mapping[str, Any]) -> dict[str, Any]:
    """Project the source fields that survive compact save/reload.

    This mirrors the compact Middle allowlists so the same input has the same
    fingerprint before and after spans/provenance details are stripped.
    """

    page_keys = {"index", "width", "height", "printed_page", "anchor_start", "anchor_end"}
    page_attrs = {
        "layout_sliced", "ocr_errors_detected", "machine_page_number",
        "page_header_text", "page_footer_text",
        "coordinate_space", "logical_pages", "input_frame_index", "logical_page_mapping", "error", "diagnostic",
    }
    block_keys = {
        "id", "type", "page_index", "order", "text", "anchor_start",
        "anchor_end", "bbox", "confidence",
    }
    block_attrs = {
        "side", "position", "placement", "heading_level", "heading_level_source",
        "raw_heading_level", "raw_block_type", "raw_label", "style", "source",
        "semantic_role", "marker", "marker_normalized",
        "footnote_confidence", "footnote_evidence", "excluded_from", "inline_marks",
        "normalization", "semantic_warnings", "marginal_confidence",
        "coordinate_space", "coordinate_transform", "logical_page_index", "logical_printed_page", "input_frame_index",
    }
    from aih_contexture.middle.reading_structure import READING_BLOCK_ATTRS
    block_attrs.update(READING_BLOCK_ATTRS)
    metadata_excluded = {
        METADATA_KEY, "images", "image_data", "debug_images", "page_images",
        'reading_render_options', 'effective_render_options',
        'classical_marginalia_review',
        'reading_review',
        'reading_page_manifest',
        'reading_postprocess',
        'semantic_resolution',
    }

    def keep_value(value: Any) -> bool:
        # Mirrors runtime.artifacts._keep_value.
        return value not in (None, "", [], {})

    def compact_value(value: Any) -> Any:
        if isinstance(value, float):
            return storage_number(value)
        if isinstance(value, list):
            # The compact serializer preserves empty list elements; only
            # dictionary entries and outer fields are omitted when empty.
            return [compact_value(item) for item in value]
        if isinstance(value, Mapping):
            return {
                key: compact_value(item)
                for key, item in value.items()
                if keep_value(item)
            }
        return value

    def attrs_from(value: Any, keep: set[str]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        return {key: compact_value(value[key]) for key in keep if key in value and keep_value(value[key])}

    def block_projection(block: Mapping[str, Any]) -> dict[str, Any]:
        output = {key: compact_value(block[key]) for key in block_keys if key in block and keep_value(block[key])}
        from aih_contexture.middle.native_geometry import compact_native_spans
        native_spans = compact_native_spans(block)
        if native_spans:
            output['spans'] = compact_value(native_spans)
        attrs = attrs_from(block.get("attrs"), block_attrs)
        if attrs:
            output["attrs"] = attrs
        provenance = block.get("provenance")
        if isinstance(provenance, list):
            compact_provenance = []
            for entry in provenance:
                if not isinstance(entry, Mapping):
                    continue
                compact_entry = {
                    key: compact_value(entry[key])
                    for key in ("backend", "stage", "raw_label", "model", "confidence")
                    if key in entry and keep_value(entry[key])
                }
                if compact_entry and compact_entry not in compact_provenance:
                    compact_provenance.append(compact_entry)
            if compact_provenance:
                output["provenance"] = compact_provenance[:2]
        children = block.get("children")
        if isinstance(children, list) and children:
            compact_children = [block_projection(child) for child in children if isinstance(child, Mapping)]
            if compact_children:
                output["children"] = compact_children
        return output

    payload = {
        key: compact_value(middle_json[key])
        for key in ("schema_version", "source_name", "page_count", "backends")
        if key in middle_json and keep_value(middle_json[key])
    }
    metadata = middle_json.get("metadata")
    if isinstance(metadata, Mapping):
        stable_metadata = {
            key: value
            for key, value in metadata.items()
            if key not in metadata_excluded and keep_value(value)
        }
        compact_metadata = compact_value(stable_metadata)
        if compact_metadata:
            payload["metadata"] = compact_metadata
    pages = middle_json.get("pages")
    compact_pages = []
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, Mapping):
                continue
            item = {key: compact_value(page[key]) for key in page_keys if key in page and keep_value(page[key])}
            attrs = attrs_from(page.get("attrs"), page_attrs)
            if attrs:
                item["attrs"] = attrs
            blocks = page.get("blocks")
            item["blocks"] = [block_projection(block) for block in blocks if isinstance(block, Mapping)] if isinstance(blocks, list) else []
            provenance = page.get("provenance")
            if isinstance(provenance, list):
                compact_provenance = []
                for entry in provenance:
                    if not isinstance(entry, Mapping):
                        continue
                    compact_entry = {
                        key: compact_value(entry[key])
                        for key in ("backend", "stage", "model")
                        if key in entry and keep_value(entry[key])
                    }
                    if compact_entry and compact_entry not in compact_provenance:
                        compact_provenance.append(compact_entry)
                if compact_provenance:
                    item["provenance"] = compact_provenance[:2]
            compact_pages.append(item)
    payload["pages"] = compact_pages
    if "page_count" not in payload:
        payload["page_count"] = len(compact_pages)
    return payload


def middle_source_fingerprint(middle_json: Mapping[str, Any]) -> str:
    """Fingerprint source Middle content, excluding this analyzer's cache.

    The value is stable across JSON whitespace/key ordering and across
    compact-save/reload cycles. It includes page/block text, structure,
    geometry and all non-classical-marginalia metadata.
    """
    middle_json = decode_middle_storage(middle_json)

    return _fingerprint(_source_payload(middle_json))


def _valid_human_evidence(
    evidence: Mapping[str, Any] | None,
    source_fingerprint: str,
) -> tuple[Mapping[str, Any] | None, str | None]:
    if evidence is None:
        return None, None
    if not isinstance(evidence, Mapping):
        return None, "human_evidence_not_a_mapping"
    claimed = str(evidence.get("source_fingerprint") or "")
    if not claimed or claimed != source_fingerprint:
        return None, "human_evidence_source_fingerprint_missing_or_mismatched"
    return evidence, None


def json_dumps_compact(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Body band estimation
# ---------------------------------------------------------------------------


def _bbox(block: Mapping[str, Any], page: Mapping[str, Any] | None = None) -> list[float] | None:
    raw = block.get("bbox")
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            values = [float(v) for v in raw]
        except (TypeError, ValueError, OverflowError):
            return None
        if not all(math.isfinite(value) for value in values):
            return None
        if page is not None and not classical_bbox_is_trustworthy(values, page, block):
            return None
        if values[2] > values[0] and values[3] > values[1]:
            return values
    return None


def _estimate_body_band(page: Mapping[str, Any]) -> dict[str, float] | None:
    """Estimate the page's prose band from wide text-ish blocks.

    Uses blocks at least 25% of the page wide, so margin slivers (locator
    codes, tiny misclassified boxes) cannot drag the band outward. Returns
    ``left/right/top/bottom`` medians plus the page size.
    """

    width = _positive(page.get("width"))
    height = _positive(page.get("height"))
    if width is None or height is None:
        return None
    lefts: list[float] = []
    rights: list[float] = []
    for block in page.get("blocks", []) or []:
        if not isinstance(block, Mapping):
            continue
        block_type = str(block.get("type") or "")
        if not block_type.startswith(_PROSE_WIDE_TYPE_PREFIXES):
            continue
        box = _bbox(block, page)
        if box is None or (box[2] - box[0]) < width * 0.25:
            continue
        lefts.append(box[0])
        rights.append(box[2])
    if not lefts:
        return None
    # Band edges from the outermost real text column: prose legitimately
    # starts at several indents (short connector lines, quote columns), so a
    # min/max over wide blocks - not a median/percentile - keeps short words
    # misclassified as MarginalNote "inside the band" (L511 'et').
    return {
        "left": max(0.0, min(lefts) - 2.0),
        "right": min(float(width), max(rights) + 2.0),
        "width": width,
        "height": height,
    }


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


# ---------------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------------


class _Candidate:
    __slots__ = (
        "raw",
        "source_type",
        "block_id",
        "block_index",
        "bbox",
        "char_start",
        "char_end",
        "line_index",
        "pdf_word",
        "role",
        "scheme",
        "normalized",
        "components",
        "confidence",
        "evidence",
        "notes",
    )

    def __init__(self, raw: str, **kwargs: Any) -> None:
        self.raw = raw
        self.source_type = ""
        self.block_id = ""
        self.block_index = -1
        self.bbox: list[float] | None = None
        self.char_start = 0
        self.char_end = len(raw)
        self.line_index = 0
        self.pdf_word: dict[str, Any] | None = None
        self.role = "undetermined"
        self.scheme = ""
        self.normalized = raw
        self.components: dict[str, Any] = {}
        self.confidence = "low"
        self.evidence: list[str] = []
        self.notes: list[str] = []
        for key, value in kwargs.items():
            setattr(self, key, value)

    def item(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "raw": self.raw,
            "normalized": self.normalized,
            "role": self.role,
            "scheme": self.scheme,
            "block_id": self.block_id,
            "char_range": [self.char_start, self.char_end],
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }
        if self.components:
            payload["components"] = dict(self.components)
        if self.bbox is not None:
            payload["bbox"] = [round(v, 2) for v in self.bbox]
        if self.pdf_word:
            payload["pdf_word"] = self.pdf_word
        if self.notes:
            payload["notes"] = list(self.notes)
        return payload


def _split_candidate_lines(text: str) -> list[tuple[int, int, str]]:
    """Split block text into per-line (start, end, stripped) segments."""

    segments: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\n]+", text or ""):
        stripped = match.group(0).strip()
        if stripped:
            start = match.start() + (match.group(0).index(stripped[0]) if stripped else 0)
            segments.append((start, start + len(stripped), stripped))
    return segments


def _collect_marginal_candidates(page: Mapping[str, Any], band: dict[str, float] | None) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for index, block in enumerate(page.get("blocks", []) or []):
        if not isinstance(block, Mapping) or str(block.get("type") or "") != "MarginalNote":
            continue
        text = str(block.get("text") or "")
        box = _bbox(block, page)
        lines = _split_candidate_lines(text)
        if not lines:
            candidates.append(
                _Candidate("", source_type="marginal_note", block_id=str(block.get("id") or ""), block_index=index, bbox=box, role="empty")
            )
            continue
        if len(lines) == 1:
            start, end, stripped = lines[0]
            candidates.append(
                _Candidate(
                    stripped,
                    source_type="marginal_note",
                    block_id=str(block.get("id") or ""),
                    block_index=index,
                    bbox=box,
                    char_start=start,
                    char_end=end,
                )
            )
            continue
        # Keep prose-shaped multi-line marginalia intact. Split only when the
        # complete block is a sequence of locator-shaped lines; this preserves
        # cases such as ``10\n[228]`` without turning a paragraph note into
        # unrelated single-line fragments.
        if len(lines) >= 2 and all(
            re.fullmatch(r"(?:\d{1,4}[ab]?|[ab]|\[\d{1,4}\]|\d{1,3}\.\d{1,3})", line[2], re.I)
            for line in lines
        ):
            original_line_count = len(lines)
            base_line_index = 0
            # A 3-digit page number followed by a bare column letter is ONE
            # Bekker page-column marker split across lines ('402\na').
            if len(lines) >= 2 and re.fullmatch(r"\d{3}", lines[0][2]) and re.fullmatch(r"[ab]", lines[1][2], re.I):
                candidates.append(
                    _Candidate(
                        lines[0][2] + lines[1][2].lower(),
                        source_type="marginal_note",
                        block_id=str(block.get("id") or ""),
                        block_index=index,
                        bbox=box,
                        char_start=lines[0][0],
                        char_end=lines[1][1],
                        evidence=["join:page_column_split_lines"],
                    )
                )
                lines = lines[2:]
                base_line_index = 2
            line_height = (box[3] - box[1]) / max(1, original_line_count) if box else 0.0
            for line_index, (start, end, stripped) in enumerate(lines):
                sub_box = None
                if box and line_height:
                    visual_index = base_line_index + line_index
                    sub_box = [box[0], box[1] + visual_index * line_height, box[2], box[1] + (visual_index + 1) * line_height]
                candidates.append(
                    _Candidate(
                        stripped,
                        source_type="marginal_note",
                        block_id=str(block.get("id") or ""),
                        block_index=index,
                        bbox=sub_box or box,
                        char_start=start,
                        char_end=end,
                        line_index=line_index,
                    )
                )
            continue

        # A single prose candidate keeps all original newlines and its exact
        # source span. This is important for multi-line printed marginalia and
        # handwritten notes awaiting review.
        first_start = lines[0][0]
        last_end = lines[-1][1]
        candidates.append(
            _Candidate(
                text[first_start:last_end],
                source_type="marginal_note",
                block_id=str(block.get("id") or ""),
                block_index=index,
                bbox=box,
                char_start=first_start,
                char_end=last_end,
            )
        )
    return candidates


def _collect_stray_text_candidates(page: Mapping[str, Any], band: dict[str, float] | None) -> list[_Candidate]:
    """Bekker-style page-column markers misclassified as tiny Text blocks."""

    candidates: list[_Candidate] = []
    if band is None:
        return candidates
    for index, block in enumerate(page.get("blocks", []) or []):
        if not isinstance(block, Mapping) or str(block.get("type") or "") != "Text":
            continue
        if _is_footnote_block(block):
            continue
        source_text = str(block.get("text") or "")
        text = source_text.strip()
        if not text or len(text) > 8 or "\n" in text:
            continue
        if not _BEKKER_RE.fullmatch(text.replace(" ", "")):
            continue
        box = _bbox(block, page)
        if box is None:
            continue
        width = box[2] - box[0]
        center_x = (box[0] + box[2]) / 2
        in_margin = center_x < band["left"] - 1 or center_x > band["right"] + 1
        tiny = width <= max(12.0, band["width"] * 0.08)
        above_body = box[3] <= band.get("top", box[3]) + 1 if band.get("top") is not None else False
        # A short body label such as a letter number "123a" has the same
        # spelling as a Bekker anchor. Size or a heading position alone is
        # insufficient evidence to remove it from the source prose.
        if not in_margin:
            continue
        candidates.append(
            _Candidate(
                text,
                source_type="stray_text",
                block_id=str(block.get("id") or ""),
                block_index=index,
                bbox=box,
                char_start=source_text.find(text),
                char_end=source_text.find(text) + len(text),
                evidence=["shape:bekker_like", f"text_block_tiny={tiny}", f"in_margin={in_margin}"],
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# PDF word-coordinate supplement
# ---------------------------------------------------------------------------


def collect_pdf_margin_words(pdf_path: str | Path) -> dict[int, list[dict[str, Any]]]:
    """Extract marginal zone word boxes from the source OCR PDF, per 0-based page.

    The OCR PDF is the layout input itself; its text layer is an independent
    OCR pass, usable as supplementary coordinate evidence. Returns raw word
    records with page-space boxes (caller maps to Middle coordinates).
    """

    import fitz  # PyMuPDF; lazily imported

    result: dict[int, list[dict[str, Any]]] = {}
    with fitz.open(str(pdf_path)) as doc:
        for page_index, page in enumerate(doc):
            try:
                words = page.get_text("words")
            except Exception:  # noqa: BLE001 - unreadable layer yields no evidence
                continue
            rotation = int(page.rotation or 0)
            rect = page.rect
            crop = page.cropbox
            media = page.mediabox
            crop_values = [float(crop.x0), float(crop.y0), float(crop.x1), float(crop.y1)]
            media_values = [float(media.x0), float(media.y0), float(media.x1), float(media.y1)]
            geometry_tolerance = 0.1
            uncropped = all(
                abs(left - right) <= geometry_tolerance
                for left, right in zip(crop_values, media_values)
            )
            coordinates_valid = bool(
                rotation == 0
                and uncropped
                and abs(crop_values[0]) <= geometry_tolerance
                and abs(crop_values[1]) <= geometry_tolerance
                and abs(media_values[0]) <= geometry_tolerance
                and abs(media_values[1]) <= geometry_tolerance
                and abs(float(rect.x0)) <= geometry_tolerance
                and abs(float(rect.y0)) <= geometry_tolerance
            )
            records: list[dict[str, Any]] = []
            for word in words:
                text = str(word[4]).strip()
                if not text:
                    continue
                records.append(
                    {
                        "text": text,
                        "bbox": [float(word[0]), float(word[1]), float(word[2]), float(word[3])],
                        "rotation": rotation,
                        "page_rect": [float(rect.width), float(rect.height)],
                        "cropbox": crop_values,
                        "mediabox": media_values,
                        "coordinates_valid": coordinates_valid,
                    }
                )
            result[page_index] = records
    return result


class _PdfWordIndex:
    """Word boxes mapped into Middle page space with margin classification."""

    def __init__(self, words: list[dict[str, Any]] | None, page: Mapping[str, Any], band: dict[str, float] | None) -> None:
        self.records: list[dict[str, Any]] = []
        self.band = band
        if not words or band is None:
            return
        middle_size = (band["width"], band["height"])
        for word in words:
            # Coordinates from rotated or cropped pages cannot be safely
            # mapped by independent width/height scaling. Fail closed unless
            # the collector explicitly validated the source page geometry.
            if word.get("coordinates_valid") is not True:
                continue
            if int(word.get("rotation") or 0) != 0:
                continue
            rect = word.get("page_rect")
            if not isinstance(rect, (list, tuple)) or len(rect) != 2:
                continue
            try:
                pdf_width, pdf_height = float(rect[0]), float(rect[1])
                box = [float(v) for v in word["bbox"]]
            except (TypeError, ValueError, KeyError):
                continue
            if pdf_width <= 0 or pdf_height <= 0 or len(box) != 4:
                continue
            scale_x = middle_size[0] / pdf_width
            scale_y = middle_size[1] / pdf_height
            ratio = scale_x / scale_y if scale_y else 0.0
            if not ratio or abs(ratio - 1.0) > 0.02:
                continue
            mapped = [box[0] * scale_x, box[1] * scale_y, box[2] * scale_x, box[3] * scale_y]
            if not classical_bbox_is_trustworthy(mapped, page):
                continue
            center_x = (mapped[0] + mapped[2]) / 2
            margin_side = ""
            if center_x < band["left"] - 0.5:
                margin_side = "left"
            elif center_x > band["right"] + 0.5:
                margin_side = "right"
            self.records.append(
                {
                    "text": word["text"],
                    "bbox": mapped,
                    "center_x": center_x,
                    "center_y": (mapped[1] + mapped[3]) / 2,
                    "margin_side": margin_side,
                    "pdf_text": word["text"],
                }
            )

    def marginal_digit_words(self, band: Mapping[str, float]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for record in self.records:
            if not record["margin_side"]:
                continue
            token = record["text"]
            if _DIGITS_RE.match(token) or _BEKKER_RE.match(token) or _BRACKETED_RE.match(token):
                out.append(record)
        return out

    def line_leading_locator_words(self) -> list[dict[str, Any]]:
        """Locator words detected per visual line, band-independent.

        Groups mapped words into visual lines (y within 2.0), then keeps
        pure-digit / Bekker tokens that are the FIRST word of their line and
        separated from the following word by a visible gap. This catches line
        numbers printed at the very left edge of the text column, where any
        body-band-relative margin test is meaningless.
        """
        lines: list[list[dict[str, Any]]] = []
        for record in sorted(self.records, key=lambda r: (r["center_y"], r["bbox"][0])):
            placed = False
            for line in lines:
                if abs(line[-1]["center_y"] - record["center_y"]) <= 2.0:
                    line.append(record)
                    placed = True
                    break
            if not placed:
                lines.append([record])
        out: list[dict[str, Any]] = []
        for line in lines:
            line.sort(key=lambda r: r["bbox"][0])
            first = line[0]
            token = first["text"]
            compact = token.replace(" ", "")
            bekk = _BEKKER_RE.fullmatch(compact)
            is_page_column = bool(bekk and bekk.group(2))
            emitted = first
            if not is_page_column and re.fullmatch(r"\d{3}", compact) and len(line) >= 2:
                second = line[1]
                if second["text"].lower() in {"a", "b"} and (second["bbox"][0] - first["bbox"][2]) <= 3.0:
                    emitted = dict(first)
                    emitted["text"] = compact + second["text"].lower()
                    is_page_column = True
            digits = _DIGITS_RE.fullmatch(token)
            is_supported_line = bool(
                digits
                and len(token) <= 2
                and 5 <= int(token) <= 35
                and _is_multiple_of_five(int(token))
            )
            edge_tolerance = max(6.0, self.band["width"] * 0.025) if self.band else 0.0
            at_text_band_edge = bool(
                self.band
                and min(
                    abs(first["center_x"] - self.band["left"]),
                    abs(first["center_x"] - self.band["right"]),
                ) <= edge_tolerance
            )
            if not (is_page_column or is_supported_line) or not (first["margin_side"] or at_text_band_edge):
                continue
            gap_ok = len(line) == 1 or (line[1]["bbox"][0] - first["bbox"][2]) >= 2.0
            if not is_page_column and not gap_ok:
                continue
            out.append(emitted)
        return out

    def word_near(self, x: float, y: float, radius: float = 6.0) -> dict[str, Any] | None:
        best = None
        best_distance = None
        for record in self.records:
            distance = abs(record["center_x"] - x) + abs(record["center_y"] - y)
            if best_distance is None or distance < best_distance:
                best, best_distance = record, distance
        if best is not None and best_distance is not None and best_distance <= radius:
            return best
        return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _is_multiple_of_five(value: int) -> bool:
    return value % 5 == 0


def _printed_page_value(page: Mapping[str, Any]) -> str | None:
    raw = page.get("printed_page")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _classify_candidates(
    page: Mapping[str, Any],
    candidates: list[_Candidate],
    band: dict[str, float] | None,
    context: dict[str, Any],
) -> None:
    printed = _printed_page_value(page)
    page_height = band["height"] if band else 0.0
    page_width = band["width"] if band else 0.0

    def candidate_order(candidate: _Candidate) -> tuple[float, float, int]:
        if candidate.bbox is None:
            return (float("inf"), float("inf"), candidate.block_index)
        return (
            (candidate.bbox[1] + candidate.bbox[3]) / 2,
            (candidate.bbox[0] + candidate.bbox[2]) / 2,
            candidate.block_index,
        )

    # Context follows this physical page's visual reading order only.
    for candidate in sorted(candidates, key=candidate_order):
        if candidate.role == "empty":
            continue
        text = candidate.raw
        box = candidate.bbox
        if box is None:
            candidate.evidence.append("geometry:missing_or_invalid_bbox")
            candidate.notes.append("kept_for_review_without_spatial_classification")
            continue
        compact = re.sub(r"\s+", "", text)

        position_notes: list[str] = []
        center_x = (box[0] + box[2]) / 2 if box else None
        center_y = (box[1] + box[3]) / 2 if box else None
        tiny_width = bool(box and (box[2] - box[0]) <= max(12.0, page_width * 0.08))
        in_margin = bool(
            band and center_x is not None and (center_x < band["left"] - 1.0 or center_x > band["right"] + 1.0)
        )
        in_band = bool(
            band and center_x is not None and band["left"] - 1.0 <= center_x <= band["right"] + 1.0
        )
        if in_margin:
            position_notes.append("position:outside_body_band")
        if in_band:
            position_notes.append("position:inside_body_band")
        if tiny_width:
            position_notes.append("geometry:tiny_width")

        # 1) printed page duplicate (value equal + top/bottom margin zone)
        if printed and compact == re.sub(r"\s+", "", printed) and box and page_height:
            if center_y <= page_height * 0.15 or center_y >= page_height * 0.80:
                candidate.role = "printed_page_number"
                candidate.confidence = "high"
                candidate.evidence = position_notes + [f"equals_printed_page:{printed}", "position:page_edge"]
                continue

        # 2) Bekker-style page-column marker: '415a', '402 a', '413 a'
        bekk_match = _BEKKER_RE.match(compact)
        if (bekk_match and len(bekk_match.group(1)) == 3 and bekk_match.group(2)
                and candidate.source_type in {"marginal_note", "stray_text"}):
            page_num = int(bekk_match.group(1))
            column = bekk_match.group(2) or ""
            near_body_top = bool(
                band
                and box
                and center_y is not None
                and center_y <= band.get("prose_top", band.get("top", box[1])) + 24
            )
            if in_margin or tiny_width or near_body_top or candidate.source_type == "stray_text":
                candidate.role = "locator"
                candidate.scheme = "bekker"
                candidate.normalized = f"{page_num}{column}" if column else str(page_num)
                candidate.components = {"page": page_num, "column": column or None, "line": None}
                candidate.confidence = "high" if (in_margin or near_body_top) else "medium"
                candidate.evidence = position_notes + ["shape:bekker_page_column"]
                context["bekker_active"] = True
                context.setdefault("bekker_pages", set()).add(page_num)
                context["bekker_context"] = {"page": page_num, "column": column or None}
                context["bekker_anchor_y"] = center_y
                continue

        # 3) bracketed old-edition page reference
        bracket_match = _BRACKETED_RE.match(text)
        if bracket_match:
            candidate.role = "locator"
            candidate.scheme = "bracketed_old_page"
            candidate.normalized = text
            candidate.components = {"page": int(bracket_match.group(1))}
            candidate.confidence = "high" if (in_margin or tiny_width) else "medium"
            candidate.evidence = position_notes + ["shape:bracketed_page"]
            continue

        # 4) pure digits: line number vs section/paragraph number
        digit_match = _DIGITS_RE.match(text)
        if digit_match and candidate.source_type == "marginal_note":
            value = int(text)
            left_edge = bool(
                band and box and center_x is not None and center_x <= max(band["left"] + 2.0, page_width * 0.10)
            )
            line_position_ok = in_margin or left_edge or tiny_width or (box and (box[3] - box[1]) <= 12.0)
            local_bekker_context = bool(
                context.get("bekker_active")
                and context.get("bekker_context")
                and context["bekker_context"].get("column") in {"a", "b"}
                and (context.get("bekker_anchor_y") is None or center_y is None or center_y >= context["bekker_anchor_y"])
            )
            if local_bekker_context and line_position_ok and 5 <= value <= 35 and _is_multiple_of_five(value):
                candidate.role = "locator"
                candidate.scheme = "bekker"
                candidate.components = {"page": None, "column": None, "line": value}
                candidate.normalized = text
                candidate.confidence = "high" if in_margin or left_edge or tiny_width else "medium"
                candidate.evidence = position_notes + [
                    f"shape:digit_{value}",
                    "page_local_bekker_anchor_precedes_candidate",
                ]
                context["bekker_active"] = True
                continue
            if local_bekker_context and line_position_ok and _is_multiple_of_five(value):
                candidate.role = "undetermined"
                candidate.evidence = position_notes + ["page_local_bekker_context", "digit_outside_supported_line_range"]
                candidate.notes.append("manual_check_required_no_automatic_bekker_normalization")
                continue
            if (
                context.get("book_line_scheme")
                and line_position_ok
                and _is_multiple_of_five(value)
                and (5 <= value <= 35 or value > 35)
            ) or _detect_line_sequence(candidates):
                # A book/page ladder can flag an ambiguous number for review,
                # but only an earlier page/column marker on this page can
                # establish a Bekker line context.
                candidate.role = "undetermined"
                candidate.evidence = position_notes + ["line_like_digit_without_page_local_bekker_anchor"]
                candidate.notes.append("manual_check_required_no_automatic_bekker_normalization")
                continue
            if line_position_ok:
                # In the absence of local Bekker context, preserve likely
                # chapter/paragraph numbers as their own locator scheme.
                candidate.role = "locator"
                candidate.scheme = "paragraph"
                candidate.components = {"number": value}
                candidate.normalized = text
                candidate.confidence = "high" if (in_margin or left_edge) else "medium"
                candidate.evidence = position_notes + ["shape:digit", "no_page_local_bekker_context"]
                continue
            candidate.role = "undetermined"
            candidate.evidence = position_notes + ["shape:digit"]
            candidate.notes.append("digit_without_margin_or_page_context")
            continue

        # 5) decimal and Roman labels are weak shape evidence. Short decimal
        # marginal labels such as 5.3 remain unresolved without an audited
        # hierarchy/sequence; punctuation is never stripped to make a line.
        if _DECIMAL_SECTION_RE.match(text):
            if in_margin or tiny_width:
                candidate.role = "undetermined"
                candidate.evidence = position_notes + ["shape:decimal_label_without_hierarchy_evidence"]
                candidate.notes.append("manual_check_required_preserve_decimal_label")
                continue
        if _ROMAN_RE.match(text):
            if in_margin or tiny_width:
                candidate.role = "locator"
                candidate.scheme = "paragraph"
                candidate.normalized = text
                candidate.components = {"label": text}
                candidate.confidence = "medium"
                candidate.evidence = position_notes + ["shape:section_label"]
                candidate.notes.append("decimal_or_roman_label_not_normalized")
                continue

        # 6) a short lowercase word may be body text, but centroid-only band
        # membership is insufficient: require normal glyph geometry and
        # stable same-column prose blocks above and below it.
        if (
            candidate.source_type == "marginal_note"
            and _SHORT_WORD_RE.match(text)
            and band is not None
            and center_x is not None
            and band["left"] - 1.0 <= center_x <= band["right"] + 1.0
        ):
            geometry_ok, geometry_evidence = _short_word_body_geometry(page, candidate, band)
            if geometry_ok:
                candidate.role = "misclassified_body"
                candidate.confidence = "high"
                candidate.evidence = position_notes + geometry_evidence + ["shape:single_short_word"]
            else:
                candidate.role = "undetermined"
                candidate.confidence = "low"
                candidate.evidence = position_notes + geometry_evidence + ["shape:single_short_word"]
                candidate.notes.append("manual_check_required_short_word_geometry")
            continue

        # 7) default: prose-shaped marginal notes stay visible text
        # marginalia (the upstream detector's claim); in-band ones carry a
        # review note. They are never dropped or merged into the body.
        candidate.role = "text_marginal"
        candidate.confidence = "medium" if in_margin else "low"
        candidate.evidence = position_notes + ["shape:prose"]
        if not in_margin:
            candidate.notes.append("inside_body_band_review")


def _short_word_body_geometry(
    page: Mapping[str, Any],
    candidate: _Candidate,
    band: Mapping[str, float],
) -> tuple[bool, list[str]]:
    """Require plausible glyph geometry and same-column prose bracketing.

    Some layout blocks absorb a nearby sidenote and become much wider than
    the stable text column. For this conservative restore decision, use a
    robust right edge (median) and a low-percentile left edge, then require
    the *whole candidate box* to fit inside that core. Blocks that overlap the
    candidate row cannot serve as bracketing evidence; this avoids treating
    a word printed beside a prose block as part of the body.
    """

    box = candidate.bbox
    text = candidate.raw.strip()
    if box is None or not text:
        return False, ["geometry:short_word_missing_bbox_or_text"]

    page_width = _positive(page.get("width")) or float(band.get("width") or 0.0)
    if page_width <= 0:
        return False, ["geometry:short_word_missing_page_width"]

    stable_rows: list[tuple[list[float], float]] = []
    for block in page.get("blocks", []) or []:
        if not isinstance(block, Mapping) or str(block.get("type") or "") not in _PROSE_BLOCK_TYPES:
            continue
        if _is_footnote_block(block):
            continue
        prose_box = _bbox(block, page)
        prose_text = str(block.get("text") or "").strip()
        if prose_box is None or not prose_text or prose_box[2] - prose_box[0] < page_width * 0.25:
            continue
        line_count = max(1, len(prose_text.splitlines()))
        line_height = (prose_box[3] - prose_box[1]) / line_count
        if line_height > 0:
            stable_rows.append((prose_box, line_height))

    if len(stable_rows) < 2:
        return False, ["geometry:insufficient_stable_prose_blocks"]

    reference_line_height = statistics.median(row[1] for row in stable_rows)
    candidate_height = box[3] - box[1]
    candidate_width = box[2] - box[0]
    glyph_count = max(1, len(text))
    if not reference_line_height > 0:
        return False, ["geometry:missing_reference_line_height"]
    if not reference_line_height * 0.35 <= candidate_height <= reference_line_height * 1.75:
        return False, ["geometry:short_word_height_outside_body_line_range"]
    min_width = reference_line_height * max(0.2, glyph_count * 0.18)
    max_width = reference_line_height * max(1.5, glyph_count * 2.0)
    if not min_width <= candidate_width <= max_width:
        return False, ["geometry:short_word_width_outside_glyph_range"]

    left_edges = [row[0][0] for row in stable_rows]
    right_edges = [row[0][2] for row in stable_rows]
    left_edges.sort()
    left_position = (len(left_edges) - 1) * 0.10
    left_low = int(left_position)
    left_fraction = left_position - left_low
    lower_left_percentile = left_edges[left_low]
    if left_low + 1 < len(left_edges):
        lower_left_percentile += (left_edges[left_low + 1] - lower_left_percentile) * left_fraction
    # A modest envelope preserves recurring indented prose rows (as in L511)
    # while limiting how far a single stray left edge can expand the core.
    core_left = max(min(left_edges), lower_left_percentile - reference_line_height * 1.5)
    core_right = statistics.median(right_edges)
    edge_tolerance = 1.0
    if box[0] < core_left - edge_tolerance or box[2] > core_right + edge_tolerance:
        return False, ["position:short_word_outside_robust_body_core"]

    center_x = (box[0] + box[2]) / 2
    vertical_gap = max(2.0, reference_line_height * 0.15)
    horizontal_tolerance = min(reference_line_height * 0.75, page_width * 0.035)
    above = False
    below = False
    overlaps_prose_row = False
    for prose_box, _ in stable_rows:
        same_column = prose_box[0] - horizontal_tolerance <= center_x <= prose_box[2] + horizontal_tolerance
        vertical_overlap = prose_box[1] < box[3] and prose_box[3] > box[1]
        horizontal_overlap = prose_box[0] < box[2] and prose_box[2] > box[0]
        if vertical_overlap and horizontal_overlap:
            overlaps_prose_row = True
        if same_column and prose_box[3] <= box[1] - vertical_gap:
            above = True
        if same_column and prose_box[1] >= box[3] + vertical_gap:
            below = True

    if overlaps_prose_row:
        return False, ["position:short_word_overlaps_prose_block_row"]
    if not (above and below):
        return False, ["position:short_word_not_bracketed_by_same_column_prose"]
    return True, [
        "geometry:short_word_height_matches_body_line",
        "geometry:short_word_width_matches_glyph_count",
        "position:inside_robust_body_core",
        "reading_position:between_same_column_prose_blocks",
    ]


def _detect_line_sequence(candidates: list[_Candidate]) -> bool:
    """Page-level clue: do digit candidates form a plausible 5-step ladder?"""

    values = sorted(
        int(c.raw) for c in candidates if c.source_type == "marginal_note" and _DIGITS_RE.match(c.raw) and len(c.raw) <= 3
    )
    multiples = [v for v in values if v % 5 == 0 and 5 <= v <= 40]
    if len(multiples) >= 2:
        steps = {multiples[i + 1] - multiples[i] for i in range(len(multiples) - 1)}
        if steps and steps <= {5, 10, 15, 20, 25, 30}:
            return True
    return False


def _detect_book_line_scheme(pages: list[Any]) -> bool:
    """Book-level pre-scan: any Bekker page-column marker or any page ladder."""

    for page in pages:
        if not isinstance(page, Mapping):
            continue
        candidates = _collect_marginal_candidates(page, _estimate_body_band(page))
        candidates.extend(_collect_stray_text_candidates(page, _estimate_body_band(page)))
        candidates = [candidate for candidate in candidates if candidate.bbox is not None]
        if _detect_line_sequence(candidates):
            return True
        for candidate in candidates:
            compact = re.sub(r"\s+", "", candidate.raw)
            if re.fullmatch(r"\d{3}[ab]", compact):
                return True
    return False
# PDF supplement: locators embedded in Text blocks + OCR cross-check
# ---------------------------------------------------------------------------


def _pdf_supplement_for_page(
    page: Mapping[str, Any],
    band: dict[str, float] | None,
    pdf_index: _PdfWordIndex,
    analysis: dict[str, Any],
    *,
    book_line_scheme: bool = False,
) -> None:
    """Recover margin-zone locator words from the OCR PDF text layer.

    Bare line values require an earlier page/column marker on this physical
    page. A PDF text disagreement is review evidence only and never silently
    normalizes Middle text.
    """

    if band is None:
        return
    prose_blocks = [
        b for b in (page.get("blocks", []) or [])
        if isinstance(b, Mapping)
        and str(b.get("type") or "") in _PROSE_BLOCK_TYPES
        and not _is_footnote_block(b)
    ]
    footnote_tops = [
        box[1]
        for block in (page.get("blocks", []) or [])
        if isinstance(block, Mapping) and _is_footnote_block(block)
        for box in [_bbox(block, page)]
        if box is not None
    ]

    words = sorted(pdf_index.line_leading_locator_words(), key=lambda w: (w["center_y"], w["bbox"][0]))
    for word in words:
        if footnote_tops and word["center_y"] >= min(footnote_tops):
            continue
        token = str(word["text"])
        targets = []
        for block in prose_blocks:
            box = _bbox(block, page)
            if box is None:
                continue
            if box[0] - 2 <= word["center_x"] <= box[2] + 2 and box[1] - 4 <= word["center_y"] <= box[3] + 4:
                targets.append(block)
        if len(targets) != 1:
            if len(targets) > 1:
                analysis["review"].append(
                    {"kind": "pdf_word_block_alignment_ambiguous", "raw": token, "bbox": word["bbox"]}
                )
            continue
        target = targets[0]

        text = str(target.get("text") or "")
        compact = token.replace(" ", "")
        locator_item: dict[str, Any] | None = None
        bekk = _BEKKER_RE.fullmatch(compact)
        if bekk and len(bekk.group(1)) == 3 and bekk.group(2):
            locator_item = {
                "raw": token,
                "normalized": compact,
                "role": "locator",
                "scheme": "bekker",
                "components": {"page": int(bekk.group(1)), "column": bekk.group(2) or None, "line": None},
                "block_id": str(target.get("id") or ""),
                "char_range": None,
                "bbox": [round(v, 2) for v in word["bbox"]],
                "confidence": "high",
                "evidence": ["pdf_word:margin_position", "pdf_text_layer"],
            }
        elif _DIGITS_RE.fullmatch(compact):
            value = int(token)
            if not (5 <= value <= 35 and _is_multiple_of_five(value)):
                continue
            if not _has_preceding_bekker_anchor(analysis["locators"], word["center_y"]):
                analysis["review"].append(
                    {
                        "kind": "pdf_digit_without_page_local_bekker_context",
                        "raw": token,
                        "block_id": str(target.get("id") or ""),
                        "bbox": [round(v, 2) for v in word["bbox"]],
                    }
                )
                continue
            locator_item = {
                "raw": token,
                "normalized": str(value),
                "role": "locator",
                "scheme": "bekker",
                "components": {"page": None, "column": None, "line": value},
                "block_id": str(target.get("id") or ""),
                "char_range": None,
                "bbox": [round(v, 2) for v in word["bbox"]],
                "confidence": "high",
                "evidence": ["pdf_word:margin_position", "shape:digit", "page_local_bekker_anchor_precedes_candidate"],
            }

        if locator_item is None:
            continue

        duplicate = False
        for existing in analysis["locators"]:
            if str(existing.get("normalized") or "") != str(locator_item["normalized"]):
                continue
            existing_bbox = existing.get("bbox")
            if (
                isinstance(existing_bbox, (list, tuple))
                and len(existing_bbox) == 4
                and abs((existing_bbox[0] + existing_bbox[2]) / 2 - (locator_item["bbox"][0] + locator_item["bbox"][2]) / 2) <= 3.0
                and abs((existing_bbox[1] + existing_bbox[3]) / 2 - (locator_item["bbox"][1] + locator_item["bbox"][3]) / 2) <= 3.0
            ):
                existing.setdefault("evidence", []).append("pdf_word:confirms")
                duplicate = True
                break
        if duplicate:
            continue

        # Add the PDF locator even if the compact JSON omitted its text, but
        # remove source text only after an exact unique line-leading match.
        edit = _locate_leading_word(text, compact)
        text_position = (
            _pdf_text_line_alignment(text, edit[0], _bbox(target, page) or [], word["center_y"])
            if edit is not None
            else None
        )
        if edit is not None and text_position is not None:
            start, end, original = edit
            analysis["edits"].append(
                {
                    "block_id": str(target.get("id") or ""),
                    "char_range": [start, end],
                    "original": original,
                    "action": "remove_locator_token",
                    "reason": "pdf_word_margin_evidence",
                    "confidence": "high",
                    "locator": locator_item["normalized"],
                    "evidence": [
                        "pdf_word:margin_position",
                        "pdf_block_bbox_unique",
                        "exact_unique_text_token",
                        "pdf_word_matches_source_text_line_position",
                    ],
                    "alignment": text_position,
                }
            )
            locator_item["char_range"] = [start, end]
        elif edit is not None:
            analysis["review"].append(
                {
                    "kind": "pdf_text_alignment_position_mismatch",
                    "raw": compact,
                    "block_id": str(target.get("id") or ""),
                    "char_range": [edit[0], edit[1]],
                    "bbox": [round(v, 2) for v in word["bbox"]],
                    "alignment": text_position,
                }
            )
        elif _has_conflicting_line_leader(text, compact):
            analysis["review"].append(
                {
                    "kind": "pdf_text_token_conflict",
                    "raw": compact,
                    "block_id": str(target.get("id") or ""),
                    "bbox": [round(v, 2) for v in word["bbox"]],
                    "note": "pdf_text_and_middle_disagree; manual_evidence_required",
                }
            )
            continue
        analysis["locators"].append(locator_item)

    _pdf_cross_check_json_marginals(pdf_index, analysis)


def _has_preceding_bekker_anchor(locators: list[dict[str, Any]], y: float) -> bool:
    """Return whether a page/column locator precedes this word on the page."""

    for item in locators:
        components = item.get("components") or {}
        box = item.get("bbox")
        if (
            item.get("role") == "locator"
            and item.get("scheme") == "bekker"
            and components.get("page") is not None
            and components.get("column") in {"a", "b"}
            and isinstance(box, (list, tuple))
            and len(box) == 4
            and (float(box[1]) + float(box[3])) / 2 <= y
        ):
            return True
    return False


def _pdf_cross_check_json_marginals(pdf_index: _PdfWordIndex, analysis: dict[str, Any]) -> None:
    """Record same-position PDF corroboration or mismatch; never normalize."""

    for item in analysis["locators"] + analysis["undetermined"]:
        raw = str(item.get("raw") or "")
        if not _DIGITS_RE.fullmatch(raw):
            continue
        box = item.get("bbox")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        near = pdf_index.word_near((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, radius=4.0)
        if near is None or not _DIGITS_RE.fullmatch(str(near.get("text") or "")):
            continue
        if str(near["text"]) == raw:
            item.setdefault("evidence", []).append("pdf_word:confirms_same_value_at_position")
        else:
            analysis["review"].append(
                {
                    "kind": "pdf_text_digit_disagreement",
                    "raw": raw,
                    "pdf_raw": str(near["text"]),
                    "block_id": item.get("block_id"),
                    "bbox": item.get("bbox"),
                    "note": "manual_evidence_required_no_automatic_digit_normalization",
                }
            )


def _locate_leading_word(text: str, token: str) -> tuple[int, int, str] | None:
    """Find one exact unique line-leading word; never trim a numeric prefix."""

    if not token:
        return None
    pattern = re.compile(r"(?m)^[ \t]*" + re.escape(token) + r"(?=$|[ \t]+)")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    start = match.start() + len(match.group(0)) - len(token)
    end = start + len(token)
    return start, end, text[start:end]


def _pdf_text_line_alignment(
    text: str,
    char_start: int,
    block_box: list[float],
    word_center_y: float,
) -> dict[str, Any] | None:
    """Check that the PDF word y aligns with the matching source text line."""

    if len(block_box) != 4 or block_box[3] <= block_box[1]:
        return None
    line_index = text[:char_start].count("\n")
    line_count = max(1, text.count("\n") + 1)
    line_height = (block_box[3] - block_box[1]) / line_count
    expected_y = block_box[1] + (line_index + 0.5) * line_height
    tolerance = max(2.5, line_height * 0.75)
    delta = abs(float(word_center_y) - expected_y)
    if delta > tolerance:
        return None
    return {
        "line_index": line_index,
        "line_count": line_count,
        "expected_y": round(expected_y, 2),
        "word_center_y": round(float(word_center_y), 2),
        "delta": round(delta, 2),
        "tolerance": round(tolerance, 2),
    }


def _has_conflicting_line_leader(text: str, token: str) -> bool:
    """Whether the same source block has a different numeric marker at start."""

    for match in re.finditer(r"(?m)^[ \t]*(\S+)", text):
        candidate = match.group(1).rstrip(".,;:")
        if candidate == token:
            continue
        if candidate.startswith(token) or _DIGITS_RE.fullmatch(candidate) or _BEKKER_RE.fullmatch(candidate):
            return True
    return False


# ---------------------------------------------------------------------------
# Human evidence (原页人工核查)
# ---------------------------------------------------------------------------


def _apply_human_evidence(
    analysis: dict[str, Any],
    evidence_page: Mapping[str, Any],
    page: Mapping[str, Any],
    source_fingerprint: str,
) -> None:
    blocks = [block for block in page.get("blocks", []) or [] if isinstance(block, Mapping)]

    def find_source(block_id: Any) -> Mapping[str, Any] | None:
        matches = [block for block in blocks if str(block.get("id") or "") == str(block_id or "")]
        return matches[0] if len(matches) == 1 else None

    def source_span(block: Mapping[str, Any], char_range: Any) -> tuple[int, int, str] | None:
        if not isinstance(char_range, (list, tuple)) or len(char_range) != 2:
            return None
        try:
            start, end = int(char_range[0]), int(char_range[1])
        except (TypeError, ValueError):
            return None
        text = str(block.get("text") or "")
        if start < 0 or end < start or end > len(text):
            return None
        return start, end, text[start:end]

    for locator in evidence_page.get("add_locator", []) or []:
        block = find_source(locator.get("block_id")) if locator.get("block_id") else None
        char_range = locator.get("char_range")
        original = locator.get("original")
        if char_range is not None or original is not None:
            if (
                block is None
                or not isinstance(char_range, (list, tuple))
                or len(char_range) != 2
                or not isinstance(original, str)
            ):
                analysis["review"].append({"kind": "human_locator_rejected", "reason": "invalid_source_span"})
                continue
            span = source_span(block, char_range)
            if span is None or span[2] != original:
                analysis["review"].append({"kind": "human_locator_rejected", "reason": "source_text_mismatch", "block_id": locator.get("block_id")})
                continue
        item = dict(locator)
        item.setdefault("role", "locator")
        item["confidence"] = "high"
        item["evidence"] = list(locator.get("evidence", [])) + ["human_page_audit"]
        item["source_fingerprint"] = source_fingerprint
        same_event: list[dict[str, Any]] = []
        if block is not None and char_range is not None and isinstance(original, str):
            same_event = [
                existing
                for existing in analysis["locators"] + analysis["undetermined"]
                if str(existing.get("block_id") or "") == str(locator.get("block_id") or "")
                and existing.get("char_range") == list(char_range)
                and (existing.get("original") == original or span[2] == original)
            ]
        if same_event:
            existing = same_event[0]
            evidence_parts = list(item["evidence"])
            for prior in same_event:
                evidence_parts.extend(prior.get("evidence") or [])
            evidence = list(dict.fromkeys(evidence_parts))
            existing.update(item)
            existing["evidence"] = evidence
            existing["original"] = original
            for duplicate in same_event[1:]:
                if duplicate in analysis["locators"]:
                    analysis["locators"].remove(duplicate)
                if duplicate in analysis["undetermined"]:
                    analysis["undetermined"].remove(duplicate)
            if existing in analysis["undetermined"]:
                analysis["undetermined"].remove(existing)
                analysis["locators"].append(existing)
            item = existing
            deduplicated = True
        else:
            analysis["locators"].append(item)
            deduplicated = False
        analysis["review"].append(
            {
                "kind": "human_added_locator",
                "locator": item.get("normalized"),
                "block_id": item.get("block_id"),
                "char_range": item.get("char_range"),
                "original": item.get("original"),
                "deduplicated_existing_event": deduplicated,
                "note": str(locator.get("note") or "原页人工核查"),
            }
        )
    for flag in evidence_page.get("flag_handwritten", []) or []:
        analysis["handwritten"].append(
            {
                "block_id": str(flag.get("block_id") or ""),
                "note": str(flag.get("note") or "原页手写批注"),
                "evidence": ["human_page_audit"],
            }
        )
        analysis["review"].append(
            {"kind": "handwritten_annotation", "block_id": flag.get("block_id"), "note": str(flag.get("note") or "")}
        )
    for fix in evidence_page.get("normalize", []) or []:
        raw = str(fix.get("raw") or "")
        char_range = fix.get("char_range")
        block_id = str(fix.get("block_id") or "")
        original = fix.get("original")
        source = find_source(block_id)
        if (
            source is None
            or not isinstance(char_range, (list, tuple))
            or len(char_range) != 2
            or not isinstance(original, str)
        ):
            analysis["review"].append({"kind": "human_normalization_rejected", "raw": raw, "reason": "missing_exact_source_span"})
            continue
        try:
            start, end = int(char_range[0]), int(char_range[1])
        except (TypeError, ValueError):
            start, end = -1, -1
        span = source_span(source, char_range)
        if span is None or span[2] != original:
            analysis["review"].append({"kind": "human_normalization_rejected", "raw": raw, "reason": "source_text_mismatch", "block_id": block_id})
            continue
        pool = analysis["locators"] + analysis["undetermined"]
        raw_compact = re.sub(r"\s+", "", raw)
        original_compact = re.sub(r"\s+", "", original)
        matches = [
            item for item in pool
            if (
                str(item.get("raw") or "") == raw
                or re.sub(r"\s+", "", str(item.get("raw") or "")) in {raw_compact, original_compact}
            )
            and str(item.get("block_id") or "") == block_id
            and item.get("char_range") == list(char_range)
            and (item.get("original") in {None, original})
        ]
        if len(matches) != 1 or not fix.get("scheme") or not isinstance(fix.get("components"), Mapping):
            analysis["review"].append({"kind": "human_normalization_rejected", "raw": raw, "reason": "ambiguous_target_or_missing_components", "block_id": block_id})
            continue
        item = matches[0]
        item["normalized"] = str(fix.get("to") or item.get("normalized") or raw)
        item["role"] = "locator"
        item["scheme"] = str(fix["scheme"])
        item["components"] = dict(fix["components"])
        item["confidence"] = "high"
        item.setdefault("notes", []).append(f"normalized_from_{raw}_human_audit")
        item.setdefault("evidence", []).append("human_page_audit")
        item["source_fingerprint"] = source_fingerprint
        if item in analysis["undetermined"]:
            analysis["undetermined"].remove(item)
            analysis["locators"].append(item)
        analysis["review"].append(
            {
                "kind": "human_normalization",
                "raw": item.get("raw"),
                "evidence_raw": raw,
                "normalized": item["normalized"],
                "block_id": block_id,
                "char_range": list(char_range),
                "original": original,
                "note": str(fix.get("note") or ""),
            }
        )

    for edit in evidence_page.get("edits", []) or []:
        block_id = str(edit.get("block_id") or "")
        source = find_source(block_id)
        char_range = edit.get("char_range")
        original = edit.get("original")
        action = str(edit.get("action") or "")
        if (
            source is None
            or not isinstance(char_range, (list, tuple))
            or len(char_range) != 2
            or not isinstance(original, str)
            or action not in {"remove_locator_token", "remove_text"}
        ):
            analysis["review"].append({"kind": "human_edit_rejected", "reason": "invalid_source_span_or_action", "block_id": block_id})
            continue
        try:
            start, end = int(char_range[0]), int(char_range[1])
        except (TypeError, ValueError):
            start, end = -1, -1
        span = source_span(source, char_range)
        if span is None or span[1] <= span[0] or span[2] != original:
            analysis["review"].append({"kind": "human_edit_rejected", "reason": "source_text_mismatch", "block_id": block_id, "char_range": list(char_range)})
            continue
        human_edit = {
                "block_id": block_id,
                "char_range": [span[0], span[1]],
                "original": original,
                "action": action,
                "reason": str(edit.get("reason") or "human_page_audit"),
                "confidence": "high",
                "evidence": ["human_page_audit"],
                "source_fingerprint": source_fingerprint,
                **({"locator": edit["locator"]} if "locator" in edit else {}),
            }
        existing_edits = [
            item for item in analysis["edits"]
            if item.get("block_id") == block_id
            and item.get("char_range") == [span[0], span[1]]
            and item.get("original") == original
        ]
        if len(existing_edits) == 1:
            existing = existing_edits[0]
            existing.update(human_edit)
            existing["evidence"] = list(dict.fromkeys(list(existing.get("evidence") or []) + human_edit["evidence"]))
        else:
            analysis["edits"].append(human_edit)


def _promote_lines_after_human_anchors(
    analysis: dict[str, Any],
    band: dict[str, float] | None,
    source_fingerprint: str,
) -> None:
    """Use a verified page/column anchor to resolve page-local line candidates.

    Only existing marginal numeric candidates from 5 through 35 are eligible.
    Values such as 80 remain unresolved until an exact human normalization is
    supplied.
    """

    anchors = [
        item for item in analysis["locators"]
        if item.get("scheme") == "bekker"
        and (item.get("components") or {}).get("page") is not None
        and (item.get("components") or {}).get("column") in {"a", "b"}
        and isinstance(item.get("bbox"), (list, tuple))
        and len(item["bbox"]) == 4
    ]
    if not anchors:
        return
    unresolved = list(analysis["undetermined"])
    for item in unresolved:
        raw = str(item.get("raw") or "")
        if not _DIGITS_RE.fullmatch(raw):
            continue
        value = int(raw)
        if value < 5 or value > 35 or not _is_multiple_of_five(value):
            continue
        box = item.get("bbox")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        item_y = (float(box[1]) + float(box[3])) / 2
        preceding = [anchor for anchor in anchors if _reading_key(anchor) <= item_y]
        if not preceding:
            continue
        anchor = max(preceding, key=_reading_key)
        anchor_box = anchor.get("bbox")
        if not isinstance(anchor_box, (list, tuple)) or len(anchor_box) != 4:
            continue
        anchor_x = (float(anchor_box[0]) + float(anchor_box[2])) / 2
        item_x = (float(box[0]) + float(box[2])) / 2
        # Preserve stream separation when left/right margins are distinct.
        if band is not None:
            anchor_side = "left" if anchor_x < band["left"] else "right" if anchor_x > band["right"] else "body"
            item_side = "left" if item_x < band["left"] else "right" if item_x > band["right"] else "body"
            if anchor_side != item_side:
                continue
        item["role"] = "locator"
        item["scheme"] = "bekker"
        item["normalized"] = raw
        item["components"] = {"page": None, "column": None, "line": value}
        item["confidence"] = "medium"
        item.setdefault("evidence", []).append("human_page_audit_context_precedes_candidate")
        item["source_fingerprint"] = source_fingerprint
        analysis["locators"].append(item)
        analysis["undetermined"].remove(item)
        analysis["review"].append(
            {
                "kind": "human_context_promoted_bekker_line",
                "raw": raw,
                "block_id": item.get("block_id"),
                "char_range": item.get("char_range"),
                "anchor": anchor.get("normalized"),
                "confidence": "medium",
            }
        )


# ---------------------------------------------------------------------------
# Range assembly and display
# ---------------------------------------------------------------------------


def _reading_key(item: Mapping[str, Any]) -> float:
    box = item.get("bbox")
    if isinstance(box, (list, tuple)) and len(box) == 4:
        return float(box[1] + box[3]) / 2
    return 1e9



def _source_ref(item: Mapping[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "block_id": item.get("block_id"),
        "char_range": item.get("char_range"),
        "raw": item.get("raw"),
    }
    if isinstance(item.get("components"), Mapping):
        ref["components"] = dict(item["components"])
    if item.get("normalized") is not None:
        ref["normalized"] = item.get("normalized")
    if isinstance(item.get("bbox"), (list, tuple)) and len(item["bbox"]) == 4:
        ref["bbox"] = list(item["bbox"])
    return ref


def _boundary_refs(start: Mapping[str, Any] | None, end: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep the observed source markers that actually define a displayed range.

    A page/column anchor may provide context for line numbers much farther down
    the page, but it is not the displayed range's start when the range starts
    with a line number. Boundary inference must use the visible endpoint.
    """

    return {
        "start": _source_ref(start) if start is not None else {},
        "end": _source_ref(end) if end is not None else {},
    }


def _locator_stream_key(item: Mapping[str, Any], band: dict[str, float] | None) -> str:
    explicit = item.get("stream_id") or item.get("language") or item.get("text_stream")
    if explicit:
        return f"stream:{explicit}"
    box = item.get("bbox")
    if band and isinstance(box, (list, tuple)) and len(box) == 4:
        center_x = (float(box[0]) + float(box[2])) / 2
        # Page/column labels and line numbers often sit on opposite sides of
        # the estimated body-band edge while belonging to the same text flow.
        # Use the physical page half as a conservative stream proxy; explicit
        # language/stream identifiers take precedence above.
        if center_x < band["width"] / 2:
            return "side:left"
        return "side:right"
    return "stream:unknown"


def _context_is_contiguous(start: Mapping[str, Any], end: Mapping[str, Any]) -> bool:
    start_page, end_page = start.get("page"), end.get("page")
    start_col, end_col = start.get("column"), end.get("column")
    if start_page is None or end_page is None or not start_col or not end_col:
        return False
    if start_page == end_page:
        return (start_col, end_col) in {("a", "b")}
    return int(end_page) == int(start_page) + 1 and start_col == "b" and end_col == "a"


def _bekker_span_display(
    start: Mapping[str, Any],
    start_line: Any,
    end: Mapping[str, Any],
    end_line: Any,
) -> str:
    first = _bekker_display(start, line=start_line)
    if start.get("page") == end.get("page"):
        tail = f"{end.get('column') or ''}{end_line if end_line is not None else ''}"
    else:
        tail = _bekker_display(end, line=end_line)
    if first == tail:
        return first
    return f"{first}-{tail}"


def _assemble_ranges(
    page: Mapping[str, Any],
    analysis: dict[str, Any],
    band: dict[str, float] | None,
    pdf_index: _PdfWordIndex | None = None,
) -> None:
    locators = [item for item in analysis["locators"] if item.get("role") == "locator"]
    by_scheme_stream: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in locators:
        scheme = str(item.get("scheme") or "unknown")
        stream = _locator_stream_key(item, band) if scheme == "bekker" else str(item.get("stream_id") or item.get("language") or "default")
        by_scheme_stream.setdefault((scheme, stream), []).append(item)

    for (scheme, stream), items in by_scheme_stream.items():
        items.sort(key=lambda item: (_reading_key(item), float(item.get("bbox", [0, 0])[0]) if isinstance(item.get("bbox"), (list, tuple)) else 0.0))
        if scheme in {"generic_line", "numeric_margin"}:
            continue
        if scheme != "bekker":
            for item in items:
                analysis["ranges"].append(
                    {
                        "scheme": scheme,
                        "stream_id": stream,
                        "display": str(item.get("normalized") or item.get("raw")),
                        "items": [item.get("normalized")],
                        "source_items": [_source_ref(item)],
                        "boundary_refs": _boundary_refs(item, item),
                        "start_boundary": "unknown",
                        "end_boundary": "unknown",
                        "single_point": True,
                        "reading_y": _reading_key(item),
                    }
                )
            continue

        chunks: list[dict[str, Any]] = []
        context: dict[str, Any] | None = None
        current: list[dict[str, Any]] = []
        anchor: dict[str, Any] | None = None

        def flush() -> None:
            nonlocal current, context, anchor
            if context is not None and (current or anchor is not None):
                chunks.append(
                    {
                        "context": dict(context),
                        "items": list(current),
                        "anchor": anchor,
                        "source_items": ([anchor] if anchor is not None else []) + [item for item in current if item is not anchor],
                    }
                )
            current = []
            context = None
            anchor = None

        for item in items:
            components = item.get("components") or {}
            page_num = components.get("page")
            column = components.get("column")
            line = components.get("line")
            has_context = page_num is not None and column in {"a", "b"}
            has_line = line is not None

            if page_num is not None and not has_context:
                # A page number with no readable column interrupts the prior
                # context. Do not let following bare lines inherit it.
                flush()
                analysis["review"].append(
                    {
                        "kind": "bekker_locator_precision_unresolved",
                        "raw": item.get("raw"),
                        "block_id": item.get("block_id"),
                    }
                )
                continue

            if has_context:
                next_context = {"page": int(page_num), "column": column}
                if context is None:
                    context = next_context
                    anchor = item
                elif context != next_context:
                    flush()
                    context = next_context
                    anchor = item
                elif anchor is None:
                    anchor = item
                if has_line:
                    current.append(item)
                continue

            if has_line:
                if context is None or not context.get("column"):
                    analysis["review"].append(
                        {
                            "kind": "bekker_line_without_page_column_context",
                            "raw": item.get("raw"),
                            "block_id": item.get("block_id"),
                            "char_range": item.get("char_range"),
                        }
                    )
                    continue
                if current:
                    previous = current[-1].get("components") or {}
                    previous_line = previous.get("line")
                    try:
                        step = int(line) - int(previous_line)
                    except (TypeError, ValueError):
                        step = -1
                    if step not in {5, 10, 15, 20, 25, 30}:
                        prior_context = dict(context)
                        flush()
                        context = prior_context
                        analysis["review"].append(
                            {
                                "kind": "bekker_line_sequence_split",
                                "previous": previous_line,
                                "raw": item.get("raw"),
                                "reason": "non_monotone_or_implausible_step",
                            }
                        )
                current.append(item)
                continue

            # Page-only Bekker events without a column are retained as points
            # under their raw, typed scheme; they do not create line context.
            analysis["review"].append(
                {
                    "kind": "bekker_locator_precision_unresolved",
                    "raw": item.get("raw"),
                    "block_id": item.get("block_id"),
                }
            )

        flush()

        index = 0
        while index < len(chunks):
            first_chunk = chunks[index]
            start_ctx = first_chunk["context"]
            first_lines = first_chunk["items"]
            if not first_lines:
                display = _bekker_display(start_ctx)
                source_items = first_chunk["source_items"]
                y = min((_reading_key(i) for i in source_items), default=1e9)
                endpoint = first_chunk.get("anchor")
                analysis["ranges"].append(
                    {
                        "scheme": scheme,
                        "stream_id": stream,
                        "display": display,
                        "items": [display],
                        "source_items": [_source_ref(i) for i in source_items],
                        "boundary_refs": _boundary_refs(endpoint, endpoint),
                        "start_boundary": "unknown",
                        "end_boundary": "unknown",
                        "single_point": True,
                        "reading_y": y,
                    }
                )
                index += 1
                continue

            start_line = (first_lines[0].get("components") or {}).get("line")
            end_ctx = start_ctx
            end_line = (first_lines[-1].get("components") or {}).get("line")
            start_endpoint = first_lines[0]
            end_endpoint = first_lines[-1]
            source_items = list(first_chunk["source_items"])
            last_y = _reading_key(first_lines[-1])
            next_index = index + 1
            while first_chunk.get("anchor") is not None and next_index < len(chunks):
                next_chunk = chunks[next_index]
                if next_chunk.get("anchor") is None or not _context_is_contiguous(end_ctx, next_chunk["context"]):
                    break
                end_ctx = next_chunk["context"]
                next_lines = next_chunk["items"]
                if next_lines:
                    end_line = (next_lines[-1].get("components") or {}).get("line")
                    end_endpoint = next_lines[-1]
                    last_y = _reading_key(next_lines[-1])
                else:
                    end_line = None
                    end_endpoint = next_chunk.get("anchor")
                source_items.extend(next_chunk["source_items"])
                next_index += 1

            if next_index > index + 1:
                display = _bekker_span_display(start_ctx, start_line, end_ctx, end_line)
                all_line_items = first_lines + [
                    item for chunk in chunks[index + 1:next_index] for item in chunk["items"]
                ]
                y = min((_reading_key(i) for i in source_items), default=1e9)
                analysis["ranges"].append(
                    {
                        "scheme": scheme,
                        "stream_id": stream,
                        "display": display,
                        "items": [str(item.get("normalized") or item.get("raw")) for item in all_line_items],
                        "source_items": [_source_ref(i) for i in source_items],
                        "boundary_refs": _boundary_refs(start_endpoint, end_endpoint),
                        "start_boundary": "unknown",
                        "end_boundary": "unknown",
                        "single_point": False,
                        "reading_y": y,
                    }
                )
                index = next_index
                continue

            display = _bekker_range_display(
                start_ctx,
                first_line=start_line,
                last_line=end_line,
            )
            y = min((_reading_key(i) for i in source_items), default=1e9)
            analysis["ranges"].append(
                {
                    "scheme": scheme,
                    "stream_id": stream,
                    "display": display,
                    "items": [str(item.get("normalized") or item.get("raw")) for item in first_lines],
                    "source_items": [_source_ref(i) for i in source_items],
                    "boundary_refs": _boundary_refs(start_endpoint, end_endpoint),
                    "start_boundary": "unknown",
                    "end_boundary": "unknown",
                    "single_point": len(first_lines) == 1 and start_line == end_line,
                    "reading_y": y,
                }
            )
            index += 1

    analysis["ranges"].sort(key=lambda entry: (entry.get("reading_y", 1e9), entry.get("scheme", "")))
    _annotate_boundaries(page, analysis, band, pdf_index)


def _bekker_display(ctx: Mapping[str, Any], *, line: Any = None) -> str:
    base = f"{ctx.get('page')}{ctx.get('column') or ''}"
    if line is not None and str(line) != "None":
        base = f"{base}{line}"
    return base


def _bekker_range_display(ctx: Mapping[str, Any], *, first_line: Any, last_line: Any) -> str:
    start = _bekker_display(ctx, line=first_line)
    if start == _bekker_display(ctx, line=last_line):
        return start
    end_tail = f"{ctx.get('column') or ''}{last_line}" if last_line is not None else f"{ctx.get('column') or ''}"
    return f"{start}-{end_tail}"


def _annotate_boundaries(
    page: Mapping[str, Any],
    analysis: dict[str, Any],
    band: dict[str, float] | None,
    pdf_index: _PdfWordIndex | None = None,
) -> None:
    """Mark extension only when prose brackets this range in the same text lane."""

    if band is None:
        return
    prose_boxes: list[list[float]] = []
    footnote_boxes: list[list[float]] = []
    for block in page.get("blocks", []) or []:
        if not isinstance(block, Mapping):
            continue
        box = _bbox(block, page)
        block_type = str(block.get("type") or "")
        if box is not None and _is_footnote_block(block):
            footnote_boxes.append(box)
        if block_type in _PROSE_BLOCK_TYPES and not _is_footnote_block(block) and box is not None and (box[2] - box[0]) >= band["width"] * 0.2:
            prose_boxes.append(box)

    def lane_for(locator_box: list[float]) -> list[list[float]]:
        center_x = (locator_box[0] + locator_box[2]) / 2
        if center_x < band["left"]:
            candidates = [box for box in prose_boxes if abs(box[0] - band["left"]) <= max(12.0, band["width"] * 0.08)]
        elif center_x > band["right"]:
            candidates = [box for box in prose_boxes if abs(box[2] - band["right"]) <= max(12.0, band["width"] * 0.08)]
        else:
            candidates = [box for box in prose_boxes if box[0] <= center_x <= box[2]]
        return candidates

    for entry in analysis["ranges"]:
        if entry.get("scheme") != "bekker":
            continue
        refs = entry.get("source_items") or []
        boundary_refs = entry.get("boundary_refs") if isinstance(entry.get("boundary_refs"), Mapping) else {}
        first_ref = boundary_refs.get("start") if isinstance(boundary_refs.get("start"), Mapping) else None
        last_ref = boundary_refs.get("end") if isinstance(boundary_refs.get("end"), Mapping) else None
        # Backward-compatible fallback for direct callers constructing old
        # range records; resolver caches are versioned and will be rebuilt.
        if first_ref is None and refs and isinstance(refs[0], Mapping):
            first_ref = refs[0]
        if last_ref is None and refs and isinstance(refs[-1], Mapping):
            last_ref = refs[-1]
        if first_ref is None or last_ref is None:
            continue
        first_box, last_box = first_ref.get("bbox"), last_ref.get("bbox")
        if not (
            isinstance(first_box, (list, tuple)) and len(first_box) == 4
            and isinstance(last_box, (list, tuple)) and len(last_box) == 4
        ):
            continue
        top_lane = lane_for(first_box)
        bottom_lane = lane_for(last_box)
        threshold = max(4.0, band["height"] * 0.015)
        first_y = (float(first_box[1]) + float(first_box[3])) / 2
        last_y = (float(last_box[1]) + float(last_box[3])) / 2
        if pdf_index is not None:
            body_words = []
            for word in pdf_index.records:
                if word.get("margin_side"):
                    continue
                box = word.get("bbox")
                if not isinstance(box, (list, tuple)) or len(box) != 4:
                    continue
                center_x = float(word["center_x"])
                center_y = float(word["center_y"])
                if not band["left"] - 1 <= center_x <= band["right"] + 1:
                    continue
                if not any(
                    prose_box[0] <= center_x <= prose_box[2]
                    and prose_box[1] <= center_y <= prose_box[3]
                    for prose_box in prose_boxes
                ):
                    continue
                if any(fbox[0] <= center_x <= fbox[2] and fbox[1] <= center_y <= fbox[3] for fbox in footnote_boxes):
                    continue
                token = str(word.get("pdf_text") or word.get("text") or "").strip()
                if not token or _DIGITS_RE.fullmatch(token) or (len(token) <= 1 and token.isalpha()):
                    continue
                body_words.append(word)
            if any(float(word["center_y"]) < float(first_box[1]) - threshold for word in body_words):
                entry["start_boundary"] = "extends"
            if any(float(word["center_y"]) > float(last_box[3]) + threshold for word in body_words):
                entry["end_boundary"] = "extends"
        else:
            from aih_contexture.middle.native_geometry import native_words
            source_words = [word for block in page.get('blocks', [])
                if isinstance(block, Mapping) and block.get('type') in _PROSE_BLOCK_TYPES
                and not _is_footnote_block(block)
                for word in native_words(block, page)
                if len(word['raw']) > 1 and not word['raw'].isdigit()]
            def in_lane(word, lane):
                return any(box[0] <= word['x'] <= box[2] and box[1] <= word['y'] <= box[3] for box in lane)
            if any(in_lane(word, top_lane) and word['y'] < float(first_box[1]) - threshold for word in source_words):
                entry['start_boundary'] = 'extends'
            if any(in_lane(word, bottom_lane) and word['y'] > float(last_box[3]) + threshold for word in source_words):
                entry['end_boundary'] = 'extends'
            # Without usable word coordinates, only a separate prose block wholly
            # beyond the locator can establish extension. A block that merely
            # overlaps a marker is not enough to assert page-boundary status.
            if any(box[3] < float(first_box[1]) - threshold for box in top_lane):
                entry["start_boundary"] = "extends"
            if any(box[1] > float(last_box[3]) + threshold for box in bottom_lane):
                entry["end_boundary"] = "extends"


def format_range_comment(entry: Mapping[str, Any]) -> str:
    display = str(entry.get("display") or "").strip()
    display = display.replace("-->", "- >").replace("--", "- -")
    if entry.get("scheme") == "generic_line":
        return f"<!-- {display} -->"
    prefix = "…" if entry.get("start_boundary") == "extends" else ""
    suffix = "…" if entry.get("end_boundary") == "extends" else ""
    return f"<!-- {prefix}{display}{suffix} -->"


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def _record_margin_sides(data: dict[str, Any]) -> None:
    """Keep placement and audit geometry in JSON rather than reading comments."""
    for page in data.get('pages') or []:
        if not isinstance(page, dict):
            continue
        analysis = (page.get('attrs') or {}).get(PAGE_ATTR_KEY) or {}
        by_id = {str(b.get('id') or ''):b for b in page.get('blocks',[]) if isinstance(b,dict)}
        for key in ('text_marginalia','undetermined','handwritten'):
            for item in analysis.get(key) or []:
                if isinstance(item, dict):
                    item['side'] = classical_margin_side(page, by_id.get(str(item.get('block_id') or '')), item) or 'unknown'


def resolve_classical_marginalia(
    middle_json: dict[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
    pdf_words_by_page: Mapping[int, list[dict[str, Any]]] | None = None,
    evidence: Mapping[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Analyse and cache classical marginalia per page (input stays immutable).

    Returns a deep copy carrying ``page.attrs.classical_marginalia`` records
    plus ``metadata.classical_marginalia_resolution``. Results are reused when
    the stored version and config signature match; ``force=True`` re-analyses.
    """
    middle_json = decode_middle_storage(middle_json)

    if not isinstance(middle_json, dict):
        return copy.deepcopy(middle_json)
    mode = normalize_classical_marginalia_mode((config or {}).get("classical_marginalia_mode"))
    data = copy.deepcopy(middle_json)
    # The default/off path is deliberately transparent: no analysis metadata,
    # candidates, edits, or normalization are added.
    if mode == "off":
        return data

    data = storage_numbers(data)

    signature = classical_marginalia_config_signature(config)
    source_fingerprint = middle_source_fingerprint(middle_json)
    pdf_fingerprint = (
        _fingerprint({str(key): value for key, value in pdf_words_by_page.items()})
        if pdf_words_by_page is not None
        else None
    )
    valid_evidence, rejected_evidence = _valid_human_evidence(evidence, source_fingerprint)
    human_fingerprint = _fingerprint(valid_evidence) if valid_evidence is not None else None
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        data["metadata"] = metadata

    cached = metadata.get(METADATA_KEY)
    cached_inputs = cached.get("cache_inputs") if isinstance(cached, dict) else None
    pages = data.get("pages", []) or []
    page_caches_valid = all(
        isinstance(page, Mapping)
        and isinstance(page.get("attrs"), Mapping)
        and isinstance(page["attrs"].get(PAGE_ATTR_KEY), Mapping)
        and page["attrs"][PAGE_ATTR_KEY].get("version") == CLASSICAL_MARGINALIA_VERSION
        and page["attrs"][PAGE_ATTR_KEY].get("source_fingerprint") == source_fingerprint
        for page in pages
    )
    cache_matches = bool(
        isinstance(cached, dict)
        and cached.get("version") == CLASSICAL_MARGINALIA_VERSION
        and cached.get("config_signature") == signature
        and cached.get("source_fingerprint") == source_fingerprint
        and isinstance(cached_inputs, Mapping)
        and page_caches_valid
        and cached.get("completed") is True
    )
    pdf_matches = pdf_words_by_page is None or (
        isinstance(cached_inputs, Mapping)
        and cached_inputs.get("pdf_supplement_fingerprint") == pdf_fingerprint
    )
    human_matches = valid_evidence is None or (
        isinstance(cached_inputs, Mapping)
        and cached_inputs.get("human_evidence_fingerprint") == human_fingerprint
    )
    # 0.5 tightens coordinate trust only. Preserve previously audited source-
    # bound results if every stored source/candidate box satisfies the new
    # rules. Otherwise reanalyse; never grandfather the mixed-unit defect.
    legacy_signature = hashlib.sha256(json_dumps_compact({
        "version": "classical-marginalia/0.4", "classical_marginalia_mode": mode,
    }).encode("utf-8")).hexdigest()[:16]
    legacy_matches = (
        not force and isinstance(cached, dict)
        and cached.get("version") == "classical-marginalia/0.4"
        and cached.get("completed") is True
        and cached.get("source_fingerprint") == source_fingerprint
        and cached.get("config_signature") == legacy_signature
        and isinstance(cached_inputs, Mapping) and pdf_matches and human_matches
    )
    if legacy_matches:
        for page in pages:
            analysis = (page.get("attrs") or {}).get(PAGE_ATTR_KEY, {})
            if analysis.get("version") != "classical-marginalia/0.4" or analysis.get("source_fingerprint") != source_fingerprint:
                legacy_matches = False;break
            items = list(page.get("blocks") or [])
            for key in ("locators", "restores", "text_marginalia"):
                items.extend(analysis.get(key) or [])
            if any(isinstance(item, Mapping) and item.get("bbox") is not None
                   and not classical_bbox_is_trustworthy(item["bbox"], page, item) for item in items):
                legacy_matches = False;break
    if legacy_matches:
        for page in pages:
            page["attrs"][PAGE_ATTR_KEY]["version"] = CLASSICAL_MARGINALIA_VERSION
        cached.update(version=CLASSICAL_MARGINALIA_VERSION, config_signature=signature,
                      cache_migrated_from="classical-marginalia/0.4")
        if rejected_evidence:
            cached["rejected_human_evidence"] = rejected_evidence
        _record_margin_sides(data)
        return data
    if not force and cache_matches and pdf_matches and human_matches:
        if rejected_evidence:
            metadata[METADATA_KEY]["rejected_human_evidence"] = rejected_evidence
        return data

    stored_pdf_fingerprint = pdf_fingerprint if pdf_fingerprint is not None else "absent"
    stored_human_fingerprint = human_fingerprint if human_fingerprint is not None else "absent"

    book_line_scheme = _detect_book_line_scheme(data.get("pages", []) or [])

    counts: dict[str, int] = {}
    for page in data.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        page_analysis = _analyse_page(
            page,
            pdf_words=(pdf_words_by_page or {}).get(int(page.get("index", 0))),
            evidence_page=_evidence_for_page(valid_evidence, page),
            book_line_scheme=book_line_scheme,
            source_fingerprint=source_fingerprint,
        )
        page_analysis["source_fingerprint"] = source_fingerprint
        for edit in page_analysis.get("edits", []) or []:
            edit.setdefault("source_fingerprint", source_fingerprint)
        attrs = page.get("attrs")
        if not isinstance(attrs, dict):
            attrs = {}
            page["attrs"] = attrs
        attrs[PAGE_ATTR_KEY] = page_analysis
        for key in (
            "pages",
            "locators",
            "ranges",
            "text_marginalia",
            "restores",
            "printed_page_duplicates",
            "empty_margin_boxes",
            "edits",
            "review",
            "undetermined",
        ):
            value = len(page_analysis.get(key, [])) if key != "pages" else 1
            counts[key] = counts.get(key, 0) + value

    metadata[METADATA_KEY] = {
        "version": CLASSICAL_MARGINALIA_VERSION,
        "completed": True,
        "config_signature": signature,
        "source_fingerprint": source_fingerprint,
        "pdf_supplement_fingerprint": stored_pdf_fingerprint,
        "human_evidence_fingerprint": stored_human_fingerprint,
        "cache_inputs": {
            "source_fingerprint": source_fingerprint,
            "pdf_supplement_fingerprint": stored_pdf_fingerprint,
            "human_evidence_fingerprint": stored_human_fingerprint,
        },
        "counts": {k: v for k, v in counts.items() if v},
        "with_pdf_supplement": bool(pdf_words_by_page),
        "with_human_evidence": bool(valid_evidence),
    }
    if rejected_evidence:
        metadata[METADATA_KEY]["rejected_human_evidence"] = rejected_evidence
    _record_margin_sides(data)
    return data


def _evidence_for_page(evidence: Mapping[str, Any] | None, page: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if not isinstance(evidence, Mapping):
        return None
    pages = evidence.get("pages")
    if not isinstance(pages, Mapping):
        return None
    found = pages.get(str(page.get("index")), pages.get(page.get("index")))
    return found if isinstance(found, Mapping) else None


def analyze_generic_line_numbers(page: dict[str, Any], analysis: dict[str, Any], band: dict[str, float] | None) -> None:
    from aih_contexture.middle.generic_line_numbers import analyze_generic_lines
    analyze_generic_lines(page, analysis)


def _analyse_page(
    page: dict[str, Any],
    *,
    pdf_words: list[dict[str, Any]] | None,
    evidence_page: Mapping[str, Any] | None,
    book_line_scheme: bool = False,
    source_fingerprint: str = "",
) -> dict[str, Any]:
    capability = classical_marginalia_capabilities({"pages": [page]})
    if capability["status"] == "unavailable":
        analysis = {
            "version": CLASSICAL_MARGINALIA_VERSION,
            **{key: [] for key in ("locators", "ranges", "text_marginalia", "restores", "printed_page_duplicates", "empty_margin_boxes", "edits", "review", "undetermined", "handwritten", "notes")},
            "capabilities": capability,
        }
        for block in page.get("blocks", []) or []:
            if not isinstance(block, Mapping) or block.get("type") != "MarginalNote":
                continue
            raw = str(block.get("text") or "")
            if raw.strip():
                analysis["undetermined"].append({
                    "block_id": block.get("id"), "raw": raw, "original": raw,
                    "char_range": [0, len(raw)], "bbox": None, "role": "undetermined",
                    "confidence": "low", "evidence": ["geometry:unavailable"],
                    "notes": ["no_locator_inference_without_trustworthy_page_geometry"],
                    "side": classical_margin_side(page, block, None) or "unknown",
                })
        analysis["notes"].append("classical_analysis_unavailable_missing_geometry")
        if evidence_page:
            analysis["review"].append({"kind": "human_evidence_not_applied_missing_geometry"})
        return analysis
    band = _estimate_body_band(page)
    if band is not None:
        band["top"] = min(
            (
                box[1]
                for box in (
                    _bbox(b, page) for b in page.get("blocks", []) or [] if isinstance(b, Mapping)
                )
                if box
            ),
            default=0.0,
        )
        band["prose_top"] = min(
            (
                box[1]
                for box in (
                    _bbox(b, page)
                    for b in page.get("blocks", []) or []
                    if isinstance(b, Mapping) and str(b.get("type") or "").startswith(_PROSE_WIDE_TYPE_PREFIXES)
                )
                if box
            ),
            default=band["top"],
        )

    candidates = _collect_marginal_candidates(page, band)
    candidates.extend(_collect_stray_text_candidates(page, band))

    context: dict[str, Any] = {
        "page_has_line_sequence": _detect_line_sequence(candidates),
        "book_line_scheme": book_line_scheme,
    }
    _classify_candidates(page, candidates, band, context)

    analysis: dict[str, Any] = {
        "version": CLASSICAL_MARGINALIA_VERSION,
        "locators": [],
        "ranges": [],
        "text_marginalia": [],
        "restores": [],
        "printed_page_duplicates": [],
        "empty_margin_boxes": [],
        "edits": [],
        "review": [],
        "undetermined": [],
        "handwritten": [],
        "notes": [],
    }

    def candidate_item(candidate: _Candidate) -> dict[str, Any]:
        item = candidate.item()
        blocks = page.get("blocks", []) or []
        if 0 <= candidate.block_index < len(blocks):
            source_block = blocks[candidate.block_index]
            if isinstance(source_block, Mapping):
                text = str(source_block.get("text") or "")
                if 0 <= candidate.char_start <= candidate.char_end <= len(text):
                    item["original"] = text[candidate.char_start:candidate.char_end]
        return item

    for candidate in candidates:
        if candidate.role == "empty":
            analysis["empty_margin_boxes"].append(candidate_item(candidate))
        elif candidate.role == "locator":
            item = candidate_item(candidate)
            analysis["locators"].append(item)
            if candidate.source_type == "stray_text":
                source_block = (page.get("blocks", []) or [])[candidate.block_index]
                source_text = str(source_block.get("text") or "") if isinstance(source_block, Mapping) else ""
                if source_text[candidate.char_start:candidate.char_end] == candidate.raw:
                    analysis["edits"].append(
                        {
                            "block_id": candidate.block_id,
                            "char_range": [candidate.char_start, candidate.char_end],
                            "original": candidate.raw,
                            "action": "remove_locator_token",
                            "reason": "confirmed_bekker_marker_in_text_block",
                            "confidence": candidate.confidence,
                            "evidence": list(candidate.evidence),
                            "locator": candidate.normalized,
                        }
                    )
                else:
                    analysis["review"].append(
                        {
                            "kind": "stray_text_edit_rejected",
                            "block_id": candidate.block_id,
                            "char_range": [candidate.char_start, candidate.char_end],
                            "reason": "source_text_mismatch",
                        }
                    )
        elif candidate.role == "printed_page_number":
            analysis["printed_page_duplicates"].append(candidate_item(candidate))
        elif candidate.role == "text_marginal":
            analysis["text_marginalia"].append(candidate_item(candidate))
        elif candidate.role == "misclassified_body":
            analysis["restores"].append(candidate_item(candidate))
        elif candidate.role == "undetermined":
            item = candidate_item(candidate)
            analysis["undetermined"].append(item)
            analysis["review"].append(
                {
                    "kind": "undetermined_candidate",
                    "raw": item.get("raw"),
                    "block_id": item.get("block_id"),
                    "char_range": item.get("char_range"),
                    "reason": item.get("notes") or item.get("evidence"),
                }
            )

    from aih_contexture.middle.native_geometry import analyze_native_margins
    analyze_native_margins(page, analysis)
    analyze_generic_line_numbers(page, analysis, band)
    pdf_index = None
    if pdf_words:
        pdf_index = _PdfWordIndex(list(pdf_words), page, band)
        _pdf_supplement_for_page(page, band, pdf_index, analysis, book_line_scheme=book_line_scheme)

    if evidence_page is not None:
        _apply_human_evidence(analysis, evidence_page, page, source_fingerprint)
        _promote_lines_after_human_anchors(analysis, band, source_fingerprint)

    _assemble_ranges(page, analysis, band, pdf_index)
    return analysis


def page_locator_comments(page: Mapping[str, Any], *, generic_line_output_mode: str = 'drop') -> list[str]:
    """Page-top locator comments for a page carrying a classical analysis record."""

    attrs = page.get("attrs")
    if not isinstance(attrs, dict):
        return []
    analysis = attrs.get(PAGE_ATTR_KEY)
    if not isinstance(analysis, dict):
        return []
    comments: list[str] = []
    for entry in analysis.get("ranges", []) or []:
        if entry.get('scheme') == 'generic_line' and generic_line_output_mode == 'drop':
            continue
        comments.append(format_range_comment(entry))
    return comments
