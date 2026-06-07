"""
VLM 版面识别提示词 - Surya 对齐版

严格对齐 Surya 的标签集、块类型定义和识别行为。
"""

# Surya 对齐版 - 现代出版物
SURYA_ALIGNED_MODERN_PROMPT = """Analyze this document page and identify all layout regions. Your output must match Surya layout detection conventions.

## Output Format

Return JSON in this EXACT format:
{"regions": [{"label": "Text", "polygon": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]], "confidence": 0.95}, ...]}

## Supported Labels (Surya Standard)

Use EXACTLY these labels (case-sensitive):
Text, Caption, Code, Figure, Footnote, Form, Equation, Handwriting, TextInlineMath, ListItem, PageFooter, PageHeader, Picture, SectionHeader, Table, TableOfContents, ComplexRegion

DO NOT use variations like "Footer", "Header", "Image", "Paragraph" - use the exact names above.

## Block Type Definitions (Surya Conventions)

### Footnote - CRITICAL
**Surya Definition**: Annotation text at page bottom with numbered markers.

**Characteristics**:
- Location: Bottom 10-25% of page (ABOVE PageFooter)
- Font size: 60-80% of Text size (noticeably smaller)
- Markers: MUST have <sup>1</sup>, <sup>2</sup>, [1], [2], ①, ②, or *
- Separation: Horizontal line or whitespace from main Text
- Content: Annotation/citation text (multiple lines possible)

**vs PageFooter**: Footnote has annotation content + markers; PageFooter is just page numbers
**vs Text**: Footnote is smaller, at bottom, has markers

**Decision Rule**: Has numbered markers + smaller text + bottom location = Footnote

### PageFooter
**Surya Definition**: Page numbers and brief metadata at absolute bottom margin.

**Characteristics**:
- Location: Bottom 0-5% of page (absolute bottom edge)
- Content: Page numbers, copyright (brief, 1-2 lines max)
- Font size: Small
- Position: Usually centered or at corners
- NO numbered annotation markers

**vs Footnote**: PageFooter is just page numbers; Footnote has annotation content

### PageHeader
**Surya Definition**: Chapter titles, book name, page numbers at top margin.

**Characteristics**:
- Location: Top 0-5% of page (absolute top edge)
- Content: Chapter/section titles, book name, page numbers
- Font size: Small
- Usually centered or at corners

### Text
**Surya Definition**: Main body content.

**Characteristics**:
- Location: Main body area (middle 60-80% of page)
- Font size: Standard (baseline)
- Alignment: Justified or left-aligned
- NO numbered markers at start

**vs Footnote**: Text is standard size, in main area, no markers

### SectionHeader
**Surya Definition**: Chapter/section titles.

**Characteristics**:
- Font size: 120-150% of Text size (larger)
- Font weight: Bold
- May have numbering (1., 1.1, etc.)

### Caption
**Surya Definition**: Figure/Table titles.

**Characteristics**:
- Location: Directly above/below Figure/Table
- Format: "Figure X:", "Table X:", "Fig. X:"
- Font size: 80-90% of Text size

### ListItem
**Surya Definition**: Bulleted or numbered list items.

**Characteristics**:
- Markers: •, -, *, 1., 2., a), etc.
- Indentation: Indented from left margin
- Hanging indent style

### Table
**Surya Definition**: Structured data in rows and columns.

**Characteristics**:
- Grid structure with cells
- Borders (visible or implied)
- Header row often bold

### Figure/Picture
**Surya Definition**: Non-text visual content.

**Characteristics**:
- Charts, diagrams, photos, illustrations
- May have Caption nearby

### Equation
**Surya Definition**: Mathematical notation.

**Characteristics**:
- Math symbols and notation
- Display (centered) or inline
- May have equation numbers

### Code
**Surya Definition**: Programming code or pseudocode.

**Characteristics**:
- Monospace font
- Indentation structure
- Syntax patterns

### ComplexRegion
**Surya Definition**: Mixed or complex content.

**Characteristics**:
- Multiple content types mixed
- Difficult to classify as single type

## Recognition Rules (Surya Behavior)

### Priority Order
1. Identify PageHeader (top 0-5%)
2. Identify PageFooter (bottom 0-5%)
3. Identify Footnote (bottom 10-25%, has markers)
4. Identify main content (Text, SectionHeader, etc.)
5. Identify figures, tables, equations

### Size-Based Classification
- Footnote: 60-80% of Text size
- PageHeader/PageFooter: 70-90% of Text size
- SectionHeader: 120-150% of Text size
- Caption: 80-90% of Text size

### Position-Based Classification
- Top 0-5%: PageHeader
- Bottom 0-5%: PageFooter
- Bottom 10-25% with markers: Footnote
- Middle area: Text, SectionHeader, etc.

### Marker-Based Classification
- Has <sup>number</sup> or [number] at bottom: Footnote
- Has "Figure X:" or "Table X:": Caption
- Has bullet or number prefix: ListItem

### Critical Distinctions

**Footnote vs PageFooter**:
```
Footnote:
- Has annotation content (multiple lines)
- Has numbered markers (<sup>1</sup>, [1])
- Location: bottom 10-25%

PageFooter:
- Just page numbers (1-2 lines)
- No annotation markers
- Location: bottom 0-5% (absolute edge)

Rule: If has markers + annotation = Footnote; if just page number = PageFooter
```

**Footnote vs Text**:
```
Footnote:
- Font size: 60-80% of Text
- Location: bottom area
- Has markers

Text:
- Font size: 100% (baseline)
- Location: main body
- No markers

Rule: If smaller + bottom + markers = Footnote; otherwise = Text
```

## Reading Order (Surya Convention)

Order regions top-to-bottom, left-to-right:
1. PageHeader (if present)
2. Main content (top to bottom)
   - For multi-column: left column first, then right column
3. Footnote (if present)
4. PageFooter (if present)

Assign position starting from 0.

## Bounding Boxes (Surya Standard)

- Format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] (top-left, top-right, bottom-right, bottom-left)
- Coordinates: Pixel coordinates relative to image
- Fit: Tightly fit content (minimal padding)
- Overlap: Avoid overlaps unless necessary

## Confidence Scores (Surya Format)

Provide confidence in top_k format:
```json
{
  "label": "Footnote",
  "confidence": 0.95
}
```

If uncertain, use lower confidence (0.7-0.8).

## Important Notes

- Use EXACT label names from Surya standard
- Follow Surya's block type definitions strictly
- Pay special attention to Footnote vs PageFooter vs Text
- Provide tight bounding boxes
- Order by reading order
- When in doubt, prefer Text over Footnote (Surya is conservative)
"""

# Surya 对齐版 - 学术论文
SURYA_ALIGNED_ACADEMIC_PROMPT = """Analyze this academic paper page and identify all layout regions. Your output must match Surya layout detection conventions for academic documents.

## Output Format

Return JSON in this EXACT format:
{"regions": [{"label": "Text", "polygon": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]], "confidence": 0.95}, ...]}

## Supported Labels (Surya Standard)

Use EXACTLY these labels:
Text, Caption, Code, Figure, Footnote, Form, Equation, Handwriting, TextInlineMath, ListItem, PageFooter, PageHeader, Picture, SectionHeader, Table, TableOfContents, ComplexRegion

## Academic Paper Specifics (Surya Behavior)

### Footnote - CRITICAL FOR ACADEMIC PAPERS
**Academic papers often have dense footnotes**

**Characteristics**:
- Location: Bottom 15-30% of page (more space than regular documents)
- Font size: 60-75% of Text size (smaller than modern publications)
- Markers: Sequential numbering (<sup>1</sup>, <sup>2</sup>, <sup>3</sup>, ...)
- Separation: Thin horizontal line
- Content: Citations, references, explanatory notes
- May span multiple lines per footnote

**vs References**: References are at document end; Footnotes are at page bottom

### Multi-Column Layout
Academic papers often use 2-column layout:
- Process left column first (top to bottom)
- Then right column (top to bottom)
- Figures/Tables may span both columns

### Equation
**Display equations**:
- Centered on page
- May have equation numbers (right-aligned)
- Separate block

**Inline equations**:
- Part of Text block (use TextInlineMath if distinguishable)

### Caption
**Academic format**:
- "Figure X:", "Table X:", "Fig. X:"
- May include detailed description
- Above or below Figure/Table

### SectionHeader
**Academic sections**:
- Numbered: 1., 1.1, 1.1.1
- Standard sections: Abstract, Introduction, Methods, Results, Discussion, Conclusion
- Bold, larger than Text

## Recognition Rules for Academic Papers

### Priority Order
1. PageHeader (journal name, paper title)
2. Abstract (if present)
3. SectionHeader
4. Main Text (column-by-column)
5. Equations (display)
6. Figures/Tables with Captions
7. Footnotes (bottom area with markers)
8. PageFooter (page numbers)

### Footnote Density
- Academic papers may have 20-30% of page as footnotes
- Carefully separate from main Text
- Each footnote starts with marker

### Critical: Footnote vs PageFooter in Academic Papers
```
Footnote:
- Multiple lines of citation/annotation
- Numbered markers
- Bottom 15-30%

PageFooter:
- Just page number
- May include journal name
- Bottom 0-5%

Rule: If has citations/annotations = Footnote; if just page number = PageFooter
```

## Important for Academic Papers

- Footnotes are VERY common - identify carefully
- Multi-column layout requires column-aware ordering
- Equations are important - don't miss them
- Caption-Figure/Table relationships are critical
- Use exact Surya label names
"""

# 导出函数
def get_surya_aligned_prompt(template_name: str = "modern") -> str:
    """
    获取 Surya 对齐版提示词。

    Args:
        template_name: 模板名称
            - modern: 现代出版物
            - academic: 学术论文

    Returns:
        提示词字符串
    """
    templates = {
        "modern": SURYA_ALIGNED_MODERN_PROMPT,
        "academic": SURYA_ALIGNED_ACADEMIC_PROMPT,
    }
    return templates.get(template_name, SURYA_ALIGNED_MODERN_PROMPT)
