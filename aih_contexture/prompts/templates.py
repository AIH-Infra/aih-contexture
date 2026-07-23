"""
Built-in Template Library

Provides 7 pre-configured templates for common document types:
1. ancient_chinese - 中文古籍
2. archive_document - 档案文献
3. modern_publication - 现代出版物（默认）
4. gothic_german - 哥特体德文
5. manuscript - 手稿
6. academic_paper - 学术论文
7. mixed_content - 混合内容
"""

# 语言预设配置（17种语言）
LANGUAGE_PRESETS = {
    "zh-Hans": {
        "code": "zh-Hans",
        "name": "Chinese - Simplified",
        "display_name": "中文(简)",
        "script_direction": "horizontal",
        "special_chars": ["，", "。", "、", "；", "：", "？", "！", "《", "》", "「", "」"],
    },
    "zh-Hant": {
        "code": "zh-Hant",
        "name": "Chinese - Traditional",
        "display_name": "中文(繁)",
        "script_direction": "horizontal",  # or "vertical" for ancient texts
        "special_chars": ["，", "。", "、", "；", "：", "？", "！", "《", "》", "「", "」"],
    },
    "en": {
        "code": "en",
        "name": "English",
        "display_name": "English",
        "script_direction": "horizontal",
        "special_chars": [],
    },
    "enm": {
        "code": "enm",
        "name": "English, Middle",
        "display_name": "English, Middle",
        "script_direction": "horizontal",
        "special_chars": ["þ", "ð", "ȝ"],  # thorn, eth, yogh
    },
    "de-Fraktur": {
        "code": "de-Fraktur",
        "name": "Fraktur",
        "display_name": "Fraktur",
        "script_direction": "horizontal",
        "special_chars": ["ä", "ö", "ü", "ß", "ſ"],  # long s
    },
    "fr": {
        "code": "fr",
        "name": "French",
        "display_name": "Français",
        "script_direction": "horizontal",
        "special_chars": ["à", "â", "é", "è", "ê", "ë", "î", "ï", "ô", "ù", "û", "ü", "ÿ", "ç", "œ", "æ"],
    },
    "frm": {
        "code": "frm",
        "name": "French, Middle",
        "display_name": "Français (Milieu)",
        "script_direction": "horizontal",
        "special_chars": ["à", "â", "é", "è", "ê", "ë", "î", "ï", "ô", "ù", "û", "ü", "ÿ", "ç"],
    },
    "grc": {
        "code": "grc",
        "name": "Greek, Ancient",
        "display_name": "Ελληνικά (Αρχαίος)",
        "script_direction": "horizontal",
        "special_chars": ["ά", "έ", "ή", "ί", "ό", "ύ", "ώ", "ϊ", "ϋ", "ΐ", "ΰ"],
    },
    "el": {
        "code": "el",
        "name": "Greek, Modern",
        "display_name": "Ελληνικά",
        "script_direction": "horizontal",
        "special_chars": ["ά", "έ", "ή", "ί", "ό", "ύ", "ώ", "ϊ", "ϋ", "ΐ", "ΰ"],
    },
    "it": {
        "code": "it",
        "name": "Italian",
        "display_name": "Italiano",
        "script_direction": "horizontal",
        "special_chars": ["à", "è", "é", "ì", "ò", "ù"],
    },
    "it-old": {
        "code": "it-old",
        "name": "Italian - Old",
        "display_name": "Italiano (Antico)",
        "script_direction": "horizontal",
        "special_chars": ["à", "è", "é", "ì", "ò", "ù"],
    },
    "ja": {
        "code": "ja",
        "name": "Japanese",
        "display_name": "日本語",
        "script_direction": "horizontal",  # or "vertical"
        "special_chars": ["、", "。", "「", "」", "『", "』", "・"],
    },
    "ko": {
        "code": "ko",
        "name": "Korean",
        "display_name": "한국어",
        "script_direction": "horizontal",
        "special_chars": ["、", "。", "·"],
    },
    "la": {
        "code": "la",
        "name": "Latin",
        "display_name": "Lingua Latina",
        "script_direction": "horizontal",
        "special_chars": ["æ", "œ"],
    },
    "ru": {
        "code": "ru",
        "name": "Russian",
        "display_name": "Русский",
        "script_direction": "horizontal",
        "special_chars": ["ё", "Ё"],
    },
    "es": {
        "code": "es",
        "name": "Spanish; Castilian",
        "display_name": "Español",
        "script_direction": "horizontal",
        "special_chars": ["á", "é", "í", "ó", "ú", "ü", "ñ", "¿", "¡"],
    },
    "es-old": {
        "code": "es-old",
        "name": "Spanish; Castilian - Old",
        "display_name": "Español (Antiguo)",
        "script_direction": "horizontal",
        "special_chars": ["á", "é", "í", "ó", "ú", "ü", "ñ", "¿", "¡"],
    },
}

# 语言显示名称映射（用于 UI）
LANGUAGE_DISPLAY_NAMES = {
    code: preset["display_name"]
    for code, preset in LANGUAGE_PRESETS.items()
}


# Template 0: 通用模板（推荐 - 最大化利用大模型泛化能力）
UNIVERSAL = {
    "text_direction": "horizontal",
    "may_have_footnotes": True,
    "may_have_references": True,
    "may_have_handwriting": True,
    "handwriting_mode": "mixed",
    "describe_images": True,
    "language_mode": "monolingual",
    "primary_language": "zh",
    "document_era": "modern",
    "may_have_page_numbers": True,
    "may_have_headers_footers": True,
    "special_features": ["handwriting", "stamps", "damage_stains"],
    "temperature": 0.1,
    "top_p": 0.2,
    "max_tokens": 0,  # 不限制
    "custom_instructions": """## 档案文献识别指导

### 混合内容
- 区分印刷体和手写体
- 手写内容标记为 `**[手写]** 内容`

### 公章和签名
- 识别公章内容：`[公章: 单位名称]`
- 识别签名：`[签名: 姓名]` 或 `[签名: 不清]`

### 档案编号识别
如果看到档案编号，输出：`<!-- PageHeader: 档案编号 -->`

### 特殊元素
- 印章：`[印章: 内容]`
- 照片：`[照片: 描述]`
- 污损：`[污损/不清]`"""
}

# Template 1: 中文古籍
ANCIENT_CHINESE = {
    "text_direction": "vertical",
    "may_have_footnotes": True,
    "may_have_references": True,
    "may_have_handwriting": False,
    "language_mode": "monolingual",
    "primary_language": "zh",
    "document_era": "ancient",
    "may_have_page_numbers": True,
    "may_have_headers_footers": False,
    "special_features": ["seal_script", "seals_stamps", "annotations"],
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192,
    "custom_instructions": """## 中文古籍识别指导

### 文本方向
- 竖排文本，从右到左，从上到下阅读
- 保持原有的列顺序

### 字符识别
- 识别繁体字和异体字
- 注意古今字形差异
- 识别通假字（保持原文，不要转换）

### 标点符号
- 古籍可能无标点或使用句读符号（。、，）
- 保持原有标点，不要添加现代标点

### 特殊元素
- 识别夹注和小字注释为脚注
- 识别印章和题跋（标记为 `[印章: 内容]`）
- 识别批注（标记为 `[批注: 内容]`）"""
}

# Template 2: 档案文献
ARCHIVE_DOCUMENT = {
    "text_direction": "horizontal",
    "may_have_footnotes": True,
    "may_have_references": True,
    "may_have_handwriting": True,
    "language_mode": "monolingual",
    "primary_language": "zh",
    "document_era": "modern",
    "may_have_page_numbers": True,
    "may_have_headers_footers": True,
    "special_features": ["handwriting", "stamps", "damage_stains"],
    "temperature": 0.1,
    "top_p": 0.2,
    "max_tokens": 8192,
    "custom_instructions": """## 档案文献识别指导

### 混合内容
- 区分印刷体和手写体
- 手写内容标记为 `**[手写]** 内容`

### 公章和签名
- 识别公章内容：`[公章: 单位名称]`
- 识别签名：`[签名: 姓名]` 或 `[签名: 不清]`

### 档案编号识别（重要）
**如果在页面上看到档案编号（如 SC 001, SC-001, 档案号：123 等），请使用以下格式输出**：

```
<!-- PageHeader: 档案编号 -->
```

**档案编号常见位置**：
- 页面顶部或底部
- 页眉或页脚区域
- 页面角落
- 可能带有前缀（如 SC, DOC, 档案号, 编号等）

**示例**：
- 看到 "SC 001" → 输出 `<!-- PageHeader: SC 001 -->`
- 看到 "SC-001" → 输出 `<!-- PageHeader: SC-001 -->`
- 看到 "档案号：123" → 输出 `<!-- PageHeader: 123 -->`
- 看到 "编号 A-2024-001" → 输出 `<!-- PageHeader: A-2024-001 -->`

**规则**：
- 将此标签放在输出的开头（内容之前）
- 只在实际看到档案编号时输出
- 不要猜测或编造编号
- 保持原始格式（包括空格、横线等）

### 文档元信息
- 保留文档编号、日期、文号
- 保留页眉页脚中的档案信息

### 破损处理
- 破损无法识别：`[破损]`
- 污渍遮挡：`[污渍遮挡]`
- 模糊不清：`[unclear]`"""
}

# Template 3: 现代出版物（默认推荐）
MODERN_PUBLICATION = {
    "text_direction": "horizontal",
    "may_have_footnotes": True,
    "may_have_references": True,
    "may_have_handwriting": False,
    "language_mode": "multilingual",
    "primary_language": "zh",
    "document_era": "contemporary",
    "may_have_page_numbers": True,
    "may_have_headers_footers": True,
    "special_features": [],
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192,
    "custom_instructions": """## 现代出版物识别指导

### 标准排版
- 横排文本，现代标点
- 标准段落格式

### 脚注识别（重点）
- 脚注通常在页面底部
- 字号明显小于正文
- 有编号标记（[1], ①, *）
- 与正文之间有分隔线或空白

**脚注示例**:
正文内容<sup>1</sup>继续正文。

---

<sup>1</sup> 这是脚注内容，位于页面底部，字号较小。

### 中英混排
- 保持中英文混合
- 保留英文单词的大小写
- 保留专有名词

### 图表
- 识别图表标题：`**图 1**: 标题内容`
- 识别表格标题：`**表 1**: 标题内容`"""
}

# Template 4: 哥特体德文
GOTHIC_GERMAN = {
    "text_direction": "horizontal",
    "may_have_footnotes": True,
    "may_have_references": True,
    "may_have_handwriting": False,
    "language_mode": "monolingual",
    "primary_language": "de",
    "document_era": "ancient",
    "may_have_page_numbers": True,
    "may_have_headers_footers": True,
    "special_features": ["gothic_script", "fraktur"],
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192,
    "custom_instructions": """## 哥特体德文识别指导

### Fraktur 字体
- 识别 Fraktur（哥特体）字形
- 注意长 s (ſ) 和短 s (s) 的区别
  - 词首和词中用长 s (ſ)
  - 词尾用短 s (s)

### 德文特殊字符
- ä, ö, ü, ß
- 保持原有拼写

### 历史拼写
- 保持历史拼写，不要现代化
- 如 "daſs" 不要改为 "dass\""""
}

# Template 5: 手稿
MANUSCRIPT = {
    "text_direction": "horizontal",
    "may_have_footnotes": True,
    "may_have_references": False,
    "may_have_handwriting": True,
    "language_mode": "monolingual",
    "primary_language": "en",
    "document_era": "modern",
    "may_have_page_numbers": False,
    "may_have_headers_footers": False,
    "special_features": ["handwriting", "corrections", "annotations"],
    "temperature": 0.2,
    "top_p": 0.3,
    "max_tokens": 8192,
    "custom_instructions": """## 手稿识别指导

### 手写内容
- 全手写内容
- 容忍字迹潦草和不规则

### 修改标记
- 删除线内容：`~~删除的内容~~`
- 插入内容：`^插入的内容^`
- 左侧边注：`<!-- Margin:left -->` + `> 内容` + `<!-- /Margin -->`
- 右侧边注：`<!-- Margin:right -->` + `> 内容` + `<!-- /Margin -->`

### 不规则排版
- 保持原有布局
- 不强制对齐"""
}

# Template 6: 学术论文
ACADEMIC_PAPER = {
    "text_direction": "horizontal",
    "may_have_footnotes": True,
    "may_have_references": True,
    "may_have_handwriting": False,
    "language_mode": "multilingual",
    "primary_language": "en",
    "document_era": "contemporary",
    "may_have_page_numbers": True,
    "may_have_headers_footers": True,
    "special_features": ["equations", "tables", "figures"],
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192,
    "custom_instructions": """## 学术论文识别指导

### 结构化格式
- 识别章节标题层级（# ## ###）
- 识别摘要、引言、方法、结果、讨论、结论

### 数学公式
- 行内公式：`$E = mc^2$`
- 块级公式：
$$
\\int_0^\\infty e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}
$$

### 表格和图表
- 保持表格格式
- 识别图表标题和编号

### 参考文献
- 识别引用标记 [1], (Smith, 2020)
- 识别参考文献列表

### 脚注格式
- 脚注标记：<sup>1</sup>, <sup>2</sup>, <sup>3</sup>
- 引用标记：<sup>1</sup>, <sup>2</sup>, <sup>3</sup>

**脚注示例**:
正文内容<sup>1</sup>继续正文。

---

<sup>1</sup> 这是脚注内容，位于页面底部，字号较小。"""
}

# Template 7: 混合内容
MIXED_CONTENT = {
    "text_direction": "mixed",
    "may_have_footnotes": True,
    "may_have_references": True,
    "may_have_handwriting": True,
    "language_mode": "multilingual",
    "primary_language": "zh",
    "document_era": "modern",
    "may_have_page_numbers": True,
    "may_have_headers_footers": True,
    "special_features": ["all"],
    "temperature": 0.1,
    "top_p": 0.2,
    "max_tokens": 8192,
    "custom_instructions": """## 混合内容识别指导

### 最大灵活性
- 适应横排和竖排混合
- 识别所有可能的文档元素
- 处理多语言混合

### 自适应识别
- 根据实际内容调整识别策略
- 不强制任何特定格式"""
}

# 模板字典
BUILTIN_TEMPLATES = {
    "universal": UNIVERSAL,
    "ancient_chinese": ANCIENT_CHINESE,
    "archive_document": ARCHIVE_DOCUMENT,
    "modern_publication": MODERN_PUBLICATION,
    "gothic_german": GOTHIC_GERMAN,
    "manuscript": MANUSCRIPT,
    "academic_paper": ACADEMIC_PAPER,
    "mixed_content": MIXED_CONTENT,
}

# 模板显示名称（用于 UI）
TEMPLATE_DISPLAY_NAMES = {
    "universal": "通用模板（推荐）",
    "ancient_chinese": "中文古籍",
    "archive_document": "档案文献",
    "modern_publication": "现代出版物",
    "gothic_german": "哥特体德文",
    "manuscript": "手稿",
    "academic_paper": "学术论文",
    "mixed_content": "混合内容",
}
