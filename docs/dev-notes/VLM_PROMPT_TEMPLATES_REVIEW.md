# VLM 提示词模板系统 - 完整展示

本文档展示所有 VLM Direct 模式下的提示词模板，包括基础语法、7个预置模板及其完整提示词内容。

---

## 📋 目录

1. [基础 Marker 语法](#基础-marker-语法)
2. [输出要求（严格规则）](#输出要求严格规则)
3. [元素存在性原则](#元素存在性原则)
4. [7个预置模板](#7个预置模板)
   - [模板1: 现代出版物（推荐）](#模板1-现代出版物推荐)
   - [模板2: 中文古籍](#模板2-中文古籍)
   - [模板3: 档案文献](#模板3-档案文献)
   - [模板4: 哥特体德文](#模板4-哥特体德文)
   - [模板5: 手稿](#模板5-手稿)
   - [模板6: 学术论文](#模板6-学术论文)
   - [模板7: 混合内容](#模板7-混合内容)
5. [API 参数预设](#api-参数预设)
6. [自定义配置](#自定义配置)

---

## 基础 Marker 语法

所有模板都包含以下基础语法说明：

```markdown
# Marker Markdown Syntax

Convert this document page to Markdown using the following syntax:

## Headings
# Level 1 Heading
## Level 2 Heading
### Level 3 Heading

## Lists
- Unordered list item
- Another item
  - Nested item

1. Ordered list item
2. Second item

## Tables
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data     | Data     | Data     |

## Math
Inline math: $E = mc^2$
Block math:
$$
\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
$$

## Code
```python
def hello():
    print("Hello")
```

## Formatting
**Bold** *Italic* `Code`
Subscript: <sub>text</sub>
Superscript: <sup>text</sup>

## Footnotes
Text with footnote reference[^1]

[^1]: Footnote content at bottom of page

## References
<span id="ref1">Reference anchor</span>
```

---

## 输出要求（严格规则）

所有模板都包含以下严格输出要求：

```markdown
## Output Requirements (CRITICAL - MUST FOLLOW)

### Strict Rules
1. **Output ONLY Markdown content, NO explanations or meta-information**
2. **Do NOT wrap output in code blocks (no ```markdown)**
3. **Do NOT add phrases like "Here is the result", "The content is"**
4. **Do NOT fabricate content that doesn't exist**
5. **If an element doesn't exist, do NOT mark it**
6. **Keep exact same as original, do NOT fix errors or add punctuation**
7. **Do NOT add your understanding, summary, or comments**

### Example

❌ Wrong:
Here is the converted Markdown:

# Title
Content...

Note: This is a sample document.

✅ Correct:
# Title
Content...

### Direct Output
Output Markdown directly without any wrapper.
```

---

## 元素存在性原则

所有模板都包含以下元素存在性原则：

```markdown
## Element Existence Principle

**IMPORTANT**: Each page has different content. Do NOT assume all elements exist!

- ✅ If page has heading, output `# Heading`
- ❌ If page has NO heading, do NOT add `#`
- ✅ If page has table, output table
- ❌ If page has NO table, do NOT create table
- ✅ If page has footnotes, output `[^1]` and `[^1]: content`
- ❌ If page has NO footnotes, do NOT add footnote marks
- ✅ If page has math, output `$formula$`
- ❌ If page has NO math, do NOT add `$` symbols

**Principle**: Only mark what you actually see, do NOT fabricate or assume!

### Uncertainty Handling
- If text is blurry: output `[unclear]`
- If image quality is poor: output `[unreadable]`
- If non-text content (image, chart): output `[image]` or `[chart]`
- **Do NOT guess or fabricate content**
```

---

## 7个预置模板

### 模板1: 现代出版物（推荐）

**适用场景**: 现代印刷书籍、期刊、杂志等标准排版文档

**文档特征参数**:
```python
text_direction: "horizontal"
has_footnotes: True
has_references: True
has_handwriting: False
language_mode: "multilingual"
primary_language: "zh"
document_era: "contemporary"
has_page_numbers: True
has_headers_footers: True
special_features: []
```

**API 参数**:
```python
temperature: 0.0
top_p: 0.1
max_tokens: 8192
```

**自定义指导**:
```markdown
## 现代出版物识别指导

### 标准排版
- 横排文本，现代标点
- 标准段落格式

### 脚注识别（重点）
- 脚注通常在页面底部
- 字号明显小于正文
- 有编号标记（[1], ①, *）
- 与正文之间有分隔线或空白

**脚注示例**:
正文内容[^1]继续正文。

---

[^1]: 这是脚注内容，位于页面底部，字号较小。

### 中英混排
- 保持中英文混合
- 保留英文单词的大小写
- 保留专有名词

### 图表
- 识别图表标题：`**图 1**: 标题内容`
- 识别表格标题：`**表 1**: 标题内容`
```

**完整提示词示例**:
```
[基础 Marker 语法]
+
[输出要求（严格规则）]
+
[元素存在性原则]
+
[现代出版物识别指导]
```

---

### 模板2: 中文古籍

**适用场景**: 竖排古籍、线装书、古代文献

**文档特征参数**:
```python
text_direction: "vertical"
has_footnotes: True
has_references: True
has_handwriting: False
language_mode: "monolingual"
primary_language: "zh"
document_era: "ancient"
has_page_numbers: True
has_headers_footers: False
special_features: ["seal_script", "seals_stamps", "annotations"]
```

**API 参数**:
```python
temperature: 0.0
top_p: 0.1
max_tokens: 8192
```

**自定义指导**:
```markdown
## 中文古籍识别指导

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
- 识别批注（标记为 `[批注: 内容]`）
```

**特殊指导（自动生成）**:
```markdown
### Text Direction
- Vertical text, read from right to left, top to bottom
- Maintain original column order

### Footnote Recognition
Footnotes have these characteristics:
- Usually at bottom of page
- Smaller font size than main text
- Separated by line or space
- Has numbering or symbols ([1], *, †)

**Do NOT** assume indented text is footnote!
**Do** consider position, font size, and markers together.

Example:
Main text[^1] continues.

---

[^1]: Footnote content at bottom, smaller font.
```

---

### 模板3: 档案文献

**适用场景**: 历史档案、公文、手写与印刷混合文档

**文档特征参数**:
```python
text_direction: "horizontal"
has_footnotes: True
has_references: True
has_handwriting: True
language_mode: "monolingual"
primary_language: "zh"
document_era: "modern"
has_page_numbers: True
has_headers_footers: True
special_features: ["handwriting", "stamps", "damage_stains"]
```

**API 参数**:
```python
temperature: 0.1
top_p: 0.2
max_tokens: 8192
```

**自定义指导**:
```markdown
## 档案文献识别指导

### 混合内容
- 区分印刷体和手写体
- 手写内容标记为 `**[手写]** 内容`

### 公章和签名
- 识别公章内容：`[公章: 单位名称]`
- 识别签名：`[签名: 姓名]` 或 `[签名: 不清]`

### 文档元信息
- 保留文档编号、日期、文号
- 保留页眉页脚中的档案信息

### 破损处理
- 破损无法识别：`[破损]`
- 污渍遮挡：`[污渍遮挡]`
- 模糊不清：`[unclear]`
```

**特殊指导（自动生成）**:
```markdown
### Handwriting
- Mark handwritten content: `**[Handwritten]** content`
- Tolerate irregular writing
- Mark unclear parts: `[unclear]`

### Footnote Recognition
[同上]
```

---

### 模板4: 哥特体德文

**适用场景**: Fraktur 字体德文文献、历史德文文档

**文档特征参数**:
```python
text_direction: "horizontal"
has_footnotes: True
has_references: True
has_handwriting: False
language_mode: "monolingual"
primary_language: "de"
document_era: "ancient"
has_page_numbers: True
has_headers_footers: True
special_features: ["gothic_script", "fraktur"]
```

**API 参数**:
```python
temperature: 0.0
top_p: 0.1
max_tokens: 8192
```

**自定义指导**:
```markdown
## 哥特体德文识别指导

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
- 如 "daſs" 不要改为 "dass"
```

---

### 模板5: 手稿

**适用场景**: 全手写文档、笔记、草稿

**文档特征参数**:
```python
text_direction: "horizontal"
has_footnotes: True
has_references: False
has_handwriting: True
language_mode: "monolingual"
primary_language: "en"
document_era: "modern"
has_page_numbers: False
has_headers_footers: False
special_features: ["handwriting", "corrections", "annotations"]
```

**API 参数**:
```python
temperature: 0.2
top_p: 0.3
max_tokens: 8192
```

**自定义指导**:
```markdown
## 手稿识别指导

### 手写内容
- 全手写内容
- 容忍字迹潦草和不规则

### 修改标记
- 删除线内容：`~~删除的内容~~`
- 插入内容：`^插入的内容^`
- 边注：`[边注: 内容]`

### 不规则排版
- 保持原有布局
- 不强制对齐
```

---

