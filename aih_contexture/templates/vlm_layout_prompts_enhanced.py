"""
VLM 版面识别提示词模板 - 增强版

针对不同文档类型提供优化的提示词模板，包含详细的块类型规范。
"""

# 现代出版物（增强版）
MODERN_LAYOUT_PROMPT_ENHANCED = """Analyze this modern document page and identify all layout regions with precise block type classification.

## Output Format

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]], "confidence": 0.95}, ...]}

Where:
- label: Block type (see detailed specifications below)
- polygon: Bounding box as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates (top-left, top-right, bottom-right, bottom-left)
- confidence: Score between 0.0 and 1.0

## Block Type Specifications

### Footnote (脚注) - IMPORTANT
**Visual Characteristics**:
- Location: Bottom 10-20% of page
- Font size: 70-80% of main text size (noticeably smaller)
- Markers: Has numbering (<sup>1</sup>, [1], ①, *)
- Separation: Separated from main text by horizontal line or significant whitespace
- Alignment: Usually left-aligned, may have indentation

**Key Distinctions**:
- vs Text: Smaller font, bottom location, has markers
- vs PageFooter: Footnote has annotation content with markers; PageFooter has page numbers/metadata
- vs Caption: Caption is near figures/tables; Footnote is at page bottom

### PageHeader (页眉)
**Visual Characteristics**:
- Location: Top 5-10% of page
- Content: Chapter titles, book name, page numbers
- Font size: Usually smaller than main text
- Separation: May have underline or whitespace

### PageFooter (页脚)
**Visual Characteristics**:
- Location: Bottom 5-10% of page (ABOVE footnotes if present)
- Content: Page numbers, copyright info (brief metadata)
- Font size: Usually smaller than main text
- Separation: May have overline or whitespace

**Key Distinction from Footnote**:
- PageFooter: Brief page numbers/metadata
- Footnote: Longer annotation content with numbered markers

### Text (正文)
**Visual Characteristics**:
- Location: Main body area of page
- Font size: Standard size (baseline)
- Alignment: Justified or left-aligned
- Line spacing: Standard

### SectionHeader (章节标题)
**Visual Characteristics**:
- Font size: Larger than main text
- Font weight: Bold
- Location: Beginning of section or standalone line
- Numbering: May have section numbers

### Caption (图表标题)
**Visual Characteristics**:
- Location: Directly above or below Figure/Table
- Content: "Figure X:", "Table X:", "图 X:", "表 X:"
- Font size: Usually smaller than main text

### ListItem (列表项)
**Visual Characteristics**:
- Markers: Bullets (•, -, *) or numbers (1., 2., 3.)
- Indentation: Indented from left margin
- Alignment: Hanging indent

### Table (表格)
**Visual Characteristics**:
- Grid structure with rows and columns
- Cell borders (visible or implied)
- Structured data layout

### Figure/Picture (图形/图片)
**Visual Characteristics**:
- Non-text visual content
- May include charts, diagrams, photos
- Usually has Caption nearby

### Equation (公式)
**Visual Characteristics**:
- Mathematical notation
- May be inline or display (centered)
- Special symbols and formatting

### Code (代码)
**Visual Characteristics**:
- Monospace font
- Syntax highlighting or plain text
- Indentation structure

## Recognition Rules

1. **Priority Order**:
   - First identify PageHeader and PageFooter (top/bottom margins)
   - Then identify Footnotes (bottom area with markers)
   - Then identify main content (Text, SectionHeader, etc.)

2. **Size-Based Classification**:
   - Footnote: 70-80% of Text size
   - PageHeader/PageFooter: 80-90% of Text size
   - SectionHeader: 120-150% of Text size

3. **Position-Based Classification**:
   - Top 5-10%: Likely PageHeader
   - Bottom 5-10%: Likely PageFooter
   - Bottom 10-20%: Likely Footnote (if has markers)
   - Middle area: Text, SectionHeader, etc.

4. **Marker-Based Classification**:
   - Has <sup>number</sup> or [number]: Likely Footnote
   - Has "Figure X:" or "Table X:": Likely Caption
   - Has bullet or number prefix: Likely ListItem

5. **Separation Rules**:
   - Footnotes are separated from Text by line or whitespace
   - PageHeader/PageFooter are in margin areas
   - Captions are adjacent to Figure/Table

## Important Notes

- Detect ALL visible regions on the page
- Use precise bounding boxes that tightly fit each region
- Order regions by reading order (top-to-bottom, left-to-right)
- Do NOT overlap regions unless necessary
- Pay special attention to distinguishing Footnote from Text and PageFooter
- If uncertain between Footnote and Text, check: location (bottom?), size (smaller?), markers (has numbering?)
"""

# 学术论文（增强版）
ACADEMIC_PAPER_PROMPT_ENHANCED = """Analyze this academic/scientific paper page and identify all layout regions with precise block type classification.

## Output Format

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]], "confidence": 0.95}, ...]}

## Block Type Specifications

### Footnote (脚注) - CRITICAL FOR ACADEMIC PAPERS
**Visual Characteristics**:
- Location: Bottom 15-25% of page (academic papers often have dense footnotes)
- Font size: 60-75% of main text size (smaller than modern publications)
- Markers: Numbered sequentially (<sup>1</sup>, <sup>2</sup>, <sup>3</sup>, ...)
- Separation: Horizontal line (often thin) separating from main text
- Content: Citations, explanatory notes, references

**Academic-Specific Features**:
- May span multiple lines
- May contain citations in specific formats (Author, Year)
- Numbering continues across pages

### References (参考文献)
**Visual Characteristics**:
- Location: End of document or bottom of page
- Format: [1], [2], [3] or numbered list
- Content: Author names, publication info
- Font size: Similar to or smaller than main text

### Equation (公式) - IMPORTANT
**Visual Characteristics**:
- Mathematical notation with special symbols
- Display equations: Centered, may have equation numbers
- Inline equations: Within text flow
- May use LaTeX-style formatting

### Caption (图表标题) - IMPORTANT
**Visual Characteristics**:
- Format: "Figure X:", "Table X:", "Fig. X:"
- Location: Above or below Figure/Table
- Font size: Smaller than main text
- May include detailed description

### Table (表格) - IMPORTANT
**Visual Characteristics**:
- Grid structure with clear rows and columns
- Header row often bold or shaded
- Data cells with numerical or text content
- May have borders or gridlines

### Figure (图形) - IMPORTANT
**Visual Characteristics**:
- Charts, graphs, diagrams, plots
- May include axes, legends, labels
- Scientific visualizations

### SectionHeader (章节标题)
**Academic-Specific**:
- Numbered sections (1., 1.1, 1.1.1)
- Standard sections: Abstract, Introduction, Methods, Results, Discussion, Conclusion
- Font: Bold, larger than text

### Abstract (摘要)
**Visual Characteristics**:
- Location: Beginning of paper
- Label: "Abstract" or "摘要"
- Font: May be italicized or smaller
- Single paragraph or structured

## Recognition Rules for Academic Papers

1. **Multi-Column Layout**:
   - Many academic papers use 2-column layout
   - Process column-by-column (left to right)
   - Figures/Tables may span columns

2. **Footnote Density**:
   - Academic papers often have many footnotes
   - Footnotes may occupy 20-30% of page
   - Carefully separate from main text

3. **Equation Handling**:
   - Display equations: Separate blocks, centered
   - Inline equations: Part of Text block
   - Equation numbers: Usually right-aligned

4. **Citation Markers**:
   - In-text citations: [1], (Author, Year)
   - Footnote markers: <sup>1</sup>, <sup>2</sup>
   - Reference numbers: [1], [2]

5. **Figure/Table Placement**:
   - May be at top or bottom of page
   - Caption always adjacent to Figure/Table
   - May have "continued" notation

## Important Notes

- Academic papers have complex structure - be precise
- Footnotes are CRITICAL - distinguish carefully from Text and PageFooter
- Multi-column layout requires column-aware ordering
- Equations and Figures are important - don't miss them
- Pay attention to Caption-Figure/Table relationships
"""

# 中文古籍（增强版）
CHINESE_ANCIENT_PROMPT_ENHANCED = """识别这页中文古籍的版面布局，精确分类各个区域。

## 输出格式

以 JSON 格式返回：
{"regions": [{"label": "Text", "polygon": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]], "confidence": 0.95}, ...]}

## 块类型详细规范

### Footnote (夹注/小注) - 重要
**视觉特征**:
- 位置: 正文行间或页面边缘
- 字号: 明显小于正文（通常是正文的 50-60%）
- 形式: 双行小字、夹注、眉批
- 标记: 可能有圈点、符号标记

**古籍特有形式**:
- 夹注: 正文行间的小字注释
- 眉批: 页面上方的批注
- 旁批: 页面侧边的批注
- 双行小注: 两行小字的注释

**与其他类型的区别**:
- vs Text: 字号明显更小
- vs PageHeader: PageHeader 是书名、卷标，Footnote 是注释内容

### PageHeader (书眉/卷标)
**视觉特征**:
- 位置: 页面顶部中央或两侧
- 内容: 书名、卷数、篇名
- 字号: 小于正文
- 形式: 可能有鱼尾、象鼻等装饰

### PageFooter (页码/叶码)
**视觉特征**:
- 位置: 页面底部或版心外
- 内容: 页码、叶码（如"一之一"）
- 字号: 小于正文

### Text (正文)
**视觉特征**:
- 位置: 版心内主体区域
- 字号: 标准大小
- 排列: 竖排，从右向左
- 行距: 标准行距

### SectionHeader (章节标题)
**视觉特征**:
- 字号: 可能大于正文或与正文相同
- 位置: 段落开头或独立行
- 标记: 可能有"第X章"、"卷X"等

### Picture (插图)
**古籍特有**:
- 版画、木刻插图
- 可能有图说（标题）
- 位置: 独立页或正文中

### ComplexRegion (复杂区域)
**古籍特有元素**:
- 印章: 藏书印、鉴藏印
- 题跋: 后人题写的文字
- 批注: 读者批注
- 版框: 边框、鱼尾等装饰

## 识别规则

1. **字号判断**:
   - 正文: 标准大小（基准）
   - 夹注/小注: 50-60% 正文大小
   - 书眉/页码: 70-80% 正文大小

2. **位置判断**:
   - 版心内: 正文、夹注
   - 版心外: 书眉、页码、批注
   - 行间: 夹注

3. **排列方向**:
   - 主要内容: 竖排，从右向左
   - 注释: 可能横排或竖排

4. **特殊元素**:
   - 印章: 标记为 Picture 或 ComplexRegion
   - 题跋: 标记为 Footnote 或 ComplexRegion
   - 批注: 标记为 Footnote

## 重要提示

- 识别所有可见区域
- 特别注意区分正文和夹注（字号差异明显）
- 按从右至左、从上到下的阅读顺序排列区域
- 注意识别版心、边框、鱼尾等传统元素
- 夹注是古籍的重要特征，务必准确识别
"""

# 模板字典
ENHANCED_LAYOUT_PROMPT_TEMPLATES = {
    "modern_enhanced": MODERN_LAYOUT_PROMPT_ENHANCED,
    "academic_enhanced": ACADEMIC_PAPER_PROMPT_ENHANCED,
    "chinese_ancient_enhanced": CHINESE_ANCIENT_PROMPT_ENHANCED,
}


def get_enhanced_layout_prompt(template_name: str = "modern_enhanced") -> str:
    """
    获取增强版版面识别提示词模板。

    Args:
        template_name: 模板名称
            - modern_enhanced: 现代出版物（增强版）
            - academic_enhanced: 学术论文（增强版）
            - chinese_ancient_enhanced: 中文古籍（增强版）

    Returns:
        提示词字符串
    """
    return ENHANCED_LAYOUT_PROMPT_TEMPLATES.get(
        template_name,
        MODERN_LAYOUT_PROMPT_ENHANCED
    )
