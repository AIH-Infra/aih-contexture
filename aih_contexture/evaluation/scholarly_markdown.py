from __future__ import annotations

import re
from pathlib import Path
from typing import Any


OPEN_CLOSE_BLOCKS = ("ImageDescription", "Margin", "MarginalNote", "InlineAnnotation", "ComplexRegion")
LEGACY_HTML_SUP_RE = re.compile(r"<sup>\s*([0-9]{1,4}|[ivxlcdm]{1,12}|\*+)\s*\)</sup>", re.IGNORECASE)
MARKDOWN_FOOTNOTE_DEF_RE = re.compile(r"(?m)^\[\^[^\]]+\]:")
MARKDOWN_FOOTNOTE_REF_RE = re.compile(r"(?<!\!)\[\^[^\]]+\](?!:)")
LEGACY_MARGIN_BLOCKQUOTE_RE = re.compile(r"(?m)^>\s*\*\*\[Marginal-(?:Left|Right|Top|Bottom|Note)\]\*\*")
LEGACY_MARGIN_COMMENT_RE = re.compile(r"<!--\s*MarginalNote\b")
CLASSICAL_LOCATOR_ENDPOINT = r"(?:\d{3}[ab](?:\d{1,2})?|\d{3}[ab]?|\d{1,4}(?:\.\d{1,3})?|\[\d{1,4}\])"
CLASSICAL_LOCATOR_RE = re.compile(
    rf"^(?P<start>{CLASSICAL_LOCATOR_ENDPOINT})(?:-(?P<end>(?:[ab](?:\d{{1,2}})?|{CLASSICAL_LOCATOR_ENDPOINT})))?$"
)
PROBABLE_BEKKER_LOCATOR_RE = re.compile(r"^…?\s*\d{3}[ab](?:\d{0,2})?(?=$|[-…])")
PROBABLE_BRACKET_LOCATOR_RE = re.compile(r"^…?\s*\[\d{1,4}\]")
PROBABLE_NUMERIC_LOCATOR_RE = re.compile(r"^…?\s*\d{1,4}(?:\.\d{1,3})?(?=$|[-…])")
DATE_COMMENT_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")


def evaluate_scholarly_markdown_text(
    text: str,
    *,
    source_path: str | None = None,
    strict_new_output: bool = True,
    validate_classical_locators: bool = False,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    lines = text.splitlines()

    if not text.strip():
        errors.append({"code": "empty_document", "message": "Markdown document is empty."})

    anchors = _anchors(text)
    if not anchors:
        errors.append({"code": "missing_page_anchors", "message": "Markdown document has no interval page anchors."})
    else:
        expected = list(range(anchors[0], anchors[-1] + 1))
        if anchors != expected:
            errors.append({
                "code": "non_contiguous_page_anchors",
                "message": f"Expected contiguous anchors {expected}, got {anchors}.",
            })
        if anchors[0] != 0:
            warnings.append({"code": "first_anchor_not_zero", "message": f"First anchor is {anchors[0]}, expected 0."})

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if re.match(r"<!--\s*page-(header|footer)\s*:", stripped, flags=re.IGNORECASE):
            warnings.append({
                "code": "legacy_page_header_footer",
                "message": "Use PageHeader/PageFooter comment casing for new output.",
                "line": str(line_no),
            })

        # Classical page locator comments intentionally have no label. Validate
        # only comments that look like locator data; ordinary HTML comments
        # (including IDs and descriptive metadata) are unaffected.
        for comment in re.finditer(r"<!--(.*?)-->", line) if validate_classical_locators else ():
            body = comment.group(1).strip()
            if not body or ":" in body:
                continue
            # Unlabelled date/prose comments have no declared locator role.
            # Recognize only typed Bekker shapes, old-page brackets or a bare
            # number. Generated locators use this constrained syntax.
            if not _is_probable_classical_locator(body):
                continue
            candidate = _locator_candidate(body)
            if CLASSICAL_LOCATOR_RE.fullmatch(candidate) is None:
                errors.append({
                    "code": "invalid_classical_locator_comment",
                    "message": f"Malformed unlabeled classical locator comment: {body!r}.",
                    "line": str(line_no),
                })

    legacy_html_sup_count = len(LEGACY_HTML_SUP_RE.findall(text))
    markdown_footnote_definition_count = len(MARKDOWN_FOOTNOTE_DEF_RE.findall(text))
    markdown_footnote_reference_count = len(MARKDOWN_FOOTNOTE_REF_RE.findall(text))
    legacy_margin_blockquote_count = len(LEGACY_MARGIN_BLOCKQUOTE_RE.findall(text))
    legacy_marginal_note_comment_count = len(LEGACY_MARGIN_COMMENT_RE.findall(text))
    if strict_new_output:
        legacy_checks = [
            (
                legacy_html_sup_count,
                "legacy_html_superscript_marker",
                "Use <sup>n</sup>, not legacy <sup>n)</sup>, in new output.",
            ),
            (
                markdown_footnote_definition_count + markdown_footnote_reference_count,
                "legacy_markdown_footnote",
                "Use <sup>n</sup> footnote lines, not Markdown footnotes, in new output.",
            ),
            (
                legacy_margin_blockquote_count,
                "legacy_margin_blockquote",
                "Use Margin:left/right comment blocks, not Marginal-* blockquotes, in new output.",
            ),
            (
                legacy_marginal_note_comment_count,
                "legacy_marginal_note_comment",
                "Use Margin:left/right comment blocks, not MarginalNote comment blocks, in new output.",
            ),
        ]
        for count, code, message in legacy_checks:
            if count:
                errors.append({"code": code, "message": f"{message} Found {count} occurrence(s)."})

    for tag in OPEN_CLOSE_BLOCKS:
        opens = len(re.findall(rf"<!--\s*{tag}\b", text))
        closes = len(re.findall(rf"<!--\s*/{tag}\s*-->", text))
        if opens != closes:
            errors.append({
                "code": "unbalanced_comment_block",
                "message": f"{tag} comment blocks are unbalanced: {opens} openings, {closes} closings.",
            })

    footnote_blocks = len(re.findall(r"<!--\s*FootnoteBlock\b", text))
    footnote_defs = len(re.findall(r"(?m)^(?:\[\^[^\]]+\]:|<sup>[^<]+</sup>\s+)", text))

    metrics = {
        "line_count": len(lines),
        "anchor_count": len(anchors),
        "first_anchor": anchors[0] if anchors else None,
        "final_anchor": anchors[-1] if anchors else None,
        "page_header_count": len(re.findall(r"<!--\s*PageHeader\s*:", text)),
        "page_footer_count": len(re.findall(r"<!--\s*PageFooter\s*:", text)),
        "footnote_block_count": footnote_blocks,
        "footnote_definition_count": footnote_defs,
        "legacy_html_superscript_marker_count": legacy_html_sup_count,
        "markdown_footnote_definition_count": markdown_footnote_definition_count,
        "markdown_footnote_reference_count": markdown_footnote_reference_count,
        "legacy_margin_blockquote_count": legacy_margin_blockquote_count,
        "legacy_marginal_note_comment_count": legacy_marginal_note_comment_count,
        "image_description_count": len(re.findall(r"<!--\s*ImageDescription\b", text)),
        "margin_count": len(re.findall(r"<!--\s*Margin\s*:", text)),
        "marginal_note_count": len(re.findall(r"<!--\s*(?:Margin\s*:|MarginalNote\b)", text)),
        "inline_annotation_count": len(re.findall(r"<!--\s*InlineAnnotation\b", text)),
        "classical_locator_comment_count": (
            sum(
                1 for line in lines for match in re.finditer(r"<!--(.*?)-->", line)
                if ":" not in match.group(1)
                and _is_probable_classical_locator(match.group(1).strip())
                and CLASSICAL_LOCATOR_RE.fullmatch(_locator_candidate(match.group(1).strip()))
            )
            if validate_classical_locators else 0
        ),
    }
    return {
        "source_path": source_path,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics,
    }


def evaluate_scholarly_markdown_files(
    paths: list[str | Path],
    *,
    validate_classical_locators: bool = False,
) -> dict[str, Any]:
    results = []
    for path in paths:
        markdown_path = Path(path)
        results.append(
            evaluate_scholarly_markdown_text(
                markdown_path.read_text(encoding="utf-8"),
                source_path=str(markdown_path),
                validate_classical_locators=validate_classical_locators,
            )
        )
    return {
        "ok": all(result["ok"] for result in results),
        "case_count": len(results),
        "results": results,
    }


def _anchors(text: str) -> list[int]:
    values = [int(match.group(1)) for match in re.finditer(r"(?m)^\{(\d+)\}\s*$", text)]
    return values


def _is_probable_classical_locator(body: str) -> bool:
    """Avoid treating untyped prose and dates as locator comments."""
    if DATE_COMMENT_RE.fullmatch(body.strip()):
        return False
    return bool(
        PROBABLE_BEKKER_LOCATOR_RE.match(body)
        or PROBABLE_BRACKET_LOCATOR_RE.match(body)
        or PROBABLE_NUMERIC_LOCATOR_RE.match(body)
    )


def _locator_candidate(body: str) -> str:
    """Remove the optional truncation marks used by generated locator comments."""
    return body.strip().removeprefix("…").removesuffix("…").strip()
