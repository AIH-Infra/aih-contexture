"""
页码处理器

从文档页面中提取和规范化页码信息，同时保留页眉/页脚文本元数据。
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Annotated, List, Optional, Tuple

from aih_contexture.logger import get_logger
from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document

logger = get_logger()


CHINESE_NUMBERS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "壹": 1,
    "二": 2,
    "贰": 2,
    "兩": 2,
    "两": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "陸": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
    "十": 10,
    "拾": 10,
    "百": 100,
    "佰": 100,
    "千": 1000,
    "仟": 1000,
}

ROMAN_NUMERALS = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

CHINESE_DIGIT_CHARS = "零〇一二三四五六七八九十百千壹贰叁肆伍陆陸柒捌玖拾佰仟兩两"
YEAR_MARKERS = ("年", "年月", "世纪", "世紀", "月", "日", "号", "號", "卷", "期")
ENGLISH_MONTH_PATTERN = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)


@dataclass
class RegionBlockCandidate:
    block: object
    zone: str
    source: str
    alignment: str
    margin_distance: float
    text: str
    display_text: Optional[str] = None


@dataclass
class PageNumberCandidate:
    page_number: str
    numeric: Optional[int]
    format: str
    zone: str
    source: str
    alignment: str
    text: str
    match_text: str
    match_start: int
    match_end: int
    margin_distance: float
    block_type: Optional[BlockTypes]
    base_score: float = 0.0
    final_score: float = 0.0


class PageNumberProcessor(BaseProcessor):
    """
    页码处理器。

    说明：
    1. 始终写入机器页码与页眉/页脚元数据；
    2. 仅在启用印刷页码提取时选择 printed page number；
    3. 页码选择基于多候选打分，而不是“命中即返回”。
    """

    block_types: Tuple[BlockTypes] = (
        BlockTypes.PageHeader,
        BlockTypes.PageFooter,
    )

    page_numbering_enabled: Annotated[bool, "是否启用页码提取"] = True
    page_number_format: Annotated[str, "页码格式: arabic, roman, chinese, custom"] = "arabic"
    use_printed_page_number: Annotated[bool, "使用印刷页码而非机器页码"] = True
    page_number_custom_pattern: Annotated[Optional[str], "自定义页码正则表达式"] = None
    page_number_prefix: Annotated[str, "页码前缀"] = ""
    page_number_suffix: Annotated[str, "页码后缀"] = ""
    printed_page_zones: Annotated[
        List[str],
        "页码搜索区域: header, footer, top-right, bottom-right, top-left, bottom-left",
    ] = None
    printed_page_header_y_frac: Annotated[float, "页眉区域阈值（页面顶部百分比）"] = 0.15
    printed_page_footer_y_frac: Annotated[float, "页脚区域阈值（页面底部百分比）"] = 0.83

    min_candidate_score: float = 1.5
    min_anchor_score: float = 2.2
    ambiguity_gap: float = 0.2

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)

        if self.printed_page_zones is None:
            self.printed_page_zones = ["footer", "header"]

        if isinstance(config, dict):
            if config.get("page_numbering_enabled") is not None:
                self.page_numbering_enabled = bool(config["page_numbering_enabled"])
            if config.get("page_number_format") is not None:
                self.page_number_format = str(config["page_number_format"])
            if config.get("use_printed_page_number") is not None:
                self.use_printed_page_number = bool(config["use_printed_page_number"])
            if config.get("page_number_custom_pattern") is not None:
                self.page_number_custom_pattern = str(config["page_number_custom_pattern"])
            if config.get("page_number_prefix") is not None:
                self.page_number_prefix = str(config["page_number_prefix"])
            if config.get("page_number_suffix") is not None:
                self.page_number_suffix = str(config["page_number_suffix"])
            if config.get("printed_page_zones") is not None:
                self.printed_page_zones = list(config["printed_page_zones"])
            if config.get("printed_page_header_y_frac") is not None:
                self.printed_page_header_y_frac = float(config["printed_page_header_y_frac"])
            if config.get("printed_page_footer_y_frac") is not None:
                self.printed_page_footer_y_frac = float(config["printed_page_footer_y_frac"])

    def __call__(self, document: Document):
        logger.info(
            "[PageNumberProcessor] start: page_numbering_enabled=%s, use_printed_page_number=%s",
            self.page_numbering_enabled,
            self.use_printed_page_number,
        )

        page_candidates: List[List[PageNumberCandidate]] = []
        page_region_texts: List[Tuple[Optional[str], Optional[str]]] = []

        for page_idx, page in enumerate(document.pages):
            region_blocks = self._collect_region_blocks(page, document)
            typed_header_blocks = [
                candidate for candidate in region_blocks["header"] if candidate.source == "typed"
            ]
            typed_footer_blocks = [
                candidate for candidate in region_blocks["footer"] if candidate.source == "typed"
            ]
            # Header/footer comments should reflect explicit layout regions only.
            # Heuristic region scraping remains available for printed-page fallback.
            header_text = self._compose_region_text(typed_header_blocks)
            footer_text = self._compose_region_text(typed_footer_blocks)
            page_region_texts.append((header_text, footer_text))

            if self.page_numbering_enabled and self.use_printed_page_number:
                candidates = self._extract_page_candidates(region_blocks)
            else:
                candidates = []

            page_candidates.append(candidates)
            logger.info(
                "[PageNumberProcessor] page=%s header=%s footer=%s candidates=%s",
                page_idx,
                bool(header_text),
                bool(footer_text),
                len(candidates),
            )

        selected_candidates = (
            self._select_candidates(page_candidates)
            if self.page_numbering_enabled and self.use_printed_page_number
            else [None] * len(document.pages)
        )

        extracted_count = 0
        for page_idx, page in enumerate(document.pages):
            machine_page_number = page_idx + 1
            header_text, footer_text = page_region_texts[page_idx]
            selected = selected_candidates[page_idx]
            printed_page_number = selected.page_number if selected else None

            if printed_page_number:
                extracted_count += 1

            self._set_page_metadata(
                page=page,
                machine_page_number=machine_page_number,
                printed_page_number=printed_page_number,
                header_text=header_text,
                footer_text=footer_text,
            )

        logger.info(
            "[PageNumberProcessor] completed: %s/%s pages with printed page number",
            extracted_count,
            len(document.pages),
        )

    def _collect_region_blocks(self, page, document: Document) -> dict[str, List[RegionBlockCandidate]]:
        page_bbox = page.polygon.bbox
        page_top = page_bbox[1]
        page_bottom = page_bbox[3]
        page_height = max(page_bottom - page_top, 1)
        page_width = max(page_bbox[2] - page_bbox[0], 1)

        header_threshold = page_top + page_height * self.printed_page_header_y_frac
        footer_threshold = page_top + page_height * self.printed_page_footer_y_frac

        typed_candidates = {"header": [], "footer": []}
        heuristic_candidates = {"header": [], "footer": []}

        for block_id in page.structure or []:
            block = document.get_block(block_id)
            if not block or not hasattr(block, "polygon"):
                continue

            block_bbox = block.polygon.bbox
            y_center = (block_bbox[1] + block_bbox[3]) / 2

            if block.block_type == BlockTypes.PageHeader:
                text = self._clean_text(self._get_block_text(block, document))
                if not text:
                    continue
                typed_candidates["header"].append(
                    self._build_region_block_candidate(
                        block, text, "header", "typed", page_bbox, header_threshold, footer_threshold, page_width, page_top, page_bottom
                    )
                )
            elif block.block_type == BlockTypes.PageFooter:
                text = self._clean_text(self._get_block_text(block, document))
                if not text:
                    continue
                typed_candidates["footer"].append(
                    self._build_region_block_candidate(
                        block, text, "footer", "typed", page_bbox, header_threshold, footer_threshold, page_width, page_top, page_bottom
                    )
                )
            else:
                header_display_text = self._clean_text(
                    self._extract_zone_text(
                        block,
                        document,
                        zone="header",
                        zone_start=page_top,
                        zone_end=header_threshold,
                    )
                )
                footer_display_text = self._clean_text(
                    self._extract_zone_text(
                        block,
                        document,
                        zone="footer",
                        zone_start=footer_threshold,
                        zone_end=page_bottom,
                    )
                )
                full_text = self._clean_text(self._get_block_text(block, document))
                intersects_header = self._bbox_intersects_vertical_zone(block_bbox, page_top, header_threshold)
                intersects_footer = self._bbox_intersects_vertical_zone(block_bbox, footer_threshold, page_bottom)

                # 兜底：若行级抽取失败，回退到旧的块级区域启发式，避免页眉/页码整体消失
                if not header_display_text and y_center <= header_threshold:
                    header_display_text = full_text
                if not footer_display_text and y_center >= footer_threshold:
                    footer_display_text = full_text

                header_candidate_text = header_display_text or full_text
                footer_candidate_text = footer_display_text or full_text

                if header_candidate_text and (header_display_text or intersects_header or y_center <= header_threshold):
                    candidate = self._build_region_block_candidate(
                        block, header_candidate_text, "header", "heuristic", page_bbox, header_threshold, footer_threshold, page_width, page_top, page_bottom
                    )
                    candidate.display_text = header_display_text or header_candidate_text
                    heuristic_candidates["header"].append(candidate)
                if footer_candidate_text and (footer_display_text or intersects_footer or y_center >= footer_threshold):
                    candidate = self._build_region_block_candidate(
                        block, footer_candidate_text, "footer", "heuristic", page_bbox, header_threshold, footer_threshold, page_width, page_top, page_bottom
                    )
                    candidate.display_text = footer_display_text or footer_candidate_text
                    heuristic_candidates["footer"].append(candidate)

        region_blocks = {"header": [], "footer": []}
        for zone in region_blocks:
            # Prefer explicit PageHeader/PageFooter detections when they contain text.
            # Heuristic region scraping is a fallback, not a peer signal, otherwise
            # the top/bottom body text can pollute header/footer metadata.
            base = typed_candidates[zone] or heuristic_candidates[zone]

            region_blocks[zone] = sorted(
                base,
                key=lambda item: (
                    0 if item.source == "typed" else 1,
                    item.block.polygon.bbox[1],
                    item.block.polygon.bbox[0],
                ),
            )

        return region_blocks

    def _build_region_block_candidate(
        self,
        block,
        text: str,
        zone: str,
        source: str,
        page_bbox,
        header_threshold: float,
        footer_threshold: float,
        page_width: float,
        page_top: float,
        page_bottom: float,
    ) -> RegionBlockCandidate:
        block_bbox = block.polygon.bbox
        x_center = (block_bbox[0] + block_bbox[2]) / 2
        if x_center <= page_bbox[0] + page_width * 0.33:
            alignment = "left"
        elif x_center >= page_bbox[0] + page_width * 0.67:
            alignment = "right"
        else:
            alignment = "center"

        if zone == "header":
            margin_distance = max((block_bbox[1] - page_top) / max(header_threshold - page_top, 1), 0)
        else:
            margin_distance = max((page_bottom - block_bbox[3]) / max(page_bottom - footer_threshold, 1), 0)

        return RegionBlockCandidate(
            block=block,
            zone=zone,
            source=source,
            alignment=alignment,
            margin_distance=min(margin_distance, 1.0),
            text=text,
        )

    def _compose_region_text(self, region_blocks: List[RegionBlockCandidate]) -> Optional[str]:
        texts = []
        seen = set()
        for candidate in region_blocks:
            text = self._clean_text(candidate.display_text or candidate.text)
            if not text or text in seen:
                continue
            seen.add(text)
            texts.append(text)

        if not texts:
            return None
        return self._clean_text(" ".join(texts))

    def _extract_zone_text(
        self,
        block,
        document: Document,
        zone: str,
        zone_start: float,
        zone_end: float,
    ) -> str:
        lines = []
        if hasattr(block, "contained_blocks"):
            try:
                lines = block.contained_blocks(document, (BlockTypes.Line,))
            except Exception:
                lines = []

        selected_entries = []
        if lines:
            for line in sorted(lines, key=lambda item: (item.polygon.bbox[1], item.polygon.bbox[0])):
                line_bbox = line.polygon.bbox
                if zone == "header" and line_bbox[1] > zone_end:
                    continue
                if zone == "footer" and line_bbox[3] < zone_start:
                    continue
                line_text = self._clean_text(line.raw_text(document))
                if line_text:
                    selected_entries.append((line_bbox, line_text))

        if not selected_entries and lines:
            ordered_lines = sorted(lines, key=lambda item: (item.polygon.bbox[1], item.polygon.bbox[0]))
            block_bbox = block.polygon.bbox
            if zone == "header" and block_bbox[1] <= zone_end:
                fallback_lines = ordered_lines[:2]
            elif zone == "footer" and block_bbox[3] >= zone_start:
                fallback_lines = ordered_lines[-2:]
            else:
                fallback_lines = []

            for line in fallback_lines:
                line_text = self._clean_text(line.raw_text(document))
                if line_text:
                    selected_entries.append((line.polygon.bbox, line_text))

        if selected_entries:
            clusters: List[List[Tuple[object, str]]] = []
            current_cluster: List[Tuple[object, str]] = []
            previous_bbox = None

            for line_bbox, line_text in selected_entries:
                if previous_bbox is None:
                    current_cluster = [(line_bbox, line_text)]
                else:
                    gap = line_bbox[1] - previous_bbox[3]
                    prev_height = max(previous_bbox[3] - previous_bbox[1], 1)
                    curr_height = max(line_bbox[3] - line_bbox[1], 1)
                    gap_threshold = max(prev_height, curr_height) * 1.2
                    if gap <= gap_threshold:
                        current_cluster.append((line_bbox, line_text))
                    else:
                        clusters.append(current_cluster)
                        current_cluster = [(line_bbox, line_text)]
                previous_bbox = line_bbox

            if current_cluster:
                clusters.append(current_cluster)

            edge_cluster = clusters[0] if zone == "header" else clusters[-1]
            cluster_texts = [line_text for _, line_text in edge_cluster[:3]]
            if cluster_texts:
                return " ".join(cluster_texts)

        block_bbox = block.polygon.bbox
        if self._bbox_intersects_vertical_zone(block_bbox, zone_start, zone_end):
            return self._get_block_text(block, document)

        return ""

    def _bbox_intersects_vertical_zone(self, bbox, zone_start: float, zone_end: float) -> bool:
        top = bbox[1]
        bottom = bbox[3]
        return max(top, zone_start) < min(bottom, zone_end)

    def _extract_page_candidates(self, region_blocks: dict[str, List[RegionBlockCandidate]]) -> List[PageNumberCandidate]:
        candidates: List[PageNumberCandidate] = []
        for zone in self.printed_page_zones or []:
            canonical_zone = self._canonical_zone(zone)
            if canonical_zone not in ("header", "footer"):
                continue

            for region_candidate in region_blocks.get(canonical_zone, []):
                matches = self._parse_page_number_candidates(region_candidate.text)
                for match in matches:
                    score = self._score_candidate(match, region_candidate)
                    match.zone = region_candidate.zone
                    match.source = region_candidate.source
                    match.alignment = region_candidate.alignment
                    match.margin_distance = region_candidate.margin_distance
                    match.block_type = region_candidate.block.block_type
                    match.base_score = score
                    match.final_score = score
                    candidates.append(match)

        deduped = {}
        for candidate in candidates:
            key = (
                candidate.zone,
                candidate.page_number,
                candidate.alignment,
                candidate.text,
                candidate.match_start,
                candidate.match_end,
            )
            existing = deduped.get(key)
            if existing is None or candidate.base_score > existing.base_score:
                deduped[key] = candidate
        return list(deduped.values())

    def _canonical_zone(self, zone: str) -> str:
        if "header" in zone or zone.startswith("top"):
            return "header"
        if "footer" in zone or zone.startswith("bottom"):
            return "footer"
        return zone

    def _parse_page_number_candidates(self, text: str) -> List[PageNumberCandidate]:
        text = self._clean_text(text)
        if not text:
            return []

        matches: List[PageNumberCandidate] = []
        seen = set()

        for fmt, page_number, match_text, match_start, match_end in self._iter_matches(text):
            if not self._is_valid_page_number_candidate(page_number, fmt, text, match_text):
                continue

            numeric = self._to_numeric(page_number)
            key = (fmt, page_number, match_text, match_start, match_end)
            if key in seen:
                continue
            seen.add(key)

            matches.append(
                PageNumberCandidate(
                    page_number=page_number,
                    numeric=numeric,
                    format=fmt,
                    zone="",
                    source="",
                    alignment="center",
                    text=text,
                    match_text=match_text,
                    match_start=match_start,
                    match_end=match_end,
                    margin_distance=1.0,
                    block_type=None,
                )
            )

        return matches

    def _iter_matches(self, text: str):
        if self.page_number_custom_pattern:
            for match in re.finditer(self.page_number_custom_pattern, text):
                value = self._extract_match_value(match)
                if value:
                    yield "custom", value, match.group(0), match.start(), match.end()
            return

        formats = self._candidate_formats()
        if "arabic" in formats:
            yield from self._extract_arabic_matches(text)
        if "roman" in formats:
            yield from self._extract_roman_matches(text)
        if "chinese" in formats:
            yield from self._extract_chinese_matches(text)

    def _candidate_formats(self) -> List[str]:
        if self.page_number_format == "arabic":
            return ["arabic"]
        if self.page_number_format == "roman":
            return ["roman"]
        if self.page_number_format == "chinese":
            return ["chinese"]
        return ["arabic", "roman", "chinese"]

    def _extract_match_value(self, match: re.Match) -> str:
        if match.lastindex:
            for index in range(1, match.lastindex + 1):
                value = match.group(index)
                if value is not None:
                    return value.strip()
        return match.group(0).strip()

    def _extract_arabic_matches(self, text: str):
        patterns = [
            (r"(?i)\bpage\s*(\d{1,4})\b", lambda m: m.group(1)),
            (r"(?i)\bp\.\s*(\d{1,4})\b", lambda m: m.group(1)),
            (r"第\s*(\d{1,4})\s*[页頁叶葉]?", lambda m: m.group(1)),
            (r"(?<!\d)(\d{1,4})\s*[页頁叶葉]", lambda m: m.group(1)),
            (r"(?<!\d)(\d{1,4})(?!\d)", lambda m: m.group(1)),
        ]
        for pattern, extractor in patterns:
            for match in re.finditer(pattern, text):
                yield "arabic", extractor(match).strip(), match.group(0).strip(), match.start(), match.end()

    def _extract_roman_matches(self, text: str):
        patterns = [
            (r"(?i)\bpage\s*([IVXLCDM]{1,8})\b", lambda m: m.group(1)),
            (r"(?i)\bp\.\s*([IVXLCDM]{1,8})\b", lambda m: m.group(1)),
            (r"(?<![A-Za-z])([IVXLCDM]{1,8})(?![A-Za-z])", lambda m: m.group(1)),
        ]
        for pattern, extractor in patterns:
            for match in re.finditer(pattern, text):
                yield "roman", extractor(match).strip(), match.group(0).strip(), match.start(), match.end()

    def _extract_chinese_matches(self, text: str):
        patterns = [
            (rf"第([{CHINESE_DIGIT_CHARS}]+)[页頁叶葉]", lambda m: m.group(0)),
            (rf"([{CHINESE_DIGIT_CHARS}]+)[页頁叶葉]", lambda m: m.group(0)),
            (rf"卷[{CHINESE_DIGIT_CHARS}]+\s*第([{CHINESE_DIGIT_CHARS}]+)", lambda m: m.group(0)),
        ]
        for pattern, extractor in patterns:
            for match in re.finditer(pattern, text):
                yield "chinese", extractor(match).strip(), match.group(0).strip(), match.start(), match.end()

        if re.fullmatch(rf"\s*[{CHINESE_DIGIT_CHARS}]{{1,6}}\s*", text):
            value = text.strip()
            yield "chinese", value, value, 0, len(value)

    def _score_candidate(
        self, candidate: PageNumberCandidate, region_candidate: RegionBlockCandidate
    ) -> float:
        text = region_candidate.text
        clean_text = self._clean_text(text)
        clean_match = self._clean_text(candidate.match_text)
        numeric_tokens = re.findall(r"(?<!\d)\d{1,4}(?!\d)", clean_text)
        explicit_edge_candidate = self._is_explicit_margin_edge_candidate(
            candidate, region_candidate, clean_text
        )

        score = 0.0
        score += 1.0 if region_candidate.zone == "footer" else 0.85
        score += 0.65 if region_candidate.source == "typed" else 0.2
        score += 0.35 * (1.0 - region_candidate.margin_distance)

        if len(clean_text) <= 8:
            score += 0.45
        elif len(clean_text) <= 20:
            score += 0.2
        else:
            score -= 0.35

        if clean_text == clean_match or clean_text == candidate.page_number:
            score += 0.45
        elif clean_match and clean_match in clean_text:
            score += 0.2

        if self._count_numeric_like_tokens(clean_text) == 1:
            score += 0.35
        else:
            score -= 0.3

        if candidate.format == "arabic" and candidate.page_number.isdigit():
            max_token_len = max((len(token) for token in numeric_tokens), default=len(candidate.page_number))
            if len(numeric_tokens) > 1:
                if len(candidate.page_number) == max_token_len:
                    score += 0.3
                elif explicit_edge_candidate:
                    # Newspaper-style headers often place the real page number at the
                    # left/right edge while longer year tokens sit in the middle.
                    score += 0.15
                else:
                    score -= 0.3

        if candidate.format in ("arabic", "roman") and any(marker in clean_text for marker in ("Page", "page", "第", "页", "頁", "叶", "葉")):
            score += 0.2
        if candidate.format == "chinese" and any(marker in clean_match for marker in ("第", "页", "頁", "叶", "葉")):
            score += 0.35

        score += self._score_edge_fragment(candidate, clean_text)
        if explicit_edge_candidate:
            # Recover candidates from explicit PageHeader/PageFooter blocks whose
            # bounding box is slightly lower than ideal but whose number is still
            # clearly anchored at the text edge.
            score += 0.35

        if region_candidate.alignment in ("left", "right"):
            score += 0.1

        if self._looks_like_year_context(clean_text, candidate.page_number):
            score -= 2.5
        if self._looks_like_long_header_metadata(clean_text):
            score -= 0.35

        return score

    def _count_numeric_like_tokens(self, text: str) -> int:
        count = 0
        count += len(re.findall(r"(?<!\d)\d{1,4}(?!\d)", text))
        count += len(re.findall(r"(?<![A-Za-z])[IVXLCDM]{1,8}(?![A-Za-z])", text, re.IGNORECASE))
        count += len(re.findall(rf"[{CHINESE_DIGIT_CHARS}]{{1,6}}", text))
        return count

    def _looks_like_year_context(self, text: str, candidate: str) -> bool:
        if self._looks_like_english_date_context(text, candidate):
            return True

        escaped = re.escape(candidate)
        for match in re.finditer(escaped, text):
            window_start = max(match.start() - 4, 0)
            window_end = min(match.end() + 8, len(text))
            window = text[window_start:window_end]
            if re.search(rf"{escaped}\s*年", window):
                return True
            if re.search(rf"(年|月|日|号|號|期|卷)\s*{escaped}", window):
                return True

            # 处理 OCR 将年份拆成两段数字的情况，例如 "18 64年"、"18.64年"、"18-64年"
            if candidate.isdigit() and len(candidate) <= 2:
                if re.search(rf"{escaped}\s*[\s.\-_/]?\s*\d{{2}}\s*年", window):
                    return True
                if re.search(rf"\d{{2}}\s*[\s.\-_/]?\s*{escaped}\s*年", window):
                    return True
                if re.search(rf"{escaped}\s*[\s.\-_/]?\s*\d{{2,3}}\s*(年|年代|世纪|世紀)", window):
                    return True
                if re.search(rf"\d{{2,3}}\s*[\s.\-_/]?\s*{escaped}\s*(年|年代|世纪|世紀)", window):
                    return True

        if re.fullmatch(r"\d{3,4}", candidate) and re.search(rf"\b{escaped}\b\s*年", text):
            return True
        return False

    def _looks_like_long_header_metadata(self, text: str) -> bool:
        if len(text) < 18:
            return False

        if any(marker in text for marker in YEAR_MARKERS):
            return True
        if re.search(rf"(?i)\b{ENGLISH_MONTH_PATTERN}\b", text):
            return True
        return False

    def _looks_like_english_date_context(self, text: str, candidate: str) -> bool:
        escaped = re.escape(candidate)
        patterns = [
            rf"(?i)\b{ENGLISH_MONTH_PATTERN}\s+{escaped}(?:st|nd|rd|th)?\b(?:\s*[,.\]\)])?\s*\d{{2,4}}\b",
            rf"(?i)\b{escaped}(?:st|nd|rd|th)?\s+{ENGLISH_MONTH_PATTERN}\b(?:\s+\d{{2,4}}\b)?",
            rf"(?i)\b{ENGLISH_MONTH_PATTERN}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*[,.\]\)])?\s*{escaped}\b",
            rf"(?i)\b\d{{1,2}}(?:st|nd|rd|th)?\s+{ENGLISH_MONTH_PATTERN}(?:\s*[,.\]\)])?\s*{escaped}\b",
        ]
        return any(re.search(pattern, text) for pattern in patterns)

    def _score_edge_fragment(self, candidate: PageNumberCandidate, text: str) -> float:
        if not text or self._count_numeric_like_tokens(text) <= 1:
            return 0.0

        edge_distance, left_ratio, right_ratio = self._match_edge_distance(candidate, text)

        if edge_distance <= 0.08:
            return 0.95
        if edge_distance <= 0.16:
            return 0.55
        if left_ratio >= 0.28 and right_ratio >= 0.28:
            return -0.45
        return 0.0

    def _match_edge_distance(self, candidate: PageNumberCandidate, text: str) -> Tuple[float, float, float]:
        text_len = max(len(text), 1)
        match_start = max(candidate.match_start, 0)
        match_end = min(candidate.match_end, text_len)
        left_ratio = match_start / text_len
        right_ratio = (text_len - match_end) / text_len
        edge_distance = min(left_ratio, right_ratio)
        return edge_distance, left_ratio, right_ratio

    def _is_explicit_margin_edge_candidate(
        self,
        candidate: PageNumberCandidate,
        region_candidate: RegionBlockCandidate,
        text: str,
    ) -> bool:
        if region_candidate.source != "typed":
            return False
        if region_candidate.block.block_type not in (BlockTypes.PageHeader, BlockTypes.PageFooter):
            return False
        if not text or len(text) < 8:
            return False
        if candidate.format not in ("arabic", "roman", "chinese", "custom"):
            return False

        edge_distance, _, _ = self._match_edge_distance(candidate, text)
        return edge_distance <= 0.12

    def _select_candidates(
        self, page_candidates: List[List[PageNumberCandidate]]
    ) -> List[Optional[PageNumberCandidate]]:
        dominant_profile = self._infer_dominant_profile(page_candidates)

        initial = []
        for candidates in page_candidates:
            self._apply_profile_bonus(candidates, dominant_profile)
            initial.append(self._pick_candidate(candidates))

        anchors = {
            page_idx: candidate
            for page_idx, candidate in enumerate(initial)
            if candidate is not None and candidate.final_score >= self.min_anchor_score
        }

        final = []
        for page_idx, candidates in enumerate(page_candidates):
            for candidate in candidates:
                candidate.final_score = candidate.base_score + self._profile_bonus(candidate, dominant_profile)
                candidate.final_score += self._neighbor_bonus(page_idx, candidate, anchors)
            final.append(self._pick_candidate(candidates))

        return final

    def _infer_dominant_profile(
        self, page_candidates: List[List[PageNumberCandidate]]
    ) -> Optional[Tuple[str, str]]:
        profile_counter = Counter()
        for candidates in page_candidates:
            if not candidates:
                continue
            best = max(candidates, key=lambda item: item.base_score)
            if best.numeric is None or best.base_score < self.min_anchor_score:
                continue
            profile_counter[(best.zone, best.alignment)] += 1

        if not profile_counter:
            return None
        return profile_counter.most_common(1)[0][0]

    def _apply_profile_bonus(
        self, candidates: List[PageNumberCandidate], profile: Optional[Tuple[str, str]]
    ):
        for candidate in candidates:
            candidate.final_score = candidate.base_score + self._profile_bonus(candidate, profile)

    def _profile_bonus(
        self, candidate: PageNumberCandidate, profile: Optional[Tuple[str, str]]
    ) -> float:
        if profile is None:
            return 0.0

        bonus = 0.0
        dominant_zone, dominant_alignment = profile
        if candidate.zone == dominant_zone:
            bonus += 0.25
        if candidate.alignment == dominant_alignment:
            bonus += 0.2
        return bonus

    def _neighbor_bonus(
        self,
        page_idx: int,
        candidate: PageNumberCandidate,
        anchors: dict[int, PageNumberCandidate],
    ) -> float:
        if candidate.numeric is None or not anchors:
            return 0.0

        bonus = 0.0

        prev_pages = [idx for idx in anchors if idx < page_idx]
        if prev_pages:
            prev_idx = max(prev_pages)
            prev_candidate = anchors[prev_idx]
            if prev_candidate.numeric is not None:
                expected = prev_candidate.numeric + (page_idx - prev_idx)
                diff = abs(candidate.numeric - expected)
                if diff == 0:
                    bonus += 0.55
                elif diff == 1:
                    bonus += 0.15
                elif diff >= 3:
                    bonus -= 0.25

        next_pages = [idx for idx in anchors if idx > page_idx]
        if next_pages:
            next_idx = min(next_pages)
            next_candidate = anchors[next_idx]
            if next_candidate.numeric is not None:
                expected = next_candidate.numeric - (next_idx - page_idx)
                diff = abs(candidate.numeric - expected)
                if diff == 0:
                    bonus += 0.55
                elif diff == 1:
                    bonus += 0.15
                elif diff >= 3:
                    bonus -= 0.25

        return bonus

    def _pick_candidate(
        self, candidates: List[PageNumberCandidate]
    ) -> Optional[PageNumberCandidate]:
        if not candidates:
            return None

        ranked = sorted(candidates, key=lambda item: item.final_score, reverse=True)
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None

        if best.final_score < self.min_candidate_score:
            return None

        if second and second.page_number != best.page_number:
            if best.final_score - second.final_score < self.ambiguity_gap:
                return None

        return best

    def _get_block_text(self, block, document: Document) -> str:
        texts = []

        if hasattr(block, "structure") and block.structure:
            for child_id in block.structure:
                child = document.get_block(child_id)
                if child:
                    child_text = self._get_block_text(child, document)
                    if child_text:
                        texts.append(child_text)

        if hasattr(block, "text") and block.text:
            texts.append(block.text)
        elif hasattr(block, "html") and block.html:
            texts.append(re.sub(r"<[^>]+>", "", block.html))

        return " ".join(texts).strip()

    def _clean_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _is_valid_page_number_candidate(
        self, page_number: str, fmt: str, full_text: str, match_text: str
    ) -> bool:
        page_number = self._clean_text(page_number)
        full_text = self._clean_text(full_text)
        match_text = self._clean_text(match_text)
        if not page_number:
            return False

        if fmt in ("arabic", "custom") and page_number.isdigit():
            num = int(page_number)
            if page_number.startswith("0") or num <= 0 or num > 999:
                return False
            if self._looks_like_year_context(full_text, page_number):
                return False
            return True

        if fmt == "roman":
            if not re.fullmatch(r"[IVXLCDMivxlcdm]{1,8}", page_number):
                return False
            if len(page_number) == 1 and page_number.upper() not in {"I", "V", "X"}:
                return False
            if self._looks_like_year_context(full_text, page_number):
                return False
            return True

        if fmt == "chinese":
            if not re.search(rf"[{CHINESE_DIGIT_CHARS}]", page_number):
                return False
            if not any(marker in match_text for marker in ("第", "页", "頁", "叶", "葉")):
                if not re.fullmatch(rf"[{CHINESE_DIGIT_CHARS}]{{1,6}}", page_number):
                    return False
                if any(marker in full_text for marker in YEAR_MARKERS):
                    return False
            return self._to_numeric(page_number) is not None

        return False

    def _set_page_metadata(
        self,
        page,
        machine_page_number: int,
        printed_page_number: Optional[str],
        header_text: Optional[str],
        footer_text: Optional[str],
    ):
        if not hasattr(page, "_internal_metadata"):
            page._internal_metadata = {}

        page._internal_metadata["machine_page_number"] = machine_page_number
        page._internal_metadata["page_number_format"] = self.page_number_format

        if header_text:
            page._internal_metadata["page_header_text"] = header_text
        if footer_text:
            page._internal_metadata["page_footer_text"] = footer_text

        if printed_page_number:
            page._internal_metadata["printed_page_number"] = printed_page_number
            numeric = self._to_numeric(printed_page_number)
            if numeric is not None:
                page._internal_metadata["printed_page_number_numeric"] = numeric

    def _to_numeric(self, page_number: str) -> Optional[int]:
        try:
            return int(page_number)
        except ValueError:
            pass

        if re.fullmatch(r"[IVXLCDMivxlcdm]+", page_number):
            return self._roman_to_int(page_number.upper())

        return self._chinese_to_int(page_number)

    def _roman_to_int(self, roman: str) -> Optional[int]:
        try:
            result = 0
            prev = 0
            for char in reversed(roman):
                curr = ROMAN_NUMERALS.get(char, 0)
                if curr < prev:
                    result -= curr
                else:
                    result += curr
                prev = curr
            return result if result > 0 else None
        except Exception:
            return None

    def _chinese_to_int(self, chinese: str) -> Optional[int]:
        try:
            match = re.search(rf"[{CHINESE_DIGIT_CHARS}]+", chinese)
            if not match:
                return None

            num_str = match.group(0)

            if all(char in CHINESE_NUMBERS and CHINESE_NUMBERS[char] < 10 for char in num_str):
                result = 0
                for char in num_str:
                    result = result * 10 + CHINESE_NUMBERS[char]
                return result if result > 0 else None

            result = 0
            temp = 0
            for char in num_str:
                if char not in CHINESE_NUMBERS:
                    continue
                val = CHINESE_NUMBERS[char]
                if val >= 10:
                    if temp == 0:
                        temp = 1
                    result += temp * val
                    temp = 0
                else:
                    temp = temp * 10 + val if temp > 0 else val

            result += temp
            return result if result > 0 else None
        except Exception:
            return None


def get_page_number(page, prefer_printed: bool = True) -> Optional[str]:
    """
    获取页面页码的便捷函数。
    """

    if not hasattr(page, "_internal_metadata"):
        return None

    metadata = page._internal_metadata
    if prefer_printed and "printed_page_number" in metadata:
        return metadata["printed_page_number"]
    if "machine_page_number" in metadata:
        return str(metadata["machine_page_number"])
    return None
