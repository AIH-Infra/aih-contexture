"""
VLM 版面识别提示词模板

针对不同文档类型提供优化的提示词模板。

版本说明:
- 基础版: 简洁的提示词，适合快速识别
- 增强版: 详细的块类型规范，适合精确识别（推荐用于脚注密集文档）
"""

# 现代出版物（基础版）
MODERN_LAYOUT_PROMPT = """Analyze this modern document page and identify all layout regions.

For each region you detect, provide:
- label: The type of content. Must be one of: Text, SectionHeader, ListItem, Figure, Picture, Table, Equation, Code, Caption, Footnote, PageHeader, PageFooter, Form, Handwriting, TableOfContents, ComplexRegion
- polygon: Bounding box coordinates as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates (top-left, top-right, bottom-right, bottom-left)
- confidence: Confidence score between 0.0 and 1.0

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[0,0], [100,0], [100,50], [0,50]], "confidence": 0.95}, ...]}

Important:
- Detect ALL visible regions on the page
- Use precise bounding boxes that tightly fit each region
- Order regions by reading order (top-to-bottom, left-to-right)
- Do not overlap regions unless necessary
- Focus on modern typography with clear structure
"""

# 中文古籍
CHINESE_ANCIENT_LAYOUT_PROMPT = """识别这页中文古籍的版面布局。

对每个识别到的区域，提供：
- label: 内容类型，必须是以下之一：Text, SectionHeader, ListItem, Figure, Picture, Table, Equation, Code, Caption, Footnote, PageHeader, PageFooter, Form, Handwriting, TableOfContents, ComplexRegion
- polygon: 边界框坐标，格式为 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]（像素坐标）
- confidence: 0.0 到 1.0 之间的置信度

以 JSON 格式返回：
{"regions": [{"label": "Text", "polygon": [[0,0], [100,0], [100,50], [0,50]], "confidence": 0.95}, ...]}

注意：
- 识别所有可见区域
- 古籍特征：竖排文字、从右向左阅读、可能有注释和标记
- 区分正文、书名、注释、插图等
- 边界框应紧贴内容
- 按从右至左、从上到下的阅读顺序排列区域
- 注意识别版心、边框、鱼尾等传统元素
"""

# 哥特体/德文古籍
GOTHIC_GERMAN_LAYOUT_PROMPT = """Analyze this historical German document with Gothic (Fraktur) script and identify all layout regions.

For each region you detect, provide:
- label: The type of content. Must be one of: Text, SectionHeader, ListItem, Figure, Picture, Table, Equation, Code, Caption, Footnote, PageHeader, PageFooter, Form, Handwriting, TableOfContents, ComplexRegion
- polygon: Bounding box coordinates as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates
- confidence: Confidence score between 0.0 and 1.0

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[0,0], [100,0], [100,50], [0,50]], "confidence": 0.95}, ...]}

Important:
- Gothic/Fraktur script has distinctive letter forms (long s, ligatures, etc.)
- Pay attention to decorative initials (drop caps) - mark as Text or SectionHeader
- Identify marginalia and annotations separately
- Historical typography may have irregular baselines and spacing
- Order regions by reading order (top-to-bottom, left-to-right for LTR)
- Be precise with ornamental borders and illustrations
"""

# 档案文件
ARCHIVE_LAYOUT_PROMPT = """Analyze this archival document page (forms, handwritten notes, stamps, seals) and identify all layout regions.

For each region you detect, provide:
- label: The type of content. Must be one of: Text, SectionHeader, ListItem, Figure, Picture, Table, Equation, Code, Caption, Footnote, PageHeader, PageFooter, Form, Handwriting, TableOfContents, ComplexRegion
- polygon: Bounding box coordinates as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates
- confidence: Confidence score between 0.0 and 1.0

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[0,0], [100,0], [100,50], [0,50]], "confidence": 0.95}, ...]}

Important:
- Distinguish between printed text and handwriting (use Handwriting label for handwritten content)
- Identify form fields and structure (use Form label)
- Detect stamps and seals as Picture or ComplexRegion
- Handle mixed orientations (rotated text, marginal notes)
- Account for degradation (fading, stains, tears)
- Order regions by logical reading order, not strictly top-to-bottom
- Be precise about overlapping elements (e.g., handwritten notes on printed forms)
"""

# 表格/表单密集文档
TABLE_FORM_LAYOUT_PROMPT = """Analyze this document page with heavy table and form content, and identify all layout regions.

For each region you detect, provide:
- label: The type of content. Must be one of: Text, SectionHeader, ListItem, Figure, Picture, Table, Equation, Code, Caption, Footnote, PageHeader, PageFooter, Form, Handwriting, TableOfContents, ComplexRegion
- polygon: Bounding box coordinates as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates
- confidence: Confidence score between 0.0 and 1.0

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[0,0], [100,0], [100,50], [0,50]], "confidence": 0.95}, ...]}

Important:
- Carefully distinguish between Table and Form regions
- Table: structured data with rows and columns
- Form: fillable fields with labels/prompts
- Capture entire table/form boundaries accurately
- Separate captions from the table/form body
- Handle nested structures (tables within forms, etc.)
- Order regions by reading order
"""

# 科技论文
SCIENTIFIC_LAYOUT_PROMPT = """Analyze this scientific/technical document page and identify all layout regions.

For each region you detect, provide:
- label: The type of content. Must be one of: Text, SectionHeader, ListItem, Figure, Picture, Table, Equation, Code, Caption, Footnote, PageHeader, PageFooter, Form, Handwriting, TableOfContents, ComplexRegion
- polygon: Bounding box coordinates as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates
- confidence: Confidence score between 0.0 and 1.0

Return your response as JSON in this exact format:
{"regions": [{"label": "Text", "polygon": [[0,0], [100,0], [100,50], [0,50]], "confidence": 0.95}, ...]}

Important:
- Identify mathematical equations (both inline and display)
- Distinguish figures from tables (charts/graphs vs. data tables)
- Separate captions from figures/tables
- Detect code blocks and algorithm pseudocode
- Handle multi-column layouts (scientific papers often use 2 columns)
- Identify footnotes and references carefully
- Order regions by reading order (column-wise for multi-column)
"""

# 模板字典（供程序查询）
LAYOUT_PROMPT_TEMPLATES = {
    "modern": MODERN_LAYOUT_PROMPT,
    "chinese_ancient": CHINESE_ANCIENT_LAYOUT_PROMPT,
    "gothic_german": GOTHIC_GERMAN_LAYOUT_PROMPT,
    "archive": ARCHIVE_LAYOUT_PROMPT,
    "table_form": TABLE_FORM_LAYOUT_PROMPT,
    "scientific": SCIENTIFIC_LAYOUT_PROMPT,
}

# 默认模板
DEFAULT_TEMPLATE = "modern"


def get_layout_prompt(template_name: str = None) -> str:
    """
    获取版面识别提示词模板。

    Args:
        template_name: 模板名称，可选值：
            基础版:
            - modern: 现代出版物（默认）
            - chinese_ancient: 中文古籍
            - gothic_german: 哥特体/德文古籍
            - archive: 档案文件
            - table_form: 表格/表单密集文档
            - scientific: 科技论文

            增强版（推荐用于脚注密集文档）:
            - modern_enhanced: 现代出版物（增强版）
            - academic_enhanced: 学术论文（增强版）
            - chinese_ancient_enhanced: 中文古籍（增强版）

            Surya 对齐版（推荐，与 Surya 行为严格一致）:
            - surya_modern: 现代出版物（Surya 对齐）
            - surya_academic: 学术论文（Surya 对齐）

    Returns:
        提示词字符串
    """
    if template_name is None:
        template_name = DEFAULT_TEMPLATE

    template_name = str(template_name).lower().strip()

    # Surya 对齐版（优先级最高）
    if template_name.startswith("surya_"):
        try:
            from aih_contexture.templates.vlm_layout_prompts_surya_aligned import get_surya_aligned_prompt
            base_name = template_name.replace("surya_", "")
            return get_surya_aligned_prompt(base_name)
        except ImportError:
            # 回退到基础版
            base_name = template_name.replace("surya_", "")
            return LAYOUT_PROMPT_TEMPLATES.get(base_name, MODERN_LAYOUT_PROMPT)

    # 增强版
    if template_name.endswith("_enhanced"):
        try:
            from aih_contexture.templates.vlm_layout_prompts_enhanced import get_enhanced_layout_prompt
            return get_enhanced_layout_prompt(template_name)
        except ImportError:
            # 如果增强模块不可用，回退到基础版
            base_name = template_name.replace("_enhanced", "")
            return LAYOUT_PROMPT_TEMPLATES.get(base_name, MODERN_LAYOUT_PROMPT)

    # 基础版
    return LAYOUT_PROMPT_TEMPLATES.get(template_name, MODERN_LAYOUT_PROMPT)


def list_templates() -> list:
    """列出所有可用的模板名称"""
    return list(LAYOUT_PROMPT_TEMPLATES.keys())
