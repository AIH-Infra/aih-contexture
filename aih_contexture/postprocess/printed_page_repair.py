import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any

from aih_contexture.postprocess.reporting import PrintedPageAction

PAGE_ANCHOR_RE = re.compile(r"(?m)^\{(\d+)\}\s*$")
PAGE_COMMENT_RE = re.compile(r"<!--\s*Page:\s*(.*?)\s*-->", re.IGNORECASE)
ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
ARABIC_RE = re.compile(r"^\d+$")


@dataclass
class ParsedPageBlock:
    pdf_page: int
    raw_block: str
    raw_candidate: str | None
    normalized_candidate: str | None
    candidate_kind: str


@dataclass
class PrintedPageCandidate:
    value: str | None
    action: str
    reason_tag: str
    confidence: float


@dataclass
class PrintedPageReviewPage:
    pdf_page: int
    current_value: str | None
    current_kind: str
    segment_kind: str
    candidates: list[PrintedPageCandidate]


@dataclass
class PrintedPageReviewSpan:
    start_pdf_page: int
    end_pdf_page: int
    pages: list[PrintedPageReviewPage]
    left_anchor_value: str | None
    right_anchor_value: str | None
    segment_kind: str


@dataclass
class PageObservation:
    pdf_page: int
    raw_candidate: str | None
    normalized_candidate: str | None
    candidate_kind: str
    numeric_value: int | None
    lexical_score: float
    local_sequence_score: float
    offset_score: float
    anomaly_score: float
    anchor_score: float
    anchor_class: str
    is_boundary_candidate: bool
    is_anomaly_candidate: bool


@dataclass
class PageSegment:
    start_pdf_page: int
    end_pdf_page: int
    dominant_kind: str
    status: str
    page_count: int
    stable_page_count: int
    boundary_page_count: int
    anchor_classes: list[str]
    confidence: float


@dataclass
class QueryZone:
    zone_type: str
    start_pdf_page: int
    end_pdf_page: int
    reason: str
    dominant_kind: str
    confidence: float


def parse_markdown_pages(markdown: str) -> list[ParsedPageBlock]:
    matches = list(PAGE_ANCHOR_RE.finditer(markdown or ""))
    pages: list[ParsedPageBlock] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        block = markdown[start:end]
        comment_match = PAGE_COMMENT_RE.search(block)
        raw_candidate = comment_match.group(1).strip() if comment_match else None
        normalized = normalize_candidate(raw_candidate)
        pages.append(
            ParsedPageBlock(
                pdf_page=int(match.group(1)),
                raw_block=block,
                raw_candidate=raw_candidate or None,
                normalized_candidate=normalized,
                candidate_kind=detect_candidate_kind(normalized),
            )
        )
    return pages


def normalize_candidate(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    cleaned = re.sub(r"^[\s\.,;:!?)\]\}]+|[\s\.,;:!?)\]\}]+$", "", cleaned)
    if not cleaned:
        return None
    if ARABIC_RE.match(cleaned):
        number = int(cleaned)
        if 0 < number < 10000:
            return str(number)
        return None
    if ROMAN_RE.match(cleaned):
        return cleaned.upper()
    return None


def detect_candidate_kind(value: str | None) -> str:
    if not value:
        return "unknown"
    if value.isdigit():
        return "arabic"
    if ROMAN_RE.match(value):
        return "roman"
    return "unknown"


def _replace_block_comment(block: str, final_value: str | None) -> str:
    has_comment = bool(PAGE_COMMENT_RE.search(block))
    if final_value is None:
        return PAGE_COMMENT_RE.sub("", block, count=1) if has_comment else block

    replacement = f"<!-- Page: {final_value} -->"
    if has_comment:
        return PAGE_COMMENT_RE.sub(replacement, block, count=1)

    anchor_match = PAGE_ANCHOR_RE.search(block)
    if not anchor_match:
        return block

    anchor_end = anchor_match.end()
    remainder = block[anchor_end:]
    if remainder.startswith("\r\n"):
        return f"{block[:anchor_end]}\r\n{replacement}{remainder}"
    if remainder.startswith("\n"):
        return f"{block[:anchor_end]}\n{replacement}{remainder}"
    return f"{block[:anchor_end]}\n{replacement}{remainder}"


def _get_segment_kind(pages: list[ParsedPageBlock], idx: int) -> str:
    counts = {"arabic": 0, "roman": 0}
    for cursor in range(max(0, idx - 3), min(len(pages), idx + 4)):
        kind = pages[cursor].candidate_kind
        if kind in counts:
            counts[kind] += 1
    if counts["arabic"] and counts["roman"]:
        return "mixed"
    if counts["arabic"]:
        return "arabic"
    if counts["roman"]:
        return "roman"
    return "unknown"


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def _numeric_value_for_kind(value: str | None, kind: str) -> int | None:
    if not value:
        return None
    if kind == "arabic" and value.isdigit():
        return int(value)
    if kind == "roman":
        return _roman_to_int(value)
    return None


def _kind_histogram(pages: list[ParsedPageBlock]) -> dict[str, int]:
    counts = Counter(page.candidate_kind for page in pages)
    return {
        "arabic": counts.get("arabic", 0),
        "roman": counts.get("roman", 0),
        "unknown": counts.get("unknown", 0),
    }


def _build_page_observations(pages: list[ParsedPageBlock]) -> list[PageObservation]:
    observations: list[PageObservation] = []
    dominant_kind = "unknown"
    histogram = _kind_histogram(pages)
    if histogram["arabic"] and histogram["roman"]:
        dominant_kind = "mixed"
    elif histogram["arabic"]:
        dominant_kind = "arabic"
    elif histogram["roman"]:
        dominant_kind = "roman"

    for idx, page in enumerate(pages):
        kind = page.candidate_kind
        numeric_value = _numeric_value_for_kind(page.normalized_candidate, kind)
        lexical_score = 0.96 if page.normalized_candidate is not None else (0.18 if page.raw_candidate else 0.0)

        prev_pair, next_pair = _nearest_values_by_kind(pages, idx, kind) if kind in {"arabic", "roman"} else (None, None)
        local_sequence_score = 0.0
        offset_score = 0.0
        boundary_candidate = False
        anomaly_candidate = False

        if kind in {"arabic", "roman"} and numeric_value is not None:
            exact_target = None
            if kind == "arabic":
                exact_target, _, _ = _infer_arabic_target(pages, idx)
            else:
                exact_target, _, _ = _infer_roman_target(pages, idx)
            if exact_target == page.normalized_candidate:
                local_sequence_score = 1.0
                offset_score = 1.0
            elif prev_pair or next_pair:
                local_sequence_score = 0.55
                offset_score = 0.5
            else:
                local_sequence_score = 0.2
                offset_score = 0.2

            if prev_pair and next_pair:
                boundary_candidate = detect_candidate_kind(prev_pair[1]) != detect_candidate_kind(next_pair[1])
                if kind == "arabic":
                    left_projection = int(prev_pair[1]) + (idx - prev_pair[0])
                    right_projection = int(next_pair[1]) - (next_pair[0] - idx)
                else:
                    prev_num = _roman_to_int(prev_pair[1])
                    next_num = _roman_to_int(next_pair[1])
                    left_projection = prev_num + (idx - prev_pair[0]) if prev_num is not None else None
                    right_projection = next_num - (next_pair[0] - idx) if next_num is not None else None
                if left_projection is not None and right_projection is not None and abs(left_projection - right_projection) > 2:
                    anomaly_candidate = True
            elif prev_pair or next_pair:
                distance = idx - prev_pair[0] if prev_pair else next_pair[0] - idx
                if distance >= 3:
                    boundary_candidate = True
        elif page.raw_candidate:
            anomaly_candidate = True

        if dominant_kind == "mixed" and kind in {"arabic", "roman"}:
            local_window_kind = _get_segment_kind(pages, idx)
            if local_window_kind == "mixed":
                boundary_candidate = True

        if page.raw_candidate and page.normalized_candidate is None:
            anomaly_candidate = True

        anomaly_score = 0.85 if anomaly_candidate else (0.35 if page.raw_candidate and page.normalized_candidate is None else 0.05)
        anchor_score = _clamp_score((0.30 * lexical_score) + (0.35 * local_sequence_score) + (0.25 * offset_score) - (0.30 * anomaly_score))
        if anchor_score >= 0.82 and not boundary_candidate:
            anchor_class = "A"
        elif anchor_score >= 0.62:
            anchor_class = "B"
        elif anchor_score >= 0.35:
            anchor_class = "C"
        else:
            anchor_class = "D"

        observations.append(
            PageObservation(
                pdf_page=page.pdf_page,
                raw_candidate=page.raw_candidate,
                normalized_candidate=page.normalized_candidate,
                candidate_kind=kind,
                numeric_value=numeric_value,
                lexical_score=_clamp_score(lexical_score),
                local_sequence_score=_clamp_score(local_sequence_score),
                offset_score=_clamp_score(offset_score),
                anomaly_score=_clamp_score(anomaly_score),
                anchor_score=anchor_score,
                anchor_class=anchor_class,
                is_boundary_candidate=boundary_candidate,
                is_anomaly_candidate=anomaly_candidate,
            )
        )
    return observations


def _segment_transition_kind(prev: PageObservation, current: PageObservation) -> str | None:
    if current.pdf_page <= prev.pdf_page:
        return "pdf_restart"
    if prev.candidate_kind in {"arabic", "roman"} and current.candidate_kind in {"arabic", "roman"} and prev.candidate_kind != current.candidate_kind:
        return "kind_transition"
    if prev.candidate_kind == current.candidate_kind and prev.candidate_kind in {"arabic", "roman"}:
        prev_num = prev.numeric_value
        current_num = current.numeric_value
        if prev_num is not None and current_num is not None:
            pdf_gap = current.pdf_page - prev.pdf_page
            value_gap = current_num - prev_num
            if pdf_gap > 0 and value_gap <= 0:
                return "restart_transition"
            if pdf_gap > 0 and abs(value_gap - pdf_gap) >= 20:
                return "restart_transition"
    return None


def _build_page_segments(observations: list[PageObservation]) -> list[PageSegment]:
    if not observations:
        return []

    segments: list[PageSegment] = []
    current: list[PageObservation] = [observations[0]]

    def flush() -> None:
        if not current:
            return
        kinds = Counter(obs.candidate_kind for obs in current if obs.candidate_kind in {"arabic", "roman"})
        dominant_kind = kinds.most_common(1)[0][0] if kinds else "unknown"
        anchor_classes = [obs.anchor_class for obs in current]
        stable_page_count = sum(1 for obs in current if not obs.is_boundary_candidate and not obs.is_anomaly_candidate and obs.candidate_kind == dominant_kind)
        boundary_page_count = sum(1 for obs in current if obs.is_boundary_candidate)
        anomaly_count = sum(1 for obs in current if obs.is_anomaly_candidate)
        transition_count = 0
        restart_like = False
        numeric_run_count = 0
        valid_numeric_count = 0
        offset_support = 0
        offset_spread = 0
        if dominant_kind == "arabic":
            offsets = [obs.pdf_page - obs.numeric_value for obs in current if obs.candidate_kind == "arabic" and obs.numeric_value is not None]
            if offsets:
                offset_counts = Counter(offsets)
                offset_support = offset_counts.most_common(1)[0][1]
                valid_numeric_count = len(offsets)
                offset_spread = max(offsets) - min(offsets)
        for prev_obs, next_obs in zip(current, current[1:]):
            transition = _segment_transition_kind(prev_obs, next_obs)
            if transition:
                transition_count += 1
            if transition == "restart_transition":
                restart_like = True
            if prev_obs.candidate_kind == dominant_kind and next_obs.candidate_kind == dominant_kind:
                if prev_obs.numeric_value is not None and next_obs.numeric_value is not None:
                    if next_obs.pdf_page > prev_obs.pdf_page and next_obs.numeric_value - prev_obs.numeric_value == next_obs.pdf_page - prev_obs.pdf_page:
                        numeric_run_count += 1
        offset_stable_run = (
            dominant_kind == "arabic"
            and len(current) >= 8
            and valid_numeric_count >= len(current) - max(6, len(current) // 10)
            and offset_support >= valid_numeric_count - max(4, len(current) // 12)
        )
        if anomaly_count and anomaly_count >= max(2, len(current) // 2):
            status = "anomaly"
        elif restart_like or (
            dominant_kind == "arabic"
            and valid_numeric_count >= 2
            and offset_spread >= 20
            and boundary_page_count
        ):
            status = "restart"
        elif boundary_page_count:
            status = "boundary"
        elif dominant_kind == "unknown":
            status = "unresolved"
        elif offset_stable_run:
            status = "stable"
        elif len(current) == 2 and numeric_run_count == 1:
            status = "stable"
        elif len(current) >= 3 and numeric_run_count >= max(1, len(current) - 3) and anomaly_count <= max(1, len(current) // 4):
            status = "stable"
        elif stable_page_count >= max(2, len(current) - 1) and transition_count == 0:
            status = "stable"
        else:
            status = "mixed"
        confidence = _clamp_score(sum(obs.anchor_score for obs in current) / len(current))
        segments.append(
            PageSegment(
                start_pdf_page=current[0].pdf_page,
                end_pdf_page=current[-1].pdf_page,
                dominant_kind=dominant_kind,
                status=status,
                page_count=len(current),
                stable_page_count=stable_page_count,
                boundary_page_count=boundary_page_count,
                anchor_classes=anchor_classes,
                confidence=confidence,
            )
        )

    for obs in observations[1:]:
        prev = current[-1]
        transition = _segment_transition_kind(prev, obs)
        hard_break = transition in {"pdf_restart", "kind_transition", "restart_transition"}
        if hard_break:
            flush()
            current = [obs]
            continue
        current.append(obs)

    flush()
    return segments


def _split_points_for_segment(segment: PageSegment, pages: list[ParsedPageBlock]) -> list[int]:
    split_points: list[int] = []
    prev_page: ParsedPageBlock | None = None
    prev_offset: float | None = None
    run_offsets: list[int] = []
    for page in pages:
        if prev_page is not None and page.pdf_page == prev_page.pdf_page:
            split_points.append(page.pdf_page)
        if page.candidate_kind != "arabic" or page.normalized_candidate is None or not page.normalized_candidate.isdigit():
            prev_page = page
            continue
        current_value = int(page.normalized_candidate)
        offset = page.pdf_page - current_value
        if prev_page is not None and prev_page.candidate_kind == "arabic" and prev_page.normalized_candidate and prev_page.normalized_candidate.isdigit():
            prev_value = int(prev_page.normalized_candidate)
            if prev_page.pdf_page < page.pdf_page:
                if current_value <= prev_value or abs((page.pdf_page - prev_page.pdf_page) - (current_value - prev_value)) >= 20:
                    split_points.append(page.pdf_page)
        if prev_offset is None:
            prev_offset = offset
            run_offsets = [offset]
            prev_page = page
            continue
        if abs(offset - prev_offset) > 10:
            split_points.append(page.pdf_page)
            prev_offset = offset
            run_offsets = [offset]
            prev_page = page
            continue
        run_offsets.append(offset)
        prev_offset = round(sum(run_offsets[-5:]) / min(len(run_offsets), 5))
        prev_page = page
    return sorted(set(point for point in split_points if segment.start_pdf_page < point <= segment.end_pdf_page))


def _segment_pages_for_bounds(pages: list[ParsedPageBlock], start_pdf_page: int, end_pdf_page: int) -> list[ParsedPageBlock]:
    seen_duplicate_anchor = False
    segment_pages: list[ParsedPageBlock] = []
    for page in pages:
        if page.pdf_page < start_pdf_page or page.pdf_page > end_pdf_page:
            continue
        if page.pdf_page == start_pdf_page:
            if seen_duplicate_anchor:
                continue
            seen_duplicate_anchor = True
        segment_pages.append(page)
    return segment_pages


def _merge_adjacent_restart_segments(segments: list[PageSegment]) -> list[PageSegment]:
    if not segments:
        return []

    merged: list[PageSegment] = []
    cursor = 0
    while cursor < len(segments):
        current = segments[cursor]
        if (
            current.status == "stable"
            and current.dominant_kind == "arabic"
            and current.page_count <= 3
            and cursor > 0
            and cursor + 1 < len(segments)
        ):
            prev_segment = merged[-1] if merged else None
            next_segment = segments[cursor + 1]
            if (
                prev_segment is not None
                and prev_segment.status in {"mixed", "boundary", "restart"}
                and next_segment.status in {"mixed", "boundary", "restart"}
                and prev_segment.end_pdf_page + 1 >= current.start_pdf_page
                and current.end_pdf_page + 1 >= next_segment.start_pdf_page
            ):
                merged[-1] = PageSegment(
                    start_pdf_page=prev_segment.start_pdf_page,
                    end_pdf_page=next_segment.end_pdf_page,
                    dominant_kind="arabic",
                    status="restart",
                    page_count=(next_segment.end_pdf_page - prev_segment.start_pdf_page + 1),
                    stable_page_count=prev_segment.stable_page_count + current.stable_page_count + next_segment.stable_page_count,
                    boundary_page_count=prev_segment.boundary_page_count + current.boundary_page_count + next_segment.boundary_page_count,
                    anchor_classes=prev_segment.anchor_classes + current.anchor_classes + next_segment.anchor_classes,
                    confidence=_clamp_score((prev_segment.confidence + current.confidence + next_segment.confidence) / 3),
                )
                cursor += 2
                continue
        merged.append(current)
        cursor += 1
    return merged


def _dedupe_overlapping_segments(segments: list[PageSegment]) -> list[PageSegment]:
    deduped: list[PageSegment] = []
    for segment in segments:
        if not deduped:
            deduped.append(segment)
            continue
        prev = deduped[-1]
        if segment.start_pdf_page < prev.start_pdf_page:
            continue
        if segment.start_pdf_page == prev.start_pdf_page:
            prev_span = prev.end_pdf_page - prev.start_pdf_page
            current_span = segment.end_pdf_page - segment.start_pdf_page
            prev_rank = 1 if prev.status == "stable" else 0
            current_rank = 1 if segment.status == "stable" else 0
            if current_rank > prev_rank or (current_rank == prev_rank and current_span > prev_span):
                deduped[-1] = segment
                continue
            if segment.end_pdf_page > prev.end_pdf_page:
                trimmed_start = prev.end_pdf_page + 1
                if trimmed_start <= segment.end_pdf_page:
                    deduped.append(replace(segment, start_pdf_page=trimmed_start, page_count=segment.end_pdf_page - trimmed_start + 1))
            continue
        if segment.start_pdf_page <= prev.end_pdf_page and segment.end_pdf_page > prev.end_pdf_page:
            if segment.status == "stable" and prev.status != "stable":
                trimmed_start = prev.end_pdf_page + 1
                if trimmed_start <= segment.end_pdf_page:
                    deduped.append(replace(segment, start_pdf_page=trimmed_start, page_count=segment.end_pdf_page - trimmed_start + 1))
                continue
        deduped.append(segment)
    return deduped


def _uncovered_ranges(base_segment: PageSegment, segments: list[PageSegment]) -> list[tuple[int, int]]:
    overlaps = sorted(
        (max(base_segment.start_pdf_page, segment.start_pdf_page), min(base_segment.end_pdf_page, segment.end_pdf_page))
        for segment in segments
        if segment.end_pdf_page >= base_segment.start_pdf_page and segment.start_pdf_page <= base_segment.end_pdf_page
    )
    uncovered: list[tuple[int, int]] = []
    cursor = base_segment.start_pdf_page
    for overlap_start, overlap_end in overlaps:
        if overlap_end < cursor:
            continue
        if overlap_start > cursor:
            uncovered.append((cursor, overlap_start - 1))
        cursor = max(cursor, overlap_end + 1)
    if cursor <= base_segment.end_pdf_page:
        uncovered.append((cursor, base_segment.end_pdf_page))
    return uncovered


def _restore_restart_segments(raw_segments: list[PageSegment], refined_segments: list[PageSegment]) -> list[PageSegment]:
    restored = list(refined_segments)
    for segment in raw_segments:
        if segment.status != "restart":
            continue
        for start_pdf_page, end_pdf_page in _uncovered_ranges(segment, restored):
            restored.append(
                replace(
                    segment,
                    start_pdf_page=start_pdf_page,
                    end_pdf_page=end_pdf_page,
                    page_count=end_pdf_page - start_pdf_page + 1,
                )
            )
    return sorted(restored, key=lambda item: (item.start_pdf_page, item.end_pdf_page, item.status != "restart"))


def _refine_long_mixed_segments(segments: list[PageSegment], pages: list[ParsedPageBlock]) -> list[PageSegment]:
    refined: list[PageSegment] = []
    page_slice = [page for page in pages]
    for segment in segments:
        if segment.status == "stable" and segment.page_count >= 80:
            refined.append(segment)
            continue
        if segment.status not in {"mixed", "boundary", "stable"} or segment.page_count < 20:
            refined.append(segment)
            continue
        segment_pages = _segment_pages_for_bounds(page_slice, segment.start_pdf_page, segment.end_pdf_page)
        split_points = _split_points_for_segment(segment, segment_pages)
        if not split_points:
            refined.append(segment)
            continue
        bounds = [segment.start_pdf_page] + split_points + [segment.end_pdf_page + 1]
        for start, end_exclusive in zip(bounds, bounds[1:]):
            sub_start = start
            sub_end = end_exclusive - 1
            if sub_end < sub_start:
                continue
            sub_pages = _segment_pages_for_bounds(segment_pages, sub_start, sub_end)
            if not sub_pages:
                continue
            sub_observations = _build_page_observations(sub_pages)
            refined.extend(_build_page_segments(sub_observations))
    refined = _dedupe_overlapping_segments(_merge_adjacent_restart_segments(refined))
    refined = _restore_restart_segments(segments, refined)
    return _dedupe_overlapping_segments(refined)


def _build_query_zones(segments: list[PageSegment]) -> list[QueryZone]:
    zones: list[QueryZone] = []
    for idx, segment in enumerate(segments):
        if segment.status == "boundary":
            reason = "kind_transition" if idx and idx < len(segments) else "boundary_window"
            zones.append(
                QueryZone(
                    zone_type="main_body_boundary" if segment.dominant_kind in {"arabic", "roman"} else "unresolved_mixed",
                    start_pdf_page=segment.start_pdf_page,
                    end_pdf_page=segment.end_pdf_page,
                    reason=reason,
                    dominant_kind=segment.dominant_kind,
                    confidence=segment.confidence,
                )
            )
        elif segment.status == "restart":
            zones.append(
                QueryZone(
                    zone_type="restart_zone",
                    start_pdf_page=segment.start_pdf_page,
                    end_pdf_page=segment.end_pdf_page,
                    reason="numbering_restart_or_large_offset_shift",
                    dominant_kind=segment.dominant_kind,
                    confidence=segment.confidence,
                )
            )
        elif segment.status == "anomaly":
            zones.append(
                QueryZone(
                    zone_type="anomaly_cluster",
                    start_pdf_page=segment.start_pdf_page,
                    end_pdf_page=segment.end_pdf_page,
                    reason="anomaly_density",
                    dominant_kind=segment.dominant_kind,
                    confidence=segment.confidence,
                )
            )
        elif segment.status in {"mixed", "unresolved"}:
            zones.append(
                QueryZone(
                    zone_type="unresolved_mixed",
                    start_pdf_page=segment.start_pdf_page,
                    end_pdf_page=segment.end_pdf_page,
                    reason="insufficient_anchor_support",
                    dominant_kind=segment.dominant_kind,
                    confidence=segment.confidence,
                )
            )
    return zones


def build_segment_diagnostics(markdown: str) -> dict[str, Any]:
    pages = parse_markdown_pages(markdown)
    observations = _build_page_observations(pages)
    segments = _build_page_segments(observations)
    segments = _refine_long_mixed_segments(segments, pages)
    query_zones = _build_query_zones(segments)
    return {
        "page_count": len(pages),
        "kind_histogram": _kind_histogram(pages),
        "observations": [
            {
                "pdf_page": obs.pdf_page,
                "raw_candidate": obs.raw_candidate,
                "normalized_candidate": obs.normalized_candidate,
                "candidate_kind": obs.candidate_kind,
                "numeric_value": obs.numeric_value,
                "lexical_score": obs.lexical_score,
                "local_sequence_score": obs.local_sequence_score,
                "offset_score": obs.offset_score,
                "anomaly_score": obs.anomaly_score,
                "anchor_score": obs.anchor_score,
                "anchor_class": obs.anchor_class,
                "is_boundary_candidate": obs.is_boundary_candidate,
                "is_anomaly_candidate": obs.is_anomaly_candidate,
            }
            for obs in observations
        ],
        "segments": [
            {
                "start_pdf_page": segment.start_pdf_page,
                "end_pdf_page": segment.end_pdf_page,
                "dominant_kind": segment.dominant_kind,
                "status": segment.status,
                "page_count": segment.page_count,
                "stable_page_count": segment.stable_page_count,
                "boundary_page_count": segment.boundary_page_count,
                "anchor_classes": segment.anchor_classes,
                "confidence": segment.confidence,
            }
            for segment in segments
        ],
        "query_zones": [
            {
                "zone_type": zone.zone_type,
                "start_pdf_page": zone.start_pdf_page,
                "end_pdf_page": zone.end_pdf_page,
                "reason": zone.reason,
                "dominant_kind": zone.dominant_kind,
                "confidence": zone.confidence,
            }
            for zone in query_zones
        ],
    }


def _projected_numeric_targets(pages: list[ParsedPageBlock], idx: int, kind: str) -> list[int]:
    prev_pair, next_pair = _nearest_values_by_kind(pages, idx, kind)
    projected: list[int] = []
    if kind == "arabic":
        if prev_pair:
            projected.append(int(prev_pair[1]) + (idx - prev_pair[0]))
        if next_pair:
            projected.append(int(next_pair[1]) - (next_pair[0] - idx))
        return projected
    if kind == "roman":
        if prev_pair:
            prev_num = _roman_to_int(prev_pair[1])
            if prev_num is not None:
                projected.append(prev_num + (idx - prev_pair[0]))
        if next_pair:
            next_num = _roman_to_int(next_pair[1])
            if next_num is not None:
                projected.append(next_num - (next_pair[0] - idx))
    return projected


def _projection_mismatch(pages: list[ParsedPageBlock], idx: int, page: ParsedPageBlock) -> int | None:
    if page.candidate_kind not in {"arabic", "roman"} or page.normalized_candidate is None:
        return None
    current_numeric = _numeric_value_for_kind(page.normalized_candidate, page.candidate_kind)
    if current_numeric is None:
        return None
    projected = _projected_numeric_targets(pages, idx, page.candidate_kind)
    if not projected:
        return None
    return min(abs(current_numeric - target) for target in projected)


def build_segment_review_proposals(markdown: str) -> dict[str, Any]:
    pages = parse_markdown_pages(markdown)
    observations = _build_page_observations(pages)
    segments = _build_page_segments(observations)
    segments = _refine_long_mixed_segments(segments, pages)
    query_zones = _build_query_zones(segments)
    proposals: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str | None]] = set()
    page_segment_status: dict[int, str] = {}
    page_segment_bounds: dict[int, tuple[int, int]] = {}
    protected_pages: set[int] = set()
    near_protected_pages: set[int] = set()
    for segment_index, segment in enumerate(segments):
        left_status = segments[segment_index - 1].status if segment_index > 0 else None
        right_status = segments[segment_index + 1].status if segment_index + 1 < len(segments) else None
        protect_edges = segment.status == "stable" and (left_status != "stable" or right_status != "stable")
        for pdf_page in range(segment.start_pdf_page, segment.end_pdf_page + 1):
            page_segment_status[pdf_page] = segment.status
            page_segment_bounds[pdf_page] = (segment.start_pdf_page, segment.end_pdf_page)
        if protect_edges and segment.page_count >= 6:
            margin = min(3, max(1, segment.page_count // 8))
            left_guard_end = min(segment.end_pdf_page, segment.start_pdf_page + margin - 1)
            right_guard_start = max(segment.start_pdf_page, segment.end_pdf_page - margin + 1)
            protected_pages.update(range(segment.start_pdf_page, left_guard_end + 1))
            protected_pages.update(range(right_guard_start, segment.end_pdf_page + 1))
            near_span = min(3, max(1, margin + 1))
            near_protected_pages.update(range(left_guard_end + 1, min(segment.end_pdf_page, left_guard_end + near_span) + 1))
            near_protected_pages.update(range(max(segment.start_pdf_page, right_guard_start - near_span), right_guard_start))

    for idx, (page, observation) in enumerate(zip(pages, observations)):
        segment_kind = _get_segment_kind(pages, idx)
        key_base = page.pdf_page
        segment_status = page_segment_status.get(page.pdf_page, "unresolved")
        if segment_kind not in {"arabic", "roman"} or observation.is_boundary_candidate or segment_status != "stable":
            abstentions.append(
                {
                    "pdf_page": page.pdf_page,
                    "current_value": page.normalized_candidate,
                    "reason": "outside_stable_segment" if segment_status != "stable" else "boundary_or_mixed_window",
                    "segment_kind": segment_kind,
                    "segment_status": segment_status,
                }
            )
            continue

        if page.pdf_page in protected_pages:
            abstentions.append(
                {
                    "pdf_page": page.pdf_page,
                    "current_value": page.normalized_candidate,
                    "reason": "segment_edge_guard_band",
                    "segment_kind": segment_kind,
                    "segment_status": segment_status,
                    "segment_bounds": page_segment_bounds.get(page.pdf_page),
                }
            )
            continue

        if segment_kind == "arabic":
            target, reason_tag, confidence = _infer_arabic_target(pages, idx)
        else:
            target, reason_tag, confidence = _infer_roman_target(pages, idx)

        if target is not None:
            action = "fill_null" if page.normalized_candidate is None else "replace"
            if action == "fill_null" and page.pdf_page in near_protected_pages:
                abstentions.append(
                    {
                        "pdf_page": page.pdf_page,
                        "current_value": page.normalized_candidate,
                        "reason": "near_guard_band_null_fill",
                        "segment_kind": segment_kind,
                        "segment_status": segment_status,
                        "segment_bounds": page_segment_bounds.get(page.pdf_page),
                    }
                )
                continue
            if segment_kind == "roman" and action == "replace":
                abstentions.append(
                    {
                        "pdf_page": page.pdf_page,
                        "current_value": page.normalized_candidate,
                        "reason": "roman_replace_abstain",
                        "segment_kind": segment_kind,
                        "segment_status": segment_status,
                        "segment_bounds": page_segment_bounds.get(page.pdf_page),
                    }
                )
                continue
            if page.normalized_candidate == target:
                continue
            key = (key_base, action, target)
            if key not in seen:
                seen.add(key)
                proposals.append(
                    {
                        "pdf_page": page.pdf_page,
                        "action": action,
                        "current_value": page.normalized_candidate,
                        "proposed_value": target,
                        "reason_tag": reason_tag or "sequence_inference",
                        "confidence": confidence or 0.9,
                        "segment_kind": segment_kind,
                        "segment_status": segment_status,
                    }
                )
            continue

        if page.raw_candidate is not None and page.normalized_candidate is None:
            key = (key_base, "delete_to_null", None)
            if key not in seen:
                seen.add(key)
                proposals.append(
                    {
                        "pdf_page": page.pdf_page,
                        "action": "delete_to_null",
                        "current_value": page.raw_candidate,
                        "proposed_value": None,
                        "reason_tag": "invalid_current_value",
                        "confidence": 0.8,
                        "segment_kind": segment_kind,
                        "segment_status": segment_status,
                    }
                )
            continue

        mismatch = _projection_mismatch(pages, idx, page)
        if observation.is_anomaly_candidate and mismatch is not None and mismatch >= 4:
            key = (key_base, "delete_to_null", None)
            if key not in seen:
                seen.add(key)
                proposals.append(
                    {
                        "pdf_page": page.pdf_page,
                        "action": "delete_to_null",
                        "current_value": page.normalized_candidate,
                        "proposed_value": None,
                        "reason_tag": "projection_conflict_outlier",
                        "confidence": 0.78,
                        "segment_kind": segment_kind,
                        "segment_status": segment_status,
                    }
                )

    return {
        "status": "review_only_proposals",
        "page_count": len(pages),
        "proposal_count": len(proposals),
        "abstain_count": len(abstentions),
        "proposals": proposals,
        "abstentions": abstentions,
        "segments": [
            {
                "start_pdf_page": segment.start_pdf_page,
                "end_pdf_page": segment.end_pdf_page,
                "dominant_kind": segment.dominant_kind,
                "status": segment.status,
                "confidence": segment.confidence,
            }
            for segment in segments
        ],
        "query_zones": [
            {
                "zone_type": zone.zone_type,
                "start_pdf_page": zone.start_pdf_page,
                "end_pdf_page": zone.end_pdf_page,
                "reason": zone.reason,
                "dominant_kind": zone.dominant_kind,
                "confidence": zone.confidence,
            }
            for zone in query_zones
        ],
    }


def _nearest_values_by_kind(pages: list[ParsedPageBlock], idx: int, kind: str) -> tuple[tuple[int, str] | None, tuple[int, str] | None]:
    prev_pair = None
    next_pair = None

    for left in range(idx - 1, -1, -1):
        value = pages[left].normalized_candidate
        if value and detect_candidate_kind(value) == kind:
            prev_pair = (left, value)
            break

    for right in range(idx + 1, len(pages)):
        value = pages[right].normalized_candidate
        if value and detect_candidate_kind(value) == kind:
            next_pair = (right, value)
            break

    return prev_pair, next_pair


def _infer_arabic_target(pages: list[ParsedPageBlock], idx: int) -> tuple[str | None, str | None, float | None]:
    prev_pair, next_pair = _nearest_values_by_kind(pages, idx, "arabic")
    if prev_pair and next_pair:
        prev_idx, prev_value = prev_pair
        next_idx, next_value = next_pair
        prev_num = int(prev_value)
        next_num = int(next_value)
        gap = next_idx - prev_idx
        value_gap = next_num - prev_num
        if gap > 0 and gap == value_gap:
            return str(prev_num + (idx - prev_idx)), "two_sided_evidence", 0.96
    return None, None, None


def _roman_to_int(value: str) -> int | None:
    if not value or not ROMAN_RE.match(value):
        return None
    roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for char in reversed(value.upper()):
        current = roman_map[char]
        if current < prev:
            total -= current
        else:
            total += current
            prev = current
    return total


def _int_to_roman(number: int) -> str | None:
    if number <= 0 or number > 3999:
        return None
    mapping = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out = []
    remaining = number
    for value, symbol in mapping:
        while remaining >= value:
            out.append(symbol)
            remaining -= value
    return "".join(out)


def _infer_roman_target(pages: list[ParsedPageBlock], idx: int) -> tuple[str | None, str | None, float | None]:
    prev_pair, next_pair = _nearest_values_by_kind(pages, idx, "roman")
    if prev_pair and next_pair:
        prev_idx, prev_value = prev_pair
        next_idx, next_value = next_pair
        prev_num = _roman_to_int(prev_value)
        next_num = _roman_to_int(next_value)
        if prev_num is None or next_num is None:
            return None, None, None
        gap = next_idx - prev_idx
        value_gap = next_num - prev_num
        if gap > 0 and gap == value_gap:
            inferred = _int_to_roman(prev_num + (idx - prev_idx))
            if inferred:
                return inferred, "roman_sequence", 0.94
    return None, None, None


def _infer_one_sided_candidates(pages: list[ParsedPageBlock], idx: int, kind: str, max_distance: int = 3) -> list[PrintedPageCandidate]:
    prev_pair, next_pair = _nearest_values_by_kind(pages, idx, kind)
    candidates: list[PrintedPageCandidate] = []

    if prev_pair and idx - prev_pair[0] > max_distance:
        prev_pair = None
    if next_pair and next_pair[0] - idx > max_distance:
        next_pair = None

    if prev_pair and next_pair:
        prev_idx, prev_value = prev_pair
        next_idx, next_value = next_pair
        if kind == "arabic":
            left_value = int(prev_value) + (idx - prev_idx)
            right_value = int(next_value) - (next_idx - idx)
            if abs(left_value - right_value) > 2:
                return []
        else:
            prev_num = _roman_to_int(prev_value)
            next_num = _roman_to_int(next_value)
            if prev_num is None or next_num is None:
                return []
            left_value = prev_num + (idx - prev_idx)
            right_value = next_num - (next_idx - idx)
            if abs(left_value - right_value) > 2:
                return []

    if kind == "arabic":
        if prev_pair:
            prev_idx, prev_value = prev_pair
            candidates.append(
                PrintedPageCandidate(
                    value=str(int(prev_value) + (idx - prev_idx)),
                    action="replace",
                    reason_tag="left_anchor_projection",
                    confidence=0.72,
                )
            )
        if next_pair:
            next_idx, next_value = next_pair
            candidates.append(
                PrintedPageCandidate(
                    value=str(int(next_value) - (next_idx - idx)),
                    action="replace",
                    reason_tag="right_anchor_projection",
                    confidence=0.72,
                )
            )
        return candidates

    if kind == "roman":
        if prev_pair:
            prev_idx, prev_value = prev_pair
            prev_num = _roman_to_int(prev_value)
            if prev_num is not None:
                inferred = _int_to_roman(prev_num + (idx - prev_idx))
                if inferred:
                    candidates.append(
                        PrintedPageCandidate(
                            value=inferred,
                            action="replace",
                            reason_tag="left_anchor_projection",
                            confidence=0.7,
                        )
                    )
        if next_pair:
            next_idx, next_value = next_pair
            next_num = _roman_to_int(next_value)
            if next_num is not None:
                inferred = _int_to_roman(next_num - (next_idx - idx))
                if inferred:
                    candidates.append(
                        PrintedPageCandidate(
                            value=inferred,
                            action="replace",
                            reason_tag="right_anchor_projection",
                            confidence=0.7,
                        )
                    )
    return candidates


def build_review_spans(markdown: str, max_span_length: int = 8) -> list[PrintedPageReviewSpan]:
    pages = parse_markdown_pages(markdown)
    review_pages: list[PrintedPageReviewPage] = []

    for idx, page in enumerate(pages):
        segment_kind = _get_segment_kind(pages, idx)
        if segment_kind not in {"arabic", "roman"}:
            continue

        candidates: list[PrintedPageCandidate] = []
        seen: set[tuple[str | None, str]] = set()

        def add_candidate(value: str | None, action: str, reason_tag: str, confidence: float):
            normalized_value = normalize_candidate(value) if value is not None else None
            key = (normalized_value, action)
            if key in seen:
                return
            seen.add(key)
            candidates.append(
                PrintedPageCandidate(
                    value=normalized_value,
                    action=action,
                    reason_tag=reason_tag,
                    confidence=confidence,
                )
            )

        if page.normalized_candidate is not None:
            add_candidate(page.normalized_candidate, "keep", "current_value", 0.9)
        elif page.raw_candidate is not None:
            add_candidate(None, "leave_null", "invalid_current_value", 0.75)

        if page.raw_candidate is not None and page.normalized_candidate is None:
            add_candidate(None, "delete_to_null", "conservative_null", 0.7)
        elif page.raw_candidate is None and page.normalized_candidate is None:
            add_candidate(None, "leave_null", "conservative_null", 0.7)

        if segment_kind == "arabic":
            target, reason_tag, confidence = _infer_arabic_target(pages, idx)
        else:
            target, reason_tag, confidence = _infer_roman_target(pages, idx)

        if target is not None:
            add_candidate(target, "fill_null" if page.normalized_candidate is None else "replace", reason_tag or "sequence_inference", confidence or 0.9)
        else:
            for extra in _infer_one_sided_candidates(pages, idx, segment_kind):
                action = "fill_null" if page.normalized_candidate is None and extra.value is not None else extra.action
                add_candidate(extra.value, action, extra.reason_tag, extra.confidence)

        if len(candidates) <= 1:
            continue

        review_pages.append(
            PrintedPageReviewPage(
                pdf_page=page.pdf_page,
                current_value=page.normalized_candidate,
                current_kind=page.candidate_kind,
                segment_kind=segment_kind,
                candidates=candidates,
            )
        )

    if not review_pages:
        return []

    spans: list[PrintedPageReviewSpan] = []
    current_pages: list[PrintedPageReviewPage] = []
    current_segment = review_pages[0].segment_kind

    def flush_span():
        if not current_pages:
            return
        first_pdf = current_pages[0].pdf_page
        last_pdf = current_pages[-1].pdf_page
        left_anchor = None
        right_anchor = None
        for page in pages:
            if page.pdf_page < first_pdf and page.candidate_kind == current_segment and page.normalized_candidate is not None:
                left_anchor = page.normalized_candidate
            if page.pdf_page > last_pdf and page.candidate_kind == current_segment and page.normalized_candidate is not None:
                right_anchor = page.normalized_candidate
                break
        spans.append(
            PrintedPageReviewSpan(
                start_pdf_page=first_pdf,
                end_pdf_page=last_pdf,
                pages=list(current_pages),
                left_anchor_value=left_anchor,
                right_anchor_value=right_anchor,
                segment_kind=current_segment,
            )
        )

    for review_page in review_pages:
        contiguous = current_pages and review_page.pdf_page == current_pages[-1].pdf_page + 1
        same_segment = review_page.segment_kind == current_segment
        short_enough = len(current_pages) < max_span_length
        if current_pages and not (contiguous and same_segment and short_enough):
            flush_span()
            current_pages = []
            current_segment = review_page.segment_kind
        if not current_pages:
            current_segment = review_page.segment_kind
        current_pages.append(review_page)

    flush_span()
    return spans


def infer_sequence_repairs(markdown: str) -> tuple[str, list[PrintedPageAction], list[str]]:
    pages = parse_markdown_pages(markdown)
    actions: list[PrintedPageAction] = []
    warnings: list[str] = []
    rewritten = markdown

    if not pages:
        return markdown, actions, ["No page anchors found; markdown postprocess skipped."]

    proposal_payload = build_segment_review_proposals(markdown)
    proposals = proposal_payload.get("proposals", []) if isinstance(proposal_payload, dict) else []
    if not proposals:
        warnings.append("No conservative printed-page repairs were applied.")
        return rewritten, actions, warnings

    page_lookup = {page.pdf_page: page for page in pages}
    seen: set[tuple[int, str, str | None]] = set()

    for proposal in proposals:
        pdf_page = proposal.get("pdf_page")
        action = proposal.get("action")
        proposed_value = proposal.get("proposed_value")
        if not isinstance(pdf_page, int) or action not in {"replace", "fill_null", "delete_to_null"}:
            continue
        page = page_lookup.get(pdf_page)
        if page is None:
            continue

        key = (pdf_page, action, proposed_value)
        if key in seen:
            continue
        seen.add(key)

        if action == "replace" and page.normalized_candidate == proposed_value:
            continue
        if action == "fill_null" and page.normalized_candidate is not None:
            continue
        if action == "delete_to_null" and page.normalized_candidate is None and page.raw_candidate is None:
            continue

        new_block = _replace_block_comment(page.raw_block, proposed_value)
        rewritten = rewritten.replace(page.raw_block, new_block, 1)
        actions.append(
            PrintedPageAction(
                pdf_page=pdf_page,
                action=action,
                raw_candidate=page.normalized_candidate if page.normalized_candidate is not None else page.raw_candidate,
                final_printed_page=proposed_value,
                confidence=proposal.get("confidence"),
                reason_tag=proposal.get("reason_tag") or "segment_review_proposal",
                source="rule",
            )
        )
        page_lookup[pdf_page] = replace(
            page,
            raw_block=new_block,
            raw_candidate=proposed_value,
            normalized_candidate=normalize_candidate(proposed_value),
            candidate_kind=detect_candidate_kind(normalize_candidate(proposed_value)),
        )

    if not actions:
        warnings.append("No conservative printed-page repairs were applied.")

    return rewritten, actions, warnings
