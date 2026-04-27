"""
Chandra Output Utilities
========================
内化自官方 chandra/output.py，去除外部包依赖。

提供三个核心转换函数：
- parse_html()     : 清理 Chandra 原始 HTML（移除 bbox/label 属性）
- parse_markdown() : 将 Chandra 原始 HTML 转为 Markdown
- parse_chunks()   : 将 Chandra 原始 HTML 转为带坐标的结构化块列表（需要 PIL.Image）

原始来源：datalab-to/chandra chandra/output.py
修改说明：
  - 移除 `from chandra.settings import settings` 依赖
  - BBOX_SCALE 默认值改为 1000（对齐 Chandra 2.0；调用方可覆盖）
  - six.text_type 替换为 str（Python 3 兼容）
  - 移除 extract_images()（项目不需要图片提取）
"""

import hashlib
import json
import re
from dataclasses import dataclass, asdict

from PIL import Image
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter, re_whitespace

BBOX_SCALE = 1000


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _get_image_name(html: str, div_idx: int) -> str:
    html_hash = hashlib.md5(html.encode("utf-8")).hexdigest()
    return f"{html_hash}_{div_idx}_img.webp"


# ---------------------------------------------------------------------------
# parse_html
# ---------------------------------------------------------------------------

def parse_html(
    html: str,
    include_headers_footers: bool = False,
    include_images: bool = True,
    extract_printed_page: bool = False,
):
    """
    清理 Chandra 原始 HTML。

    - 移除顶层 <div> 的 data-bbox / data-label 属性
    - 可选过滤 Page-Header / Page-Footer 块
    - 可选过滤 Image / Figure 块
    - 为纯文本 Text 块补充 <p> 标签
    - 可选提取印刷页码

    Returns:
        如果 extract_printed_page=True: (clean_html, page_number)
        否则: clean_html
    """
    soup = BeautifulSoup(html, "html.parser")
    top_level_divs = soup.find_all("div", recursive=False)
    out_html = ""
    div_idx = 0
    page_number = None

    for div in top_level_divs:
        div_idx += 1
        label = div.get("data-label")

        if label == "Blank-Page":
            continue

        # 提取印刷页码
        if extract_printed_page and label in ["Page-Header", "Page-Footer"]:
            text = div.get_text(strip=True)
            if re.match(r'^\d{1,3}$', text):
                page_number = text
            elif re.match(r'^[ivxIVX]{1,6}$', text):
                page_number = text
            # 提取后跳过该 div，不输出到内容中
            continue

        if label and not include_headers_footers:
            if label in ["Page-Header", "Page-Footer"]:
                continue
        if label and not include_images:
            if label in ["Image", "Figure"]:
                continue

        if label in ["Image", "Figure"]:
            img = div.find("img")
            img_src = _get_image_name(html, div_idx)
            if img:
                img["src"] = img_src
            else:
                new_img = BeautifulSoup(f"<img src='{img_src}'/>", "html.parser")
                div.append(new_img)
        elif label not in ["Image", "Figure"]:
            for img_tag in div.find_all("img"):
                if not img_tag.get("src"):
                    img_tag.decompose()

        # 纯文本块补 <p>
        if label in ["Text"] and not re.search("<.+>", str(div.decode_contents()).strip()):
            text_content = str(div.decode_contents()).strip()
            text_content = f"<p>{text_content}</p>"
            div.clear()
            div.append(BeautifulSoup(text_content, "html.parser"))

        out_html += str(div.decode_contents())

    if extract_printed_page:
        return (out_html, page_number)
    return out_html


# ---------------------------------------------------------------------------
# Markdownify 子类（官方实现，处理数学公式/表格/转义）
# ---------------------------------------------------------------------------

class _Markdownify(MarkdownConverter):
    def __init__(self, inline_math_delimiters, block_math_delimiters, **kwargs):
        super().__init__(**kwargs)
        self.inline_math_delimiters = inline_math_delimiters
        self.block_math_delimiters = block_math_delimiters

    def convert_math(self, el, text, parent_tags):
        block = el.has_attr("display") and el["display"] == "block"
        if block:
            return (
                "\n"
                + self.block_math_delimiters[0]
                + text.strip()
                + self.block_math_delimiters[1]
                + "\n"
            )
        else:
            return (
                " "
                + self.inline_math_delimiters[0]
                + text.strip()
                + self.inline_math_delimiters[1]
                + " "
            )

    def convert_table(self, el, text, parent_tags):
        return "\n\n" + str(el) + "\n\n"

    def convert_a(self, el, text, parent_tags):
        text = self.escape(text)
        text = re.sub(r"([\[\](]])", r"\\\1", text)
        return super().convert_a(el, text, parent_tags)

    def escape(self, text, parent_tags=None):
        text = super().escape(text, parent_tags)
        if self.options["escape_dollars"]:
            text = text.replace("$", r"\$")
        return text

    def process_text(self, el, parent_tags=None):
        # 原官方用 six.text_type(el)，Python 3 直接用 str
        text = str(el) or ""
        if not el.find_parent("pre"):
            text = re_whitespace.sub(" ", text)
        if not el.find_parent(["pre", "code", "kbd", "samp", "math"]):
            text = self.escape(text)
        if el.parent.name == "li" and (
            not el.next_sibling or el.next_sibling.name in ["ul", "ol"]
        ):
            text = text.rstrip()
        return text


# ---------------------------------------------------------------------------
# parse_markdown
# ---------------------------------------------------------------------------

def parse_markdown(
    html: str,
    include_headers_footers: bool = False,
    include_images: bool = True,
    extract_printed_page: bool = False,
):
    """
    将 Chandra 原始 HTML 转为 Markdown。

    先调用 parse_html() 清理，再用 Markdownify 转换。
    数学公式使用 $ / $$ 分隔符。
    可选提取印刷页码并插入到顶部。

    Returns:
        如果 extract_printed_page=True: (markdown, page_number)
        否则: markdown
    """
    result = parse_html(html, include_headers_footers, include_images, extract_printed_page)

    if extract_printed_page:
        clean, page_number = result
    else:
        clean = result
        page_number = None

    md_cls = _Markdownify(
        heading_style="ATX",
        bullets="-",
        escape_misc=False,
        escape_underscores=True,
        escape_asterisks=True,
        escape_dollars=True,
        sub_symbol="<sub>",
        sup_symbol="<sup>",
        inline_math_delimiters=("$", "$"),
        block_math_delimiters=("$$", "$$"),
    )
    try:
        markdown = md_cls.convert(clean)
    except Exception as e:
        markdown = ""

    markdown = markdown.strip()

    # 不在这里插入页码锚点，由 PageAnchorPlugin 统一处理
    # 只返回提取的页码供后续使用

    if extract_printed_page:
        return (markdown, page_number)
    return markdown


# ---------------------------------------------------------------------------
# parse_chunks / parse_layout
# ---------------------------------------------------------------------------

@dataclass
class _LayoutBlock:
    bbox: list
    label: str
    content: str


def parse_layout(
    html: str,
    image: Image.Image,
    bbox_scale: int = BBOX_SCALE,
) -> list:
    """
    解析 Chandra HTML，将 bbox 坐标从归一化空间（0-bbox_scale）映射回像素空间。
    返回 _LayoutBlock 列表。
    """
    soup = BeautifulSoup(html, "html.parser")
    top_level_divs = soup.find_all("div", recursive=False)
    width, height = image.size
    width_scaler = width / bbox_scale
    height_scaler = height / bbox_scale
    layout_blocks = []

    for div in top_level_divs:
        label = div.get("data-label", "block")
        if label == "Blank-Page":
            continue

        bbox = div.get("data-bbox")
        try:
            bbox = json.loads(bbox)
            assert len(bbox) == 4
        except Exception:
            try:
                bbox = bbox.split(" ")
                assert len(bbox) == 4
            except Exception:
                bbox = [0, 0, 1, 1]

        bbox = list(map(int, bbox))
        bbox = [
            max(0, int(bbox[0] * width_scaler)),
            max(0, int(bbox[1] * height_scaler)),
            min(int(bbox[2] * width_scaler), width),
            min(int(bbox[3] * height_scaler), height),
        ]
        content = str(div.decode_contents())
        content_soup = BeautifulSoup(content, "html.parser")
        for tag in content_soup.find_all(attrs={"data-bbox": True}):
            del tag["data-bbox"]
        content = str(content_soup)
        layout_blocks.append(_LayoutBlock(bbox=bbox, label=label, content=content))

    return layout_blocks


def parse_chunks(
    html: str,
    image: Image.Image,
    bbox_scale: int = BBOX_SCALE,
) -> list:
    """
    将 Chandra 原始 HTML 转为结构化块列表（dict）。

    每个块包含：
      - bbox  : [x0, y0, x1, y1]（像素坐标）
      - label : Chandra 标签（如 "Text", "Section-Header", "Table" 等）
      - content: 块内 HTML 内容

    需要传入原始页面 PIL.Image 用于坐标映射。
    """
    layout = parse_layout(html, image, bbox_scale=bbox_scale)
    return [asdict(block) for block in layout]
