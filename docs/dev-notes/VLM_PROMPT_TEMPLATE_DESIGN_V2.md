# VLM Prompt Template System - Design Proposal V2

## 更新说明 (Update Notes)

**V2 新增内容**:
1. ✅ API 参数控制系统（temperature, top_p, top_k 等）
2. ✅ 减少幻觉和多余内容的策略
3. ✅ 灵活处理页面元素（不强制所有元素存在）
4. ✅ 跨 API 兼容性设计（OpenAI, Gemini, Qwen, Claude）

---

## 1. 问题分析 (Problem Analysis)

### 当前问题
- **现有提示词过于简单**: 只包含基本的 Markdown 语法，缺少 Marker 特有的文档结构元素
- **脚注识别错误**: VLM 将脚注误识别为缩进文本，而非独立的脚注块
- **缺少文档类型上下文**: 不同类型文档（古籍、档案、现代出版物）需要不同的识别策略
- **无参数化定制**: 无法根据文档特征（横排/竖排、手写/印刷、单语/多语）调整提示词
- **缺少 API 参数控制**: 无法设置 temperature, top_p 等参数来控制输出质量和可复现性 ⭐
- **幻觉和多余内容**: VLM 可能返回解释性文字或不存在的元素 ⭐
- **强制性元素假设**: 提示词假设所有元素都存在，但实际每页内容不同 ⭐
- **跨 API 兼容性不足**: 不同 VLM API（OpenAI, Gemini, Qwen）参数格式不统一 ⭐

### Marker 支持的完整块类型 (32+ types)

**文本类**:
- `Text`: 普通文本段落
- `TextInlineMath`: 包含行内数学公式的文本
- `SectionHeader`: 章节标题（支持 h1-h6 级别）

**结构类**:
- `Page`: 页面容器
- `ListGroup`: 列表组
- `ListItem`: 列表项
- `TableOfContents`: 目录

**特殊内容**:
- `Footnote`: **脚注** (当前识别问题的重点)
- `Reference`: 引用/参考文献
- `PageHeader`: 页眉
- `PageFooter`: 页脚
- `Caption`: 图表标题

**富内容**:
- `Table`: 表格
- `TableCell`: 表格单元格
- `Figure`: 图形容器
- `Picture`: 图片
- `Equation`: 块级数学公式
- `Code`: 代码块

**复杂内容**:
- `Handwriting`: **手写文本** (需要特殊处理)
- `Form`: 表单
- `ComplexRegion`: 复杂区域（混合内容）

### Marker 的 Markdown 语法规范

```markdown
# 标题 (Headings)
# 一级标题
## 二级标题
### 三级标题

# 列表 (Lists)
- 无序列表项
- 另一个项
  - 嵌套项

1. 有序列表项
2. 第二项

# 表格 (Tables)
| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 数据 | 数据 | 数据 |

# 数学公式 (Math)
行内公式: $E = mc^2$
块级公式:
$$
\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
$$

# 代码 (Code)
```python
def hello():
    print("Hello")
```

# 格式 (Formatting)
**粗体** *斜体* `代码`

# 脚注 (Footnotes) - 重要!
正文中的引用[^1]

[^1]: 这是脚注内容，通常在页面底部

# 引用 (References)
<span id="ref1">引用锚点</span>

# 页码锚点 (Page Anchors)
{1}  <!-- 页码标记 -->
```

---

## 2. 设计方案 (Design Proposal)

### 2.1 API 参数控制系统 ⭐ NEW

#### 2.1.1 核心 API 参数

为了提升识别准确性、减少幻觉、增强可复现性，支持以下 API 参数：

| 参数 | 作用 | 推荐值（OCR任务） | 说明 |
|------|------|------------------|------|
| `temperature` | 控制随机性 | 0.0 - 0.2 | 低温度提高准确性和可复现性 |
| `top_p` | 核采样 | 0.1 - 0.3 | 限制候选词范围，减少幻觉 |
| `top_k` | Top-K 采样 | 1 - 10 | 进一步限制候选词 |
| `max_tokens` | 最大输出长度 | 4096 - 8192 | 根据页面内容调整 |
| `presence_penalty` | 惩罚重复主题 | 0.0 | OCR 任务不需要 |
| `frequency_penalty` | 惩罚重复词 | 0.0 | OCR 任务不需要 |
| `seed` | 随机种子 | 固定值 | 提高可复现性（部分 API 支持） |

#### 2.1.2 任务类型推荐配置

**高准确性配置（默认推荐）**:
```python
{
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0
}
```
- **适用场景**: 学术论文、法律文档、技术文档、档案
- **特点**: 最高准确性，完全可复现，最少幻觉
- **推荐指数**: ⭐⭐⭐⭐⭐

**平衡配置**:
```python
{
    "temperature": 0.2,
    "top_p": 0.3,
    "max_tokens": 8192
}
```
- **适用场景**: 一般文档、书籍、报告
- **特点**: 准确性和灵活性平衡
- **推荐指数**: ⭐⭐⭐⭐

**创意配置**:
```python
{
    "temperature": 0.5,
    "top_p": 0.8,
    "max_tokens": 8192
}
```
- **适用场景**: 手写笔记、草稿（需要推理和补全）
- **特点**: 更灵活的解释能力，可能补全模糊内容
- **推荐指数**: ⭐⭐⭐
- **注意**: 可能产生幻觉，不适合严格的 OCR 任务

#### 2.1.3 跨 API 兼容性设计 ⭐ NEW

不同 VLM API 的参数支持情况：

| 参数 | OpenAI | Gemini | Qwen | Claude | 备注 |
|------|--------|--------|------|--------|------|
| `temperature` | ✅ | ✅ | ✅ | ✅ | 通用支持 |
| `top_p` | ✅ | ✅ | ✅ | ✅ | 通用支持 |
| `top_k` | ❌ | ✅ | ✅ | ✅ | OpenAI 不支持 |
| `max_tokens` | ✅ | ✅ | ✅ | ✅ | 通用支持 |
| `presence_penalty` | ✅ | ❌ | ❌ | ❌ | 仅 OpenAI |
| `frequency_penalty` | ✅ | ❌ | ❌ | ❌ | 仅 OpenAI |
| `seed` | ✅ | ❌ | ❌ | ❌ | 仅 OpenAI |

**兼容性策略**:

```python
class APIParameterAdapter:
    """API 参数适配器，处理不同 API 的参数差异"""

    # API 支持的参数映射
    SUPPORTED_PARAMS = {
        "openai": ["temperature", "top_p", "max_tokens", "presence_penalty",
                   "frequency_penalty", "seed"],
        "gemini": ["temperature", "top_p", "top_k", "max_tokens"],
        "qwen": ["temperature", "top_p", "top_k", "max_tokens"],
        "claude": ["temperature", "top_p", "top_k", "max_tokens"],
        "unknown": ["temperature", "top_p", "max_tokens"]  # 最小公共集
    }

    @staticmethod
    def detect_api_type(base_url: str, model: str) -> str:
        """
        根据 base_url 和 model 自动检测 API 类型

        Returns:
            "openai" | "gemini" | "qwen" | "claude" | "unknown"
        """
        base_url_lower = base_url.lower()
        model_lower = model.lower()

        if "openai.com" in base_url_lower or "gpt" in model_lower:
            return "openai"
        elif "generativelanguage.googleapis.com" in base_url_lower or "gemini" in model_lower:
            return "gemini"
        elif "dashscope.aliyuncs.com" in base_url_lower or "qwen" in model_lower:
            return "qwen"
        elif "anthropic.com" in base_url_lower or "claude" in model_lower:
            return "claude"
        else:
            logger.warning(f"Unknown API type for base_url={base_url}, model={model}")
            return "unknown"

    @staticmethod
    def adapt_params(api_type: str, params: dict) -> dict:
        """
        根据 API 类型过滤和转换参数

        Args:
            api_type: "openai", "gemini", "qwen", "claude", "unknown"
            params: 原始参数字典

        Returns:
            适配后的参数字典
        """
        supported = APIParameterAdapter.SUPPORTED_PARAMS.get(api_type, [])
        adapted = {k: v for k, v in params.items() if k in supported}

        # 记录被过滤的参数
        filtered = set(params.keys()) - set(adapted.keys())
        if filtered:
            logger.info(f"[APIParameterAdapter] Filtered unsupported params for {api_type}: {filtered}")

        return adapted
```

#### 2.1.4 配置示例

```python
# VlmDirectAsyncConverter 配置
config = {
    "vlm_direct_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "vlm_direct_model": "qwen-vl-max",
    "vlm_direct_api_key": "sk-xxx",

    # API 参数配置（新增）
    "vlm_direct_temperature": 0.0,
    "vlm_direct_top_p": 0.1,
    "vlm_direct_top_k": 1,
    "vlm_direct_max_tokens": 8192,
    "vlm_direct_presence_penalty": 0.0,  # 会被自动过滤（Qwen 不支持）
    "vlm_direct_frequency_penalty": 0.0,  # 会被自动过滤（Qwen 不支持）

    # 或使用预设配置
    "vlm_direct_api_preset": "high_accuracy"  # "high_accuracy" | "balanced" | "creative"
}
```

### 2.2 减少幻觉和多余内容的策略 ⭐ NEW

#### 2.2.1 提示词强化

在提示词中添加严格的输出约束：

```markdown
## 输出要求 (CRITICAL - MUST FOLLOW)

### 严格规则
1. **只输出 Markdown 内容，不要添加任何解释、注释或元信息**
2. **不要输出代码块包装符（如 ```markdown）**
3. **不要添加"这是转换结果"、"以下是内容"等说明性文字**
4. **不要编造不存在的内容**
5. **如果某个元素不存在，就不要标记该元素** ⭐
6. **保持与原文完全一致，不要修正错误或添加标点**
7. **不要添加你的理解、总结或评论**

### 示例对比

❌ 错误输出:
```markdown
以下是转换后的 Markdown 内容：

# 标题
正文内容...

注：这是一个示例文档，包含3个段落。
```

✅ 正确输出:
```
# 标题
正文内容...
```

### 元素存在性原则 ⭐ NEW

**重要**: 每一页的内容都不同，不要假设所有元素都存在！

- ✅ 如果页面有标题，输出 `# 标题`
- ❌ 如果页面没有标题，**不要**添加 `#` 标记
- ✅ 如果页面有表格，输出表格
- ❌ 如果页面没有表格，**不要**创建表格
- ✅ 如果页面有脚注，输出 `[^1]` 和 `[^1]: 内容`
- ❌ 如果页面没有脚注，**不要**添加脚注标记
- ✅ 如果页面有数学公式，输出 `$公式$`
- ❌ 如果页面没有数学公式，**不要**添加 `$` 符号

**原则**: 只标记你确实看到的内容，不要编造或假设！

### 不确定性处理

- 如果文字模糊不清，输出 `[unclear]`
- 如果图像质量差无法识别，输出 `[unreadable]`
- 如果是非文字内容（图片、图表），输出 `[image]` 或 `[chart]`
- **不要猜测或编造内容**

### 输出格式

直接输出 Markdown，不要任何包装：

```
# 这是标题

这是正文第一段。

这是正文第二段。
```

**不要**输出：
```markdown
```markdown
# 这是标题
...
```
```

#### 2.2.2 系统级约束

使用 API 参数配合提示词，双重保障：

```python
# 高准确性配置 - 减少幻觉
api_params = {
    "temperature": 0.0,        # 完全确定性输出，无随机性
    "top_p": 0.1,              # 只选择最可能的 10% 词汇
    "max_tokens": 8192,        # 足够的输出空间
    "presence_penalty": 0.0,   # 不惩罚重复（OCR 可能有重复内容）
    "frequency_penalty": 0.0   # 不惩罚高频词（如"的"、"是"）
}
```

**参数说明**:
- `temperature=0.0`: 最关键的参数，确保输出完全确定，无创造性
- `top_p=0.1`: 进一步限制词汇选择范围，只选最可能的词
- `top_k=1`: 如果 API 支持，每次只选概率最高的词

#### 2.2.3 后处理验证

```python
def validate_and_clean_output(markdown: str, strict: bool = True) -> tuple[bool, str]:
    """
    验证 VLM 输出是否符合要求，并清理多余内容

    Args:
        markdown: VLM 原始输出
        strict: 是否启用严格模式

    Returns:
        (is_valid, cleaned_markdown)
    """
    import re

    original_markdown = markdown

    # 1. 移除代码块包装
    if markdown.strip().startswith("```"):
        lines = markdown.strip().split("\n")
        # 移除开头的 ```markdown 或 ```
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 移除结尾的 ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        markdown = "\n".join(lines)

    # 2. 移除常见的说明性前缀
    prefixes_to_remove = [
        "以下是转换结果：",
        "以下是转换后的内容：",
        "这是转换后的 Markdown：",
        "Markdown 内容如下：",
        "转换结果：",
        "Here is the converted content:",
        "The markdown content is:",
        "Converted markdown:",
    ]
    for prefix in prefixes_to_remove:
        if markdown.strip().startswith(prefix):
            markdown = markdown.strip()[len(prefix):].strip()

    # 3. 移除结尾的说明性文字
    suffixes_to_remove = [
        "注：",
        "Note:",
        "说明：",
        "以上是",
        "This is",
    ]
    lines = markdown.split("\n")
    while lines:
        last_line = lines[-1].strip()
        should_remove = False
        for suffix in suffixes_to_remove:
            if last_line.startswith(suffix):
                should_remove = True
                break
        if should_remove:
            lines.pop()
        else:
            break
    markdown = "\n".join(lines)

    # 4. 检查是否包含元信息（严格模式）
    if strict:
        meta_patterns = [
            r"^注[：:].+$",
            r"^Note[：:].+$",
            r"^\[说明\].+$",
            r"^\[Note\].+$",
        ]

        cleaned_lines = []
        for line in markdown.split("\n"):
            is_meta = False
            for pattern in meta_patterns:
                if re.match(pattern, line.strip()):
                    is_meta = True
                    logger.warning(f"Removed meta line: {line.strip()}")
                    break
            if not is_meta:
                cleaned_lines.append(line)

        markdown = "\n".join(cleaned_lines)

    # 5. 验证是否有实际内容
    if len(markdown.strip()) < 10:
        logger.error(f"Output too short: {len(markdown)} chars")
        return False, original_markdown

    # 6. 记录清理情况
    if markdown != original_markdown:
        logger.info(f"Cleaned output: {len(original_markdown)} -> {len(markdown)} chars")

    return True, markdown.strip()
```

### 2.3 模板系统架构

```
VlmPromptTemplate
├── base_template (基础模板 - 完整 Marker 语法)
├── api_parameters (API 参数配置) ⭐ NEW
│   ├── temperature: float
│   ├── top_p: float
│   ├── top_k: int
│   ├── max_tokens: int
│   ├── presence_penalty: float
│   ├── frequency_penalty: float
│   └── seed: int
├── parameters (文档特征参数)
│   ├── text_direction: "horizontal" | "vertical" | "mixed"
│   ├── has_footnotes: bool
│   ├── has_references: bool
│   ├── has_handwriting: bool
│   ├── language_mode: "monolingual" | "multilingual"
│   ├── primary_language: "zh" | "en" | "de" | "ja" | ...
│   ├── document_era: "ancient" | "modern" | "contemporary"
│   ├── has_page_numbers: bool
│   ├── has_headers_footers: bool
│   └── special_features: List[str]
└── built_in_templates (预置模板库)
    ├── ancient_chinese (中文古籍)
    ├── archive_document (档案文献)
    ├── modern_publication (现代出版物)
    ├── gothic_german (哥特体德文)
    ├── manuscript (手稿)
    ├── academic_paper (学术论文)
    └── mixed_content (混合内容)
```


### 2.4 预置模板库

每个模板包含：文档特征参数 + API 参数配置 + 特殊指导

#### Template 1: 中文古籍 (Ancient Chinese Texts)

**文档特征参数**:
```python
{
    "text_direction": "vertical",
    "has_footnotes": true,
    "has_references": true,
    "has_handwriting": false,
    "language_mode": "monolingual",
    "primary_language": "zh",
    "document_era": "ancient",
    "has_page_numbers": true,
    "has_headers_footers": false,
    "special_features": ["seal_script", "seals_stamps", "annotations"]
}
```

**API 参数配置**:
```python
{
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192
}
```

**特殊指导**:
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

### 示例
```
右起第一列内容
右起第二列内容

[^1]: 小字注释内容
[印章: 某某藏书]
```
```

#### Template 2: 档案文献 (Archive Documents)

**文档特征参数**:
```python
{
    "text_direction": "horizontal",
    "has_footnotes": true,
    "has_references": true,
    "has_handwriting": true,
    "language_mode": "monolingual",
    "primary_language": "zh",
    "document_era": "modern",
    "has_page_numbers": true,
    "has_headers_footers": true,
    "special_features": ["handwriting", "stamps", "damage_stains"]
}
```

**API 参数配置**:
```python
{
    "temperature": 0.1,  # 稍高，处理手写内容
    "top_p": 0.2,
    "max_tokens": 8192
}
```

**特殊指导**:
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

#### Template 3: 现代出版物 (Modern Publications) - 默认推荐

**文档特征参数**:
```python
{
    "text_direction": "horizontal",
    "has_footnotes": true,
    "has_references": true,
    "has_handwriting": false,
    "language_mode": "multilingual",
    "primary_language": "zh",
    "document_era": "contemporary",
    "has_page_numbers": true,
    "has_headers_footers": true,
    "special_features": []
}
```

**API 参数配置**:
```python
{
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192
}
```

**特殊指导**:
```markdown
## 现代出版物识别指导

### 标准排版
- 横排文本，现代标点
- 标准段落格式

### 脚注识别 ⭐ 重点
- 脚注通常在页面底部
- 字号明显小于正文
- 有编号标记（[1], ①, *）
- 与正文之间有分隔线或空白

**脚注示例**:
```
正文内容[^1]继续正文。

---

[^1]: 这是脚注内容，位于页面底部，字号较小。
```

### 中英混排
- 保持中英文混合
- 保留英文单词的大小写
- 保留专有名词

### 图表
- 识别图表标题：`**图 1**: 标题内容`
- 识别表格标题：`**表 1**: 标题内容`
```

#### Template 4: 哥特体德文 (Gothic German)

**文档特征参数**:
```python
{
    "text_direction": "horizontal",
    "has_footnotes": true,
    "has_references": true,
    "has_handwriting": false,
    "language_mode": "monolingual",
    "primary_language": "de",
    "document_era": "ancient",
    "has_page_numbers": true,
    "has_headers_footers": true,
    "special_features": ["gothic_script", "fraktur"]
}
```

**API 参数配置**:
```python
{
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192
}
```

**特殊指导**:
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

#### Template 5: 手稿 (Manuscripts)

**文档特征参数**:
```python
{
    "text_direction": "horizontal",
    "has_footnotes": true,
    "has_references": false,
    "has_handwriting": true,
    "language_mode": "monolingual",
    "primary_language": "en",
    "document_era": "modern",
    "has_page_numbers": false,
    "has_headers_footers": false,
    "special_features": ["handwriting", "corrections", "annotations"]
}
```

**API 参数配置**:
```python
{
    "temperature": 0.2,  # 稍高，处理手写和修改
    "top_p": 0.3,
    "max_tokens": 8192
}
```

**特殊指导**:
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

#### Template 6: 学术论文 (Academic Papers)

**文档特征参数**:
```python
{
    "text_direction": "horizontal",
    "has_footnotes": true,
    "has_references": true,
    "has_handwriting": false,
    "language_mode": "multilingual",
    "primary_language": "en",
    "document_era": "contemporary",
    "has_page_numbers": true,
    "has_headers_footers": true,
    "special_features": ["equations", "tables", "figures"]
}
```

**API 参数配置**:
```python
{
    "temperature": 0.0,
    "top_p": 0.1,
    "max_tokens": 8192
}
```

**特殊指导**:
```markdown
## 学术论文识别指导

### 结构化格式
- 识别章节标题层级（# ## ###）
- 识别摘要、引言、方法、结果、讨论、结论

### 数学公式
- 行内公式：`$E = mc^2$`
- 块级公式：
```
$$
\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
$$
```

### 表格和图表
- 保持表格格式
- 识别图表标题和编号

### 参考文献
- 识别引用标记 [1], (Smith, 2020)
- 识别参考文献列表
```

#### Template 7: 混合内容 (Mixed Content)

**文档特征参数**:
```python
{
    "text_direction": "mixed",
    "has_footnotes": true,
    "has_references": true,
    "has_handwriting": true,
    "language_mode": "multilingual",
    "primary_language": "zh",
    "document_era": "modern",
    "has_page_numbers": true,
    "has_headers_footers": true,
    "special_features": ["all"]
}
```

**API 参数配置**:
```python
{
    "temperature": 0.1,
    "top_p": 0.2,
    "max_tokens": 8192
}
```

**特殊指导**:
```markdown
## 混合内容识别指导

### 最大灵活性
- 适应横排和竖排混合
- 识别所有可能的文档元素
- 处理多语言混合

### 自适应识别
- 根据实际内容调整识别策略
- 不强制任何特定格式
```



### 3.3 集成到 VlmDirectAsyncConverter

修改 `vlm_direct_async.py` 以支持模板系统和 API 参数：

```python
class VlmDirectAsyncConverter(BaseConverter):
    # 模板配置（新增）
    vlm_direct_prompt_template: str = "modern_publication"
    vlm_direct_prompt_params: dict = {}
    vlm_direct_api_preset: str = "high_accuracy"

    # API 参数配置（新增）
    vlm_direct_temperature: float = 0.0
    vlm_direct_top_p: float = 0.1
    vlm_direct_top_k: int | None = None

    def __init__(self, config):
        super().__init__(config)

        # 构建提示词模板
        from marker.prompts.builder import PromptBuilder
        from marker.prompts.api_adapter import APIParameterAdapter

        if config.get("vlm_direct_prompt_params"):
            # 自定义参数
            self.prompt_template = PromptBuilder.from_params(
                **config["vlm_direct_prompt_params"]
            )
        else:
            # 使用预置模板
            template_name = config.get("vlm_direct_prompt_template", "modern_publication")
            self.prompt_template = PromptBuilder.from_template(template_name)

            # 应用 API 预设
            preset = config.get("vlm_direct_api_preset", "high_accuracy")
            if preset:
                preset_params = PromptBuilder.from_preset(preset)
                for key, value in preset_params.items():
                    setattr(self.prompt_template, key, value)

        # 覆盖单独指定的 API 参数
        if "vlm_direct_temperature" in config:
            self.prompt_template.temperature = config["vlm_direct_temperature"]
        if "vlm_direct_top_p" in config:
            self.prompt_template.top_p = config["vlm_direct_top_p"]
        if "vlm_direct_top_k" in config:
            self.prompt_template.top_k = config["vlm_direct_top_k"]

        # 构建提示词
        self.prompt = self.prompt_template.build_prompt()

        # 检测 API 类型
        self.api_type = APIParameterAdapter.detect_api_type(
            self.base_url, self.model
        )

        # 获取适配后的 API 参数
        self.api_params = self.prompt_template.get_api_params(self.api_type)

        logger.info(f"[VlmDirectAsyncConverter] Template: {template_name}")
        logger.info(f"[VlmDirectAsyncConverter] API Type: {self.api_type}")
        logger.info(f"[VlmDirectAsyncConverter] API Params: {self.api_params}")

    async def _convert_page_async(self, session, img, page_num, semaphore):
        # ... 构建 payload
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            **self.api_params  # 添加 API 参数
        }

        # ... API 调用
        async with session.post(...) as response:
            if response.status == 200:
                data = await response.json()
                markdown = data["choices"][0]["message"]["content"].strip()

                # 后处理验证和清理
                from marker.prompts.base import validate_and_clean_output
                is_valid, cleaned_markdown = validate_and_clean_output(markdown)

                if not is_valid:
                    logger.warning(f"Invalid output on page {page_num}")

                return (page_num, cleaned_markdown)
```

---

## 4. 优势分析 (Advantages)

### 4.1 准确性提升
- ✅ API 参数控制（temperature=0.0）确保输出确定性
- ✅ 完整的 Marker 语法规范指导 VLM
- ✅ 针对性的文档类型指导
- ✅ 详细的脚注识别规则

### 4.2 减少幻觉
- ✅ 严格的输出约束（不要解释、不要编造）
- ✅ 元素存在性原则（不强制所有元素）
- ✅ 低 temperature 和 top_p 限制随机性
- ✅ 后处理验证和清理

### 4.3 可复现性
- ✅ temperature=0.0 确保相同输入产生相同输出
- ✅ seed 参数支持（OpenAI）
- ✅ 确定性采样策略

### 4.4 兼容性
- ✅ 自动检测 API 类型
- ✅ 参数适配器过滤不支持的参数
- ✅ 支持 OpenAI, Gemini, Qwen, Claude
- ✅ 降级到最小公共参数集

### 4.5 灵活性
- ✅ 7个预置模板覆盖常见场景
- ✅ 参数化设计支持任意组合
- ✅ 自定义模板满足特殊需求
- ✅ API 参数预设 + 自定义

### 4.6 用户友好
- ✅ Streamlit UI 提供直观的模板选择
- ✅ 预置模板开箱即用
- ✅ 高级用户可自定义参数
- ✅ 实时参数说明和帮助

---

## 5. 实现步骤 (Implementation Steps)

1. **创建 API 参数适配器** (`marker/prompts/api_adapter.py`)
   - 实现 `APIParameterAdapter` 类
   - 实现 `detect_api_type()` 方法
   - 实现 `adapt_params()` 方法

2. **创建基础模板类** (`marker/prompts/base.py`)
   - 实现 `VlmPromptTemplate` 类
   - 实现 `build_prompt()` 方法
   - 实现 `get_api_params()` 方法
   - 实现 `validate_and_clean_output()` 函数

3. **创建预置模板库** (`marker/prompts/templates.py`)
   - 定义 7 个预置模板配置
   - 每个模板包含文档参数 + API 参数 + 特殊指导

4. **创建提示词构建器** (`marker/prompts/builder.py`)
   - 实现 `PromptBuilder` 类
   - 实现 `from_template()` 方法
   - 实现 `from_params()` 方法
   - 实现 `from_preset()` 方法

5. **修改 VlmDirectAsyncConverter**
   - 添加模板配置参数
   - 添加 API 参数配置
   - 集成 `PromptBuilder`
   - 集成 `APIParameterAdapter`
   - 添加后处理验证
   - 保持向后兼容

6. **更新 Streamlit UI**
   - 添加模板选择下拉框
   - 添加 API 参数预设选择
   - 添加自定义参数配置界面
   - 添加参数说明和帮助

7. **测试和优化**
   - 使用不同类型文档测试
   - 重点测试脚注识别
   - 测试不同 API 的兼容性
   - 根据结果优化提示词和参数

---

## 6. 向后兼容性 (Backward Compatibility)

- ✅ 保留 `vlm_direct_prompt` 参数，允许直接指定提示词
- ✅ 如果未指定模板，默认使用 `modern_publication`
- ✅ 如果未指定 API 参数，使用 `high_accuracy` 预设
- ✅ 现有代码无需修改即可继续工作

---

## 7. 未来扩展 (Future Extensions)

- **动态提示词优化**: 根据 VLM 输出质量自动调整提示词
- **多模型适配**: 针对不同 VLM（GPT-4V, Gemini, Qwen）优化提示词
- **用户反馈学习**: 收集用户反馈，持续改进模板
- **提示词版本管理**: 支持提示词版本控制和 A/B 测试
- **自动模板选择**: 根据文档特征自动推荐模板

---

## 8. 审查要点 (Review Checklist)

请审查以下方面：

- [ ] **API 参数控制**: temperature, top_p 等参数设计是否合理？
- [ ] **跨 API 兼容性**: 参数适配器是否能处理不同 API？
- [ ] **减少幻觉策略**: 提示词约束和 API 参数配合是否有效？
- [ ] **元素存在性原则**: 不强制所有元素存在的设计是否合理？
- [ ] **预置模板**: 7个模板是否覆盖您的使用场景？
- [ ] **脚注识别**: 详细的脚注识别指导是否能解决问题？
- [ ] **实现方案**: 文件结构和类设计是否清晰可行？
- [ ] **UI 设计**: Streamlit 界面是否直观易用？
- [ ] **其他需求**: 是否有其他需要考虑的方面？

---

## 9. 配置示例 (Configuration Examples)

### 示例 1: 使用预置模板 + 默认 API 参数

```python
config = {
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-xxx",
    "vlm_direct_prompt_template": "modern_publication",  # 使用预置模板
    "vlm_direct_api_preset": "high_accuracy"  # 使用高准确性预设
}
```

### 示例 2: 使用预置模板 + 自定义 API 参数

```python
config = {
    "vlm_direct_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "vlm_direct_model": "qwen-vl-max",
    "vlm_direct_api_key": "sk-xxx",
    "vlm_direct_prompt_template": "ancient_chinese",  # 中文古籍模板
    "vlm_direct_temperature": 0.0,  # 自定义参数
    "vlm_direct_top_p": 0.1,
    "vlm_direct_top_k": 1,
}
```

### 示例 3: 完全自定义

```python
config = {
    "vlm_direct_base_url": "https://api.openai.com/v1",
    "vlm_direct_model": "gpt-4o",
    "vlm_direct_api_key": "sk-xxx",
    "vlm_direct_prompt_params": {  # 自定义模板参数
        "text_direction": "vertical",
        "has_footnotes": True,
        "has_handwriting": True,
        "language_mode": "multilingual",
        "primary_language": "zh",
        "temperature": 0.0,  # API 参数也在这里
        "top_p": 0.1,
    }
}
```

---

**请审查此设计方案并提供反馈。审查通过后，我将开始实现代码。**
