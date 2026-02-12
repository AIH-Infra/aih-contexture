# VLM Prompt Template System - Design Proposal

## 1. 问题分析 (Problem Analysis)

### 当前问题
- **现有提示词过于简单**: 只包含基本的 Markdown 语法，缺少 Marker 特有的文档结构元素
- **脚注识别错误**: VLM 将脚注误识别为缩进文本，而非独立的脚注块
- **缺少文档类型上下文**: 不同类型文档（古籍、档案、现代出版物）需要不同的识别策略
- **无参数化定制**: 无法根据文档特征（横排/竖排、手写/印刷、单语/多语）调整提示词
- **缺少 API 参数控制**: 无法设置 temperature, top_p 等参数来控制输出质量和可复现性
- **幻觉和多余内容**: VLM 可能返回解释性文字或不存在的元素
- **强制性元素假设**: 提示词假设所有元素都存在，但实际每页内容不同
- **跨 API 兼容性不足**: 不同 VLM API（OpenAI, Gemini, Qwen）参数格式不统一

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

## 2. 设计方案 (Design Proposal)

### 2.1 模板��统架构

```
VlmPromptTemplate
├── base_template (基础模板 - 完整 Marker 语法)
├── parameters (参数化配置)
│   ├── text_direction: "horizontal" | "vertical" | "mixed"
│   ├── has_footnotes: bool
│   ├── has_references: bool
│   ├── has_handwriting: bool
│   ├── language_mode: "monolingual" | "multilingual"
│   ├── primary_language: "zh" | "en" | "de" | "ja" | ...
│   ├── document_era: "ancient" | "modern" | "contemporary"
│   ├── has_page_numbers: bool
│   ├── has_headers_footers: bool
│   └── special_features: List[str]  # ["gothic_script", "seal_script", ...]
└── built_in_templates (预置模板库)
    ├── ancient_chinese (中文古籍)
    ├── archive_document (档案文献)
    ├── modern_publication (现代出版物)
    ├── gothic_german (哥特体德文)
    ├── manuscript (手稿)
    ├── academic_paper (学术论文)
    └── mixed_content (混合内容)
```

### 2.2 基础模板 (Base Template)

完整的 Marker 语法规范提示词，包含所有 32+ 块类型的说明。

### 2.3 参数化系统

#### 核心参数

1. **text_direction** (文本方向)
   - `horizontal`: 横排文本（现代出版物）
   - `vertical`: 竖排文本（古籍、部分日文）
   - `mixed`: 混合排版

2. **has_footnotes** (是否有脚注)
   - `true`: 启用脚注识别指导
   - `false`: 不特别强调脚注

3. **has_references** (是否有引文/参考文献)
   - `true`: 识别引用标记和参考文献列表
   - `false`: 普通文本处理

4. **has_handwriting** (是否有手写内容)
   - `true`: 启用手写文本识别指导
   - `false`: 仅印刷体

5. **language_mode** (语言模式)
   - `monolingual`: 单一语言
   - `multilingual`: 多语言混合（如中英混排）

6. **primary_language** (主要语言)
   - `zh`: 中文
   - `en`: 英文
   - `de`: 德文
   - `ja`: 日文
   - `la`: 拉丁文
   - ...

7. **document_era** (文档年代)
   - `ancient`: 古代文献（特殊字体、繁体字）
   - `modern`: 近现代（简体/标准字体）
   - `contemporary`: 当代（现代排版）

8. **has_page_numbers** (是否有页码)
   - `true`: 识别并保留页码
   - `false`: 忽略页码

9. **has_headers_footers** (是否有页眉页脚)
   - `true`: 识别页眉页脚
   - `false`: 忽略

10. **special_features** (特殊特征)
    - `gothic_script`: 哥特体
    - `seal_script`: 篆书
    - `cursive`: 草书
    - `seals_stamps`: 印章
    - `annotations`: 批注
    - `damage_stains`: 破损/污渍
    - ...

### 2.4 预置模板库

#### Template 1: 中文古籍 (Ancient Chinese Texts)
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

**特殊指导**:
- 竖排文本，从右到左阅读
- 识别繁体字和异体字
- 注意句读符号（。、，）
- 识别夹注和小字注释为脚注
- 识别印章和题跋

#### Template 2: 档案文献 (Archive Documents)
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

**特殊指导**:
- 混合印刷体和手写体
- 识别公章和签名
- 保留文档编号和日期
- 注意破损和模糊区域

#### Template 3: 现代出版物 (Modern Publications)
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

**特殊指导**:
- 标准横排，现代标点
- 脚注通常在页面底部，字号较小
- 可能包含中英文混排
- 识别图表标题和引用

#### Template 4: 哥特体德文 (Gothic German)
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

**特殊指导**:
- 识别 Fraktur 字体
- 注意长 s (ſ) 和短 s (s) 的区别
- 识别德文特殊字符 (ä, ö, ü, ß)

#### Template 5: 手稿 (Manuscripts)
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

**特殊指导**:
- 全手写内容
- 识别删除线和修改
- 识别边注和批注
- 容忍不规则排版

#### Template 6: 学术论文 (Academic Papers)
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

**特殊指导**:
- 严格的结构化格式
- 大量数学公式和表格
- 脚注和尾注
- 参考文献列表
- 图表标题

#### Template 7: 混合内容 (Mixed Content)
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

**特殊指导**:
- 最大灵活性
- 识别所有可能的文档元素
- 适应混合排版

## 3. 实现方案 (Implementation Plan)

### 3.1 文件结构

```
marker/
├── prompts/
│   ├── __init__.py
│   ├── base.py              # 基础模板类
│   ├── templates.py         # 预置模板库
│   └── builder.py           # 提示词构建器
├── converters/
│   └── vlm_direct_async.py  # 修改以支持模板系统
└── scripts/
    └── streamlit_app.py     # UI 支持模板选择
```

### 3.2 核心类设计

#### VlmPromptTemplate (基类)
```python
class VlmPromptTemplate:
    def __init__(self, **params):
        self.params = params

    def build(self) -> str:
        """构建完整提示词"""
        pass

    def get_base_syntax(self) -> str:
        """获取基础 Marker 语法说明"""
        pass

    def get_special_instructions(self) -> str:
        """根据参数生成特殊指导"""
        pass
```

#### PromptBuilder (构建器)
```python
class PromptBuilder:
    @staticmethod
    def from_template(template_name: str) -> VlmPromptTemplate:
        """从预置模板创建"""
        pass

    @staticmethod
    def from_params(**params) -> VlmPromptTemplate:
        """从参数创建自定义模板"""
        pass
```

### 3.3 集成到 VlmDirectAsyncConverter

```python
class VlmDirectAsyncConverter(BaseConverter):
    # 新增配置
    vlm_direct_prompt_template: str = "modern_publication"  # 模板名称
    vlm_direct_prompt_params: dict = {}  # 自定义参数

    def __init__(self, config):
        # ...
        # 构建提示词
        if config.get("vlm_direct_prompt_params"):
            self.prompt_template = PromptBuilder.from_params(
                **config["vlm_direct_prompt_params"]
            )
        else:
            self.prompt_template = PromptBuilder.from_template(
                config.get("vlm_direct_prompt_template", "modern_publication")
            )

        self.prompt = self.prompt_template.build()
```

### 3.4 Streamlit UI 集成

```python
# 模板选择
template_options = {
    "现代出版物": "modern_publication",
    "中文古籍": "ancient_chinese",
    "档案文献": "archive_document",
    "哥特体德文": "gothic_german",
    "手稿": "manuscript",
    "学术论文": "academic_paper",
    "混合内容": "mixed_content",
    "自定义": "custom"
}

selected_template = st.selectbox("选择文档类型模板", list(template_options.keys()))

if selected_template == "自定义":
    # 显示参数配置界面
    text_direction = st.selectbox("文本方向", ["horizontal", "vertical", "mixed"])
    has_footnotes = st.checkbox("包含脚注", value=True)
    # ... 更多参数
```

## 4. 脚注识别优化 (Footnote Recognition)

### 当前问题
VLM 将脚注误识别为缩进文本，因为：
1. 提示词中没有明确说明脚注的特征
2. 没有提供脚注的 Markdown 语法示例
3. 没有强调脚注的位置和格式特征

### 解决方案

在提示词中添加详细的脚注识别指导：

```markdown
## 脚注识别 (Footnote Recognition) - 重要!

脚注是对正文的补充说明，通常具有以下特征：

### 位置特征
- 通常位于页面底部
- 与正文之间有分隔线或空白
- 可能在页边（边注）

### 格式特征
- 字号通常小于正文
- 可能有编号或符号标记（[1], *, †, ‡）
- 可能有缩进，但缩进不是脚注的唯一特征

### Markdown 语法
正文中的引用：
```
这是正文内容[^1]，继续正文。
```

脚注定义（通常在页面底部）：
```
[^1]: 这是脚注的详细说明内容。
```

### 识别规则
1. **不要**仅因为文本有缩进就认为是脚注
2. **要**综合考虑位置、字号、标记等特征
3. **要**识别脚注编号和对应的正文引用
4. **要**将脚注与正文分开标记

### 示例

错误识别：
```markdown
正文内容
    这是缩进的段落（被误认为脚注）
```

正确识别：
```markdown
正文内容[^1]

[^1]: 这是真正的脚注，位于页面底部，字号较小
```
```

## 5. 优势分析 (Advantages)

### 5.1 灵活性
- 参数化设计支持任意组合
- 预置模板覆盖常见场景
- 自定义模板满足特殊需求

### 5.2 准确性
- 完整的 Marker 语法规范
- 针对性的文档类型指导
- 详细的脚注识别规则

### 5.3 可扩展性
- 易于添加新模板
- 易于添加新参数
- 易于集成到现有系统

### 5.4 用户友好
- Streamlit UI 提供直观的模板选择
- 预置模板开箱即用
- 高级用户可自定义参数

## 6. 实现步骤 (Implementation Steps)

1. **创建基础模板类** (`marker/prompts/base.py`)
   - 定义 `VlmPromptTemplate` 基类
   - 实现完整的 Marker 语法说明
   - 实现参数化指导生成

2. **创建预置模板库** (`marker/prompts/templates.py`)
   - 实现 7 个预置模板
   - 每个模板包含参数配置和特殊指导

3. **创建提示词构建器** (`marker/prompts/builder.py`)
   - 实现 `PromptBuilder` 类
   - 支持从模板名称或参数创建

4. **修改 VlmDirectAsyncConverter**
   - 添加模板配置参数
   - 集成 `PromptBuilder`
   - 保持向后兼容（默认使用 `modern_publication` 模板）

5. **更新 Streamlit UI**
   - 添加模板选择下拉框
   - 添加自定义参数配置界面
   - 显示当前使用的提示词（可选）

6. **测试和优化**
   - 使用不同类型文档测试
   - 重点测试脚注识别
   - 根据结果优化提示词

## 7. 向后兼容性 (Backward Compatibility)

- 保留 `vlm_direct_prompt` 参数，允许直接指定提示词
- 如果未指定模板，默认使用 `modern_publication`
- 现有代码无需修改即可继续工作

## 8. 未来扩展 (Future Extensions)

- **动态提示词优化**: 根据 VLM 输出质量自动调整提示词
- **多模型适配**: 针对不同 VLM（GPT-4V, Gemini, Qwen）优化提示词
- **用户反馈学���**: 收集用户反馈，持续改进模板
- **提示词版本管理**: 支持提示词版本控制和 A/B 测试

---

## 审查要点 (Review Checklist)

请审查以下方面：

- [ ] 参数设计是否合理？是否有遗漏的重要参数？
- [ ] 预置模板是否覆盖您的使用场景？
- [ ] 脚注识别方案是否能解决当前问题？
- [ ] 实现方案是否清晰可行？
- [ ] 是否有其他需要考虑的文档类型或特征？

**请提供您的反馈，我将根据您的意见调整设计方案，然后开始实现。**
