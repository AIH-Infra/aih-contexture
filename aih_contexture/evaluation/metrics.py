"""Reference-free-of-model metrics: text error rate, table TEDS, reading order.

Everything here is a pure function over strings, HTML strings or id sequences.
Where the reference comes from (a clean PDF text layer, a hand-labelled JSON)
is the caller's decision; see ``text_layer_truth`` and ``text_baseline``.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Sequence

from lxml import html as lxml_html
from rapidfuzz.distance import Levenshtein

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str | None, *, keep_whitespace: bool = False) -> str:
    """NFKC + whitespace removal, so layout spacing and ligatures do not count as errors.

    This hides real space-insertion errors; callers that care pass keep_whitespace=True
    (whitespace is then collapsed to single spaces, not removed).
    """
    value = unicodedata.normalize("NFKC", text or "")
    if keep_whitespace:
        return _WHITESPACE.sub(" ", value).strip()
    return _WHITESPACE.sub("", value)


_TYPOGRAPHY = str.maketrans(
    {
        "‘": "'", "’": "'", "ʼ": "'", "‚": "'",
        "“": '"', "”": '"', "„": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
        "•": "-", "·": "-", "●": "-", "▪": "-", "‣": "-",
    }
)


def fold_typography(text: str) -> str:
    """Map curly quotes, dashes and bullet glyphs to ASCII.

    Used for a second, typography-blind error rate. Typographic fidelity still matters for
    scholarship, so this never replaces the strict rate; it separates "read the wrong
    character" from "wrote the right character in a plainer form" (e.g. a Markdown list dash).
    """
    return text.translate(_TYPOGRAPHY)


def edit_distance(reference: Sequence[Any], hypothesis: Sequence[Any]) -> int:
    return int(Levenshtein.distance(reference, hypothesis))


def character_error_rate(reference: str, hypothesis: str, *, keep_whitespace: bool = False) -> float | None:
    """Levenshtein distance / len(reference); None when the reference is empty.

    Can exceed 1.0 when the hypothesis is much longer than the reference.
    """
    ref = normalize_text(reference, keep_whitespace=keep_whitespace)
    hyp = normalize_text(hypothesis, keep_whitespace=keep_whitespace)
    if not ref:
        return None
    return edit_distance(ref, hyp) / len(ref)


def character_bag_scores(reference: str, hypothesis: str) -> dict[str, float | int | None]:
    """Order-free overlap of characters: separates "wrong content" from "wrong order"."""
    ref = Counter(normalize_text(reference))
    hyp = Counter(normalize_text(hypothesis))
    overlap = sum((ref & hyp).values())
    ref_total = sum(ref.values())
    hyp_total = sum(hyp.values())
    recall = overlap / ref_total if ref_total else None
    precision = overlap / hyp_total if hyp_total else None
    f1 = None
    if recall is not None and precision is not None and (recall + precision) > 0:
        f1 = 2 * recall * precision / (recall + precision)
    return {
        "reference_chars": ref_total,
        "hypothesis_chars": hyp_total,
        "overlap_chars": overlap,
        "recall": recall,
        "precision": precision,
        "f1": f1,
    }


# --------------------------------------------------------------------------- order


def kendall_tau(reference_rank: Sequence[float], hypothesis_rank: Sequence[float]) -> float | None:
    """Kendall tau-a over the paired items; None with fewer than two comparable pairs.

    Tied pairs (in either ranking) count as neither concordant nor discordant but stay
    in the denominator, so ties lower the score instead of being silently dropped.
    """
    n = len(reference_rank)
    if n != len(hypothesis_rank):
        raise ValueError("rankings must be paired")
    if n < 2:
        return None
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            product = (reference_rank[i] - reference_rank[j]) * (hypothesis_rank[i] - hypothesis_rank[j])
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    return (concordant - discordant) / (n * (n - 1) / 2)


def reading_order_scores(reference_ids: Sequence[str], hypothesis_ids: Sequence[str]) -> dict[str, Any]:
    """Compare two orderings of block ids.

    * ``order_edit_distance``: Levenshtein over the id sequences / reference length. Ids only
      in one side count as insertions/deletions, so missing and extra blocks lower it.
    * ``kendall_tau`` and ``successor_accuracy`` use only ids present in both.
    """
    common = [item for item in reference_ids if item in set(hypothesis_ids)]
    hyp_position = {item: index for index, item in enumerate(hypothesis_ids)}
    tau = kendall_tau(list(range(len(common))), [hyp_position[item] for item in common])
    successor = None
    if len(common) >= 2:
        hyp_common = [item for item in hypothesis_ids if item in set(common)]
        hyp_next = {a: b for a, b in zip(hyp_common, hyp_common[1:])}
        hits = sum(1 for a, b in zip(common, common[1:]) if hyp_next.get(a) == b)
        successor = hits / (len(common) - 1)
    return {
        "reference_items": len(reference_ids),
        "hypothesis_items": len(hypothesis_ids),
        "common_items": len(common),
        "order_edit_distance": (edit_distance(list(reference_ids), list(hypothesis_ids)) / len(reference_ids))
        if reference_ids
        else None,
        "kendall_tau": tau,
        "successor_accuracy": successor,
    }


# --------------------------------------------------------------------------- tables


class _Node:
    __slots__ = ("label", "text", "children")

    def __init__(self, label: tuple, text: str = "") -> None:
        self.label = label
        self.text = text
        self.children: list[_Node] = []


def _span(element: Any, name: str) -> int:
    try:
        return max(1, int(element.get(name) or 1))
    except ValueError:
        return 1


def _table_tree(table_html: str, *, structure_only: bool) -> _Node | None:
    if not table_html or not table_html.strip():
        return None
    root = lxml_html.fromstring(f"<div>{table_html}</div>")
    table = root.find(".//table")
    if table is None:
        return None
    tree = _Node(("table",))
    for row in table.iter("tr"):
        row_node = _Node(("tr",))
        for cell in row:
            if cell.tag not in {"td", "th"}:
                continue
            content = "" if structure_only else normalize_text(cell.text_content())
            row_node.children.append(_Node(("td", _span(cell, "colspan"), _span(cell, "rowspan")), content))
        tree.children.append(row_node)
    return tree


def _size(node: _Node) -> int:
    return 1 + sum(_size(child) for child in node.children)


def _rename_cost(a: _Node, b: _Node) -> float:
    if a.label != b.label:
        return 1.0
    if a.label[0] != "td":
        return 0.0
    longest = max(len(a.text), len(b.text))
    return edit_distance(a.text, b.text) / longest if longest else 0.0


def _tree_edit_distance(a: _Node, b: _Node) -> float:
    """Zhang-Shasha ordered tree edit distance with unit insert/delete cost."""

    def prepare(root: _Node):
        nodes: list[_Node] = []
        leftmost: list[int] = []

        def walk(node: _Node) -> int:
            first = None
            for child in node.children:
                child_leftmost = walk(child)
                if first is None:
                    first = child_leftmost
            index = len(nodes)
            nodes.append(node)
            leftmost.append(index if first is None else first)
            return leftmost[index]

        walk(root)
        keyroots = []
        seen: set[int] = set()
        for index in range(len(nodes) - 1, -1, -1):
            if leftmost[index] not in seen:
                keyroots.append(index)
                seen.add(leftmost[index])
        return nodes, leftmost, sorted(keyroots)

    nodes_a, left_a, keys_a = prepare(a)
    nodes_b, left_b, keys_b = prepare(b)
    treedist = [[0.0] * len(nodes_b) for _ in nodes_a]

    for i in keys_a:
        for j in keys_b:
            la, lb = left_a[i], left_b[j]
            rows, cols = i - la + 2, j - lb + 2
            forest = [[0.0] * cols for _ in range(rows)]
            for x in range(1, rows):
                forest[x][0] = forest[x - 1][0] + 1.0
            for y in range(1, cols):
                forest[0][y] = forest[0][y - 1] + 1.0
            for x in range(1, rows):
                for y in range(1, cols):
                    ia, jb = la + x - 1, lb + y - 1
                    if left_a[ia] == la and left_b[jb] == lb:
                        forest[x][y] = min(
                            forest[x - 1][y] + 1.0,
                            forest[x][y - 1] + 1.0,
                            forest[x - 1][y - 1] + _rename_cost(nodes_a[ia], nodes_b[jb]),
                        )
                        treedist[ia][jb] = forest[x][y]
                    else:
                        forest[x][y] = min(
                            forest[x - 1][y] + 1.0,
                            forest[x][y - 1] + 1.0,
                            forest[left_a[ia] - la][left_b[jb] - lb] + treedist[ia][jb],
                        )
    return treedist[len(nodes_a) - 1][len(nodes_b) - 1]


def table_teds(reference_html: str, hypothesis_html: str, *, structure_only: bool = False) -> float | None:
    """Tree-edit-distance similarity of two HTML tables, in [0, 1] (1 = identical).

    PubTabNet convention: tree is table > tr > td; a td matches another td only
    if colspan and rowspan agree, and then costs the normalized edit distance of
    its text (zero in ``structure_only`` mode). None when the reference has no table.
    A missing hypothesis table scores 0.
    """
    reference = _table_tree(reference_html, structure_only=structure_only)
    if reference is None:
        return None
    hypothesis = _table_tree(hypothesis_html, structure_only=structure_only)
    if hypothesis is None:
        return 0.0
    distance = _tree_edit_distance(reference, hypothesis)
    return max(0.0, 1.0 - distance / max(_size(reference), _size(hypothesis)))


def table_shape(table_html: str) -> dict[str, int] | None:
    """Rows and grid columns, with row/col spans expanded. None when there is no table."""
    if not table_html or not table_html.strip():
        return None
    root = lxml_html.fromstring(f"<div>{table_html}</div>")
    table = root.find(".//table")
    if table is None:
        return None
    occupied: set[tuple[int, int]] = set()
    rows = columns = cells = 0
    for row_index, row in enumerate(table.iter("tr")):
        rows = row_index + 1
        col = 0
        for cell in row:
            if cell.tag not in {"td", "th"}:
                continue
            while (row_index, col) in occupied:
                col += 1
            colspan, rowspan = _span(cell, "colspan"), _span(cell, "rowspan")
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied.add((row_index + dr, col + dc))
            col += colspan
            columns = max(columns, col)
            cells += 1
    return {"rows": rows, "columns": columns, "cells": cells}
