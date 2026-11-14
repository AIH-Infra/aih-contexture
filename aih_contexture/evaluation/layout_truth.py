"""Hand-labelled layout truth: block grouping, block type and reading order.

CER and content recall cannot say whether a detector grouped lines into the right blocks, typed
them correctly or put them in reading order. The truth here is made of the PDF text layer's own
lines (exact boxes, see ``benchmarks/layout_truth/prepare.py``) plus a label file that says, per
page, which lines form one block, of what type, in which order. A detector's Middle JSON is scored
against it without caring about its text: a truth line belongs to the predicted block whose box
contains the line's centre (the smallest one if blocks nest).

Label file, one section per page::

    [<sample id>_p<page index>]
    <Type> <spec>          # blocks in reading order
    spec = comma separated line numbers, ranges ``a-b`` with optional step ``a-b/2``, or ``IMG<n>``

Types: Text SectionHeader Caption Footnote Table Picture Equation PageHeader PageFooter Marginalia Ignore.
``Ignore`` (artefacts) and ``Marginalia`` (line numbers, side notes: no detector has a type for them) are labelled so every
line is accounted for, but they leave the score alone: whether a detector keeps them out of body blocks is not judged.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from aih_contexture.evaluation.metrics import kendall_tau

TRUTH_TYPES = (
    "Text", "SectionHeader", "Caption", "Footnote", "Table", "Picture", "Equation",
    "PageHeader", "PageFooter", "Marginalia", "Ignore",
)
FURNITURE = {"PageHeader", "PageFooter"}
UNSCORED = {"Ignore", "Marginalia"}
# Types are compared by class: a detector that calls a margin number a page footer is not penalised.
CLASS_OF = {
    "Text": "Text", "SectionHeader": "SectionHeader", "Caption": "Caption", "Footnote": "Footnote",
    "Table": "Table", "Picture": "Picture", "Equation": "Equation",
    "PageHeader": "Furniture", "PageFooter": "Furniture",
}
PREDICTED_ALIASES = {
    "Title": "SectionHeader", "Heading": "SectionHeader", "Section-Header": "SectionHeader",
    "ListItem": "Text", "List-item": "Text", "Code": "Text", "TableOfContents": "Text",
    "Handwriting": "Text", "Form": "Text", "Paragraph": "Text",
    "Figure": "Picture", "Image": "Picture", "Formula": "Equation",
    "Page-header": "PageHeader", "Page-footer": "PageFooter",
}
IMAGE_IOU_MATCH = 0.5


@dataclass(slots=True)
class TruthBlock:
    type: str
    lines: tuple[int, ...] = ()
    images: tuple[int, ...] = ()


@dataclass(slots=True)
class TruthPage:
    key: str
    width: float
    height: float
    lines: list[dict[str, Any]]
    images: list[dict[str, Any]]
    blocks: list[TruthBlock] = field(default_factory=list)


def parse_spec(spec: str) -> tuple[list[int], list[int]]:
    """``0-3,7,10-20/2,IMG1`` -> (line numbers, image numbers)."""
    lines: list[int] = []
    images: list[int] = []
    for token in (part.strip() for part in spec.split(",")):
        if not token:
            continue
        image = re.fullmatch(r"IMG(\d+)", token)
        span = re.fullmatch(r"(\d+)(?:-(\d+)(?:/(\d+))?)?", token)
        if image:
            images.append(int(image.group(1)))
        elif span:
            start = int(span.group(1))
            stop = int(span.group(2)) if span.group(2) else start
            step = int(span.group(3)) if span.group(3) else 1
            lines.extend(range(start, stop + 1, step))
        else:
            raise ValueError(f"bad line spec {token!r}")
    return lines, images


def parse_labels(text: str) -> dict[str, list[TruthBlock]]:
    pages: dict[str, list[TruthBlock]] = {}
    current: list[TruthBlock] | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        header = re.fullmatch(r"\[(.+)\]", line)
        if header:
            if header.group(1) in pages:
                raise ValueError(f"line {number}: page {header.group(1)} labelled twice")
            current = pages.setdefault(header.group(1), [])
            continue
        if current is None:
            raise ValueError(f"line {number}: block outside a page section")
        kind, _, spec = line.partition(" ")
        if kind not in TRUTH_TYPES:
            raise ValueError(f"line {number}: unknown type {kind!r}")
        lines, images = parse_spec(spec)
        current.append(TruthBlock(kind, tuple(lines), tuple(images)))
    return pages


def _check_page(key: str, blocks: list[TruthBlock], line_count: int, image_count: int) -> list[str]:
    problems: list[str] = []
    seen_lines: dict[int, int] = {}
    seen_images: dict[int, int] = {}
    for position, block in enumerate(blocks):
        if not block.lines and not block.images:
            problems.append(f"{key}: block {position} ({block.type}) is empty")
        for n in block.lines:
            if not 0 <= n < line_count:
                problems.append(f"{key}: line {n} does not exist (page has {line_count})")
            elif n in seen_lines:
                problems.append(f"{key}: line {n} labelled twice (blocks {seen_lines[n]} and {position})")
            seen_lines[n] = position
        for n in block.images:
            if not 0 <= n < image_count:
                problems.append(f"{key}: image {n} does not exist (page has {image_count})")
            elif n in seen_images:
                problems.append(f"{key}: image {n} labelled twice")
            seen_images[n] = position
    missing = [n for n in range(line_count) if n not in seen_lines]
    if missing:
        problems.append(f"{key}: lines never labelled: {missing}")
    missing_images = [n for n in range(image_count) if n not in seen_images]
    if missing_images:
        problems.append(f"{key}: images never labelled: {missing_images}")
    return problems


def load_truth(labels_path: str | Path, lines_path: str | Path) -> dict[str, TruthPage]:
    """Join labels with the line/image boxes; every line and image must be labelled exactly once."""
    geometry = json.loads(Path(lines_path).read_text(encoding="utf-8"))
    labels = parse_labels(Path(labels_path).read_text(encoding="utf-8"))
    pages: dict[str, TruthPage] = {}
    problems: list[str] = []
    for key, blocks in labels.items():
        if key not in geometry:
            problems.append(f"{key}: no line geometry")
            continue
        source = geometry[key]
        found = _check_page(key, blocks, len(source["lines"]), len(source.get("images") or []))
        problems.extend(found)
        width, height = source["size"]
        pages[key] = TruthPage(key, float(width), float(height), source["lines"], source.get("images") or [], blocks)
    if problems:
        raise ValueError(chr(10).join(problems))
    return pages


# ------------------------------------------------------------------ prediction side


def predicted_class(type_name: str) -> str:
    name = PREDICTED_ALIASES.get(type_name, type_name)
    return CLASS_OF.get(name, "Other")


def _area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _iou(a: list[float], b: list[float]) -> float:
    inter = _area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])
    union = _area(a) + _area(b) - inter
    return inter / union if union else 0.0


def _predicted_blocks(middle_page: dict[str, Any], truth: TruthPage) -> list[dict[str, Any]]:
    """Predicted blocks in truth coordinates, in reading order (``order`` field, else list position)."""
    scale_x = truth.width / middle_page["width"] if middle_page.get("width") else 1.0
    scale_y = truth.height / middle_page["height"] if middle_page.get("height") else 1.0
    blocks = []
    for position, block in enumerate(middle_page.get("blocks") or []):
        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        blocks.append({
            "bbox": [bbox[0] * scale_x, bbox[1] * scale_y, bbox[2] * scale_x, bbox[3] * scale_y],
            "class": predicted_class(str(block.get("type"))),
            "order": block.get("order", position),
            "position": position,
        })
    blocks.sort(key=lambda item: (item["order"], item["position"]))
    return blocks


def _owner(line: dict[str, Any], blocks: list[dict[str, Any]]) -> int | None:
    """Index of the predicted block holding the line's centre; the smallest if several do."""
    x0, y0, x1, y1 = line["bbox"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    best, best_area = None, None
    for index, block in enumerate(blocks):
        bx0, by0, bx1, by1 = block["bbox"]
        if bx0 <= cx <= bx1 and by0 <= cy <= by1:
            area = _area(block["bbox"])
            if best is None or area < best_area:
                best, best_area = index, area
    return best


def score_page(truth: TruthPage, middle_page: dict[str, Any]) -> dict[str, Any]:
    """Counts for one page; ``summarise_pages`` turns the sums into rates."""
    predicted = _predicted_blocks(middle_page, truth)
    owner: dict[int, int | None] = {}
    truth_block_of: dict[int, int] = {}
    for position, block in enumerate(truth.blocks):
        if block.type in UNSCORED:
            continue
        for n in block.lines:
            owner[n] = _owner(truth.lines[n], predicted)
            truth_block_of[n] = position
    scored = sorted(owner)

    by_class: dict[str, list[int]] = {}
    covered = correct = 0
    for n in scored:
        truth_class = CLASS_OF[truth.blocks[truth_block_of[n]].type]
        hit = owner[n] is not None
        right = hit and predicted[owner[n]]["class"] == truth_class
        covered += hit
        correct += right
        cell = by_class.setdefault(truth_class, [0, 0])
        cell[0] += right
        cell[1] += 1

    # Pair agreement on "these two lines are in the same block". An uncovered line is a block of its own.
    def predicted_cluster(n: int) -> Any:
        return owner[n] if owner[n] is not None else ("alone", n)

    same_truth = same_predicted = both = 0
    for i, a in enumerate(scored):
        for b in scored[i + 1:]:
            in_truth = truth_block_of[a] == truth_block_of[b]
            in_predicted = predicted_cluster(a) == predicted_cluster(b)
            same_truth += in_truth
            same_predicted += in_predicted
            both += in_truth and in_predicted

    # Segmentation: how many predicted blocks the truth blocks are spread over.
    truth_blocks = {truth_block_of[n] for n in scored}
    hit_blocks = {predicted_cluster(n) for n in scored}

    # Reading order over body blocks, by the block holding each truth block's first line.
    body = [
        position for position, block in enumerate(truth.blocks)
        if block.type not in FURNITURE | UNSCORED and block.lines
    ]
    truth_rank, predicted_rank = [], []
    for rank, position in enumerate(body):
        first = truth.blocks[position].lines[0]
        if owner.get(first) is not None:
            truth_rank.append(rank)
            predicted_rank.append(predicted[owner[first]]["order"])
    tau = kendall_tau(truth_rank, predicted_rank) if len(truth_rank) >= 3 else None

    pictures = [(block, n) for block in truth.blocks if block.type == "Picture" for n in block.images]
    picture_hits = sum(
        1 for _, n in pictures
        if any(p["class"] == "Picture" and _iou(p["bbox"], truth.images[n]["bbox"]) >= IMAGE_IOU_MATCH for p in predicted)
    )
    return {
        "lines": len(scored),
        "covered": covered,
        "type_correct": correct,
        "by_class": by_class,
        "pairs_truth": same_truth,
        "pairs_predicted": same_predicted,
        "pairs_both": both,
        "truth_blocks": len(truth_blocks),
        "predicted_blocks_hit": len(hit_blocks),
        "order_blocks": len(truth_rank),
        "order_tau": tau,
        "pictures": len(pictures),
        "picture_hits": picture_hits,
    }


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def summarise_pages(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Micro-average over pages (lines and pairs are summed); order tau is the mean over pages that have one."""
    rows = list(rows)
    total = {key: sum(row[key] for row in rows) for key in (
        "lines", "covered", "type_correct", "pairs_truth", "pairs_predicted", "pairs_both",
        "truth_blocks", "predicted_blocks_hit", "pictures", "picture_hits")}
    classes: dict[str, list[int]] = {}
    for row in rows:
        for name, (right, count) in row["by_class"].items():
            cell = classes.setdefault(name, [0, 0])
            cell[0] += right
            cell[1] += count
    precision = _ratio(total["pairs_both"], total["pairs_predicted"])
    recall = _ratio(total["pairs_both"], total["pairs_truth"])
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision == 0 or recall == 0 else None)
    taus = [row["order_tau"] for row in rows if row["order_tau"] is not None]
    return {
        "pages": len(rows),
        "lines": total["lines"],
        "coverage": _ratio(total["covered"], total["lines"]),
        "type_accuracy": _ratio(total["type_correct"], total["lines"]),
        "type_accuracy_by_class": {name: {"accuracy": right / count, "lines": count} for name, (right, count) in sorted(classes.items())},
        "pair_precision": precision,
        "pair_recall": recall,
        "pair_f1": f1,
        "blocks_per_truth_block": _ratio(total["predicted_blocks_hit"], total["truth_blocks"]),
        "order_tau_mean": sum(taus) / len(taus) if taus else None,
        "order_tau_pages": len(taus),
        "picture_recall": _ratio(total["picture_hits"], total["pictures"]),
        "pictures": total["pictures"],
    }
