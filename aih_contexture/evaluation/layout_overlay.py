from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont


TYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "Text": (43, 103, 210),
    "SectionHeader": (126, 60, 181),
    "PageHeader": (40, 143, 108),
    "PageFooter": (40, 143, 108),
    "Footnote": (214, 105, 31),
    "MarginalNote": (196, 68, 120),
    "Reference": (78, 121, 86),
    "Caption": (91, 112, 122),
    "Figure": (26, 130, 153),
    "Picture": (26, 130, 153),
    "Table": (160, 83, 45),
    "Equation": (187, 61, 58),
    "ListItem": (82, 113, 255),
    "Code": (70, 70, 70),
    "ComplexRegion": (120, 120, 120),
}
DEFAULT_COLOR = (80, 80, 80)
SPAN_COLOR = (210, 73, 60)


def render_middle_layout_overlay(
    middle: dict[str, Any],
    *,
    source_pdf: str | Path | None = None,
    output_dir: str | Path,
    output_pdf: str | Path | None = None,
    dpi: int = 96,
    max_label_chars: int = 42,
) -> dict[str, Any]:
    """Render bbox overlays from Contexture Middle JSON.

    This is an inspection artifact. It does not alter Middle JSON or Markdown.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    page_images = _load_page_images(middle, source_pdf=source_pdf, dpi=dpi)
    font = ImageFont.load_default()
    outputs: list[str] = []
    pdf_frames: list[Image.Image] = []

    for page_pos, page in enumerate(middle.get("pages") or []):
        if not isinstance(page, dict):
            continue
        page_index = int(page.get("index", page_pos))
        image = page_images.get(page_index) or _blank_page_image(page, dpi=dpi)
        image = image.convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        _draw_page_overlay(
            draw,
            image=image,
            page=page,
            font=font,
            max_label_chars=max_label_chars,
        )
        page_path = output_path / f"page_{page_index:04d}_layout_overlay.png"
        image.save(page_path)
        outputs.append(str(page_path))
        pdf_frames.append(image)

    pdf_path = None
    if output_pdf and pdf_frames:
        pdf_path = Path(output_pdf)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        first, rest = pdf_frames[0], pdf_frames[1:]
        first.save(pdf_path, save_all=True, append_images=rest)

    return {
        "ok": bool(outputs),
        "page_count": len(outputs),
        "images": outputs,
        "pdf": str(pdf_path) if pdf_path else None,
    }


def render_middle_layout_overlay_file(
    middle_json_path: str | Path,
    *,
    source_pdf: str | Path | None = None,
    output_dir: str | Path,
    output_pdf: str | Path | None = None,
    dpi: int = 96,
    max_label_chars: int = 42,
) -> dict[str, Any]:
    middle_path = Path(middle_json_path)
    middle = json.loads(middle_path.read_text(encoding="utf-8"))
    if source_pdf is None:
        source_pdf = _source_pdf_from_middle(middle, base_dir=middle_path.parent)
    return render_middle_layout_overlay(
        middle,
        source_pdf=source_pdf,
        output_dir=output_dir,
        output_pdf=output_pdf,
        dpi=dpi,
        max_label_chars=max_label_chars,
    )


def render_middle_span_overlay(
    middle: dict[str, Any],
    *,
    source_pdf: str | Path | None = None,
    output_dir: str | Path,
    output_pdf: str | Path | None = None,
    dpi: int = 96,
    max_label_chars: int = 32,
) -> dict[str, Any]:
    """Render span bbox overlays from Contexture Middle JSON."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    page_images = _load_page_images(middle, source_pdf=source_pdf, dpi=dpi)
    font = ImageFont.load_default()
    outputs: list[str] = []
    pdf_frames: list[Image.Image] = []
    span_count = 0

    for page_pos, page in enumerate(middle.get("pages") or []):
        if not isinstance(page, dict):
            continue
        page_index = int(page.get("index", page_pos))
        image = page_images.get(page_index) or _blank_page_image(page, dpi=dpi)
        image = image.convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        span_count += _draw_span_overlay(
            draw,
            image=image,
            page=page,
            font=font,
            max_label_chars=max_label_chars,
        )
        page_path = output_path / f"page_{page_index:04d}_span_overlay.png"
        image.save(page_path)
        outputs.append(str(page_path))
        pdf_frames.append(image)

    pdf_path = None
    if output_pdf and pdf_frames:
        pdf_path = Path(output_pdf)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        first, rest = pdf_frames[0], pdf_frames[1:]
        first.save(pdf_path, save_all=True, append_images=rest)

    return {
        "ok": bool(outputs),
        "page_count": len(outputs),
        "span_count": span_count,
        "images": outputs,
        "pdf": str(pdf_path) if pdf_path else None,
    }


def render_middle_span_overlay_file(
    middle_json_path: str | Path,
    *,
    source_pdf: str | Path | None = None,
    output_dir: str | Path,
    output_pdf: str | Path | None = None,
    dpi: int = 96,
    max_label_chars: int = 32,
) -> dict[str, Any]:
    middle_path = Path(middle_json_path)
    middle = json.loads(middle_path.read_text(encoding="utf-8"))
    if source_pdf is None:
        source_pdf = _source_pdf_from_middle(middle, base_dir=middle_path.parent)
    return render_middle_span_overlay(
        middle,
        source_pdf=source_pdf,
        output_dir=output_dir,
        output_pdf=output_pdf,
        dpi=dpi,
        max_label_chars=max_label_chars,
    )


def render_middle_review_crops(
    middle: dict[str, Any],
    *,
    source_pdf: str | Path | None = None,
    output_dir: str | Path,
    dpi: int = 144,
    padding: int = 24,
    target: str = "small_empty_complex",
) -> dict[str, Any]:
    """Crop review candidate regions from Contexture Middle JSON.

    The default target mirrors the lightweight layout evaluator: small empty
    ComplexRegion blocks are suspicious enough to inspect, but not enough to
    justify a global label remap.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    page_images = _load_page_images(middle, source_pdf=source_pdf, dpi=dpi)
    outputs: list[dict[str, Any]] = []

    for page_pos, page in enumerate(middle.get("pages") or []):
        if not isinstance(page, dict):
            continue
        page_index = int(page.get("index", page_pos))
        image = (page_images.get(page_index) or _blank_page_image(page, dpi=dpi)).convert("RGB")
        page_width = float(page.get("width") or image.size[0])
        page_height = float(page.get("height") or image.size[1])
        scale_x = image.size[0] / page_width if page_width else 1.0
        scale_y = image.size[1] / page_height if page_height else 1.0
        page_area = page_width * page_height if page_width > 0 and page_height > 0 else None

        for block_pos, block in enumerate(page.get("blocks") or []):
            if not isinstance(block, dict) or not _matches_review_target(block, page_area, target=target):
                continue
            bbox = block.get("bbox")
            if not _valid_bbox(bbox):
                continue
            x0, y0, x1, y1 = _scale_bbox(bbox, scale_x, scale_y)
            crop_box = _padded_crop_box((x0, y0, x1, y1), image.size, padding=padding)
            crop = image.crop(crop_box)
            draw = ImageDraw.Draw(crop, "RGBA")
            local_box = (x0 - crop_box[0], y0 - crop_box[1], x1 - crop_box[0], y1 - crop_box[1])
            color = TYPE_COLORS.get(str(block.get("type") or ""), DEFAULT_COLOR)
            draw.rectangle(local_box, outline=(*color, 235), width=3)
            crop_name = f"page_{page_index:04d}_block_{block_pos:04d}_{_safe_name(block.get('type'))}_review.png"
            crop_path = output_path / crop_name
            crop.save(crop_path)
            outputs.append(
                {
                    "path": str(crop_path),
                    "page_index": page_index,
                    "block_index": block_pos,
                    "block_id": block.get("id"),
                    "type": block.get("type"),
                    "bbox": bbox,
                    "raw_label": (block.get("attrs") or {}).get("raw_label") if isinstance(block.get("attrs"), dict) else None,
                    "target": target,
                }
            )

    manifest_path = output_path / "review_crops.json"
    payload = {
        "ok": True,
        "target": target,
        "crop_count": len(outputs),
        "crops": outputs,
        "manifest": str(manifest_path),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def render_middle_review_crops_file(
    middle_json_path: str | Path,
    *,
    source_pdf: str | Path | None = None,
    output_dir: str | Path,
    dpi: int = 144,
    padding: int = 24,
    target: str = "small_empty_complex",
) -> dict[str, Any]:
    middle_path = Path(middle_json_path)
    middle = json.loads(middle_path.read_text(encoding="utf-8"))
    if source_pdf is None:
        source_pdf = _source_pdf_from_middle(middle, base_dir=middle_path.parent)
    return render_middle_review_crops(
        middle,
        source_pdf=source_pdf,
        output_dir=output_dir,
        dpi=dpi,
        padding=padding,
        target=target,
    )


def _load_page_images(
    middle: dict[str, Any],
    *,
    source_pdf: str | Path | None,
    dpi: int,
) -> dict[int, Image.Image]:
    if not source_pdf:
        return {}
    source_path = Path(source_pdf)
    if not source_path.exists():
        return {}
    page_indices = [
        int(page.get("index", pos))
        for pos, page in enumerate(middle.get("pages") or [])
        if isinstance(page, dict)
    ]
    if not page_indices:
        return {}
    try:
        images = _render_pdf_pages(source_path, page_indices, dpi=dpi)
    except Exception:
        return {}
    return dict(zip(page_indices, images))


def _render_pdf_pages(source_path: Path, page_indices: list[int], *, dpi: int) -> list[Image.Image]:
    doc = pdfium.PdfDocument(str(source_path))
    try:
        images = []
        for page_index in page_indices:
            page = doc[page_index]
            image = page.render(scale=dpi / 72, draw_annots=False).to_pil()
            images.append(image.convert("RGB"))
        return images
    finally:
        doc.close()


def _source_pdf_from_middle(middle: dict[str, Any], *, base_dir: Path) -> Path | None:
    source = middle.get("source_name")
    if not source:
        return None
    path = Path(str(source))
    if path.exists():
        return path
    candidate = base_dir / path
    if candidate.exists():
        return candidate
    return None


def _blank_page_image(page: dict[str, Any], *, dpi: int) -> Image.Image:
    width = float(page.get("width") or 612)
    height = float(page.get("height") or 792)
    scale = dpi / 72
    return Image.new("RGB", (max(1, int(width * scale)), max(1, int(height * scale))), "white")


def _draw_page_overlay(
    draw: ImageDraw.ImageDraw,
    *,
    image: Image.Image,
    page: dict[str, Any],
    font: ImageFont.ImageFont,
    max_label_chars: int,
) -> None:
    page_width = float(page.get("width") or image.size[0])
    page_height = float(page.get("height") or image.size[1])
    scale_x = image.size[0] / page_width if page_width else 1.0
    scale_y = image.size[1] / page_height if page_height else 1.0

    for block_pos, block in enumerate(page.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        bbox = block.get("bbox")
        if not _valid_bbox(bbox):
            continue
        block_type = str(block.get("type") or "Unknown")
        color = TYPE_COLORS.get(block_type, DEFAULT_COLOR)
        x0, y0, x1, y1 = _scale_bbox(bbox, scale_x, scale_y)
        draw.rectangle((x0, y0, x1, y1), outline=(*color, 230), width=3)
        draw.rectangle((x0, y0, x1, y1), fill=(*color, 26))

        order = block.get("order", block_pos)
        confidence = block.get("confidence")
        label = f"{order}:{block_type}"
        if confidence is not None:
            label += f" {float(confidence):.2f}"
        raw_label = str((block.get("attrs") or {}).get("raw_label") or "").strip()
        if raw_label and raw_label != block_type:
            label += f" [{raw_label}]"
        if len(label) > max_label_chars:
            label = label[: max_label_chars - 3] + "..."
        _draw_label(draw, label, x0, y0, font=font, color=color)


def _draw_label(
    draw: ImageDraw.ImageDraw,
    label: str,
    x: float,
    y: float,
    *,
    font: ImageFont.ImageFont,
    color: tuple[int, int, int],
) -> None:
    left = int(max(0, x))
    top = int(max(0, y - 14))
    bbox = draw.textbbox((left, top), label, font=font)
    pad = 2
    draw.rectangle(
        (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
        fill=(*color, 218),
    )
    draw.text((left, top), label, fill=(255, 255, 255, 255), font=font)


def _draw_span_overlay(
    draw: ImageDraw.ImageDraw,
    *,
    image: Image.Image,
    page: dict[str, Any],
    font: ImageFont.ImageFont,
    max_label_chars: int,
) -> int:
    page_width = float(page.get("width") or image.size[0])
    page_height = float(page.get("height") or image.size[1])
    scale_x = image.size[0] / page_width if page_width else 1.0
    scale_y = image.size[1] / page_height if page_height else 1.0
    span_count = 0

    for block in page.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        for span_pos, span in enumerate(block.get("spans") or []):
            if not isinstance(span, dict):
                continue
            bbox = span.get("bbox")
            if not _valid_bbox(bbox):
                continue
            x0, y0, x1, y1 = _scale_bbox(bbox, scale_x, scale_y)
            draw.rectangle((x0, y0, x1, y1), outline=(*SPAN_COLOR, 235), width=2)
            draw.rectangle((x0, y0, x1, y1), fill=(*SPAN_COLOR, 20))
            label = _span_label(span, span_pos, max_label_chars=max_label_chars)
            _draw_label(draw, label, x0, y0, font=font, color=SPAN_COLOR)
            span_count += 1
    return span_count


def _span_label(span: dict[str, Any], span_pos: int, *, max_label_chars: int) -> str:
    text = " ".join(str(span.get("text") or "").split())
    if text:
        label = f"{span_pos}:{text}"
    else:
        label = f"{span_pos}:Span"
    if len(label) > max_label_chars:
        label = label[: max_label_chars - 3] + "..."
    return label


def _valid_bbox(value: Any) -> bool:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return False
    try:
        x0, y0, x1, y1 = [float(v) for v in value]
    except (TypeError, ValueError):
        return False
    return x1 > x0 and y1 > y0


def _scale_bbox(bbox: list[Any] | tuple[Any, ...], scale_x: float, scale_y: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = [float(v) for v in bbox]
    return x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y


def _matches_review_target(block: dict[str, Any], page_area: float | None, *, target: str) -> bool:
    block_type = str(block.get("type") or "")
    if target == "all":
        return True
    if target == "complex":
        return block_type == "ComplexRegion"
    if target == "empty_complex":
        return block_type == "ComplexRegion" and _is_empty_block(block)
    if target == "small_empty_complex":
        return block_type == "ComplexRegion" and _is_empty_block(block) and _is_small_block(block, page_area)
    return False


def _is_empty_block(block: dict[str, Any]) -> bool:
    if str(block.get("text") or "").strip():
        return False
    for span in block.get("spans") or []:
        if isinstance(span, dict) and str(span.get("text") or "").strip():
            return False
    return True


def _is_small_block(block: dict[str, Any], page_area: float | None) -> bool:
    bbox = block.get("bbox")
    if not _valid_bbox(bbox) or page_area is None or page_area <= 0:
        return False
    x0, y0, x1, y1 = [float(v) for v in bbox]
    return ((x1 - x0) * (y1 - y0) / page_area) <= 0.01


def _padded_crop_box(
    bbox: tuple[float, float, float, float],
    image_size: tuple[int, int],
    *,
    padding: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    width, height = image_size
    return (
        max(0, int(x0) - padding),
        max(0, int(y0) - padding),
        min(width, int(x1) + padding),
        min(height, int(y1) + padding),
    )


def _safe_name(value: Any) -> str:
    text = str(value or "block")
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in text)
    return safe or "block"
