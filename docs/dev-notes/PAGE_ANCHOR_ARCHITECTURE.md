# 页码锚点架构分析与可编程性设计

## 一、当前架构概览

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Streamlit UI)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户配置:                                                       │
│  • 锚点模板: {n}, {n1}, {printed}, {printed-or-n1}, ...       │
│  • 页序起始值: 0 或 1                                           │
│  • 锚点位置: before/after/both                                  │
│  • 提取印刷页码: 是/否                                          │
│                                                                 │
│  ↓ 配置传递                                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    后端核心组件 (formatters.py)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐  ┌──────────────────────┐           │
│  │ PageAnchorFormatter  │  │  PageAnchorPlugin    │           │
│  │  (格式化器)          │  │   (插件)             │           │
│  │                      │  │                      │           │
│  │ • template           │  │ • formatter          │           │
│  │ • page_anchor_start  │  │ • enabled            │           │
│  │ • wrapper            │  │ • position           │           │
│  │                      │  │ • separator          │           │
│  │ format(idx, printed) │  │ wrap_page_content()  │           │
│  └──────────────────────┘  └──────────────────────┘           │
│                                                                 │
│  ┌──────────────────────┐                                      │
│  │ PrintedPageExtractor │                                      │
│  │  (印刷页码提取器)    │                                      │
│  │                      │                                      │
│  │ • patterns           │                                      │
│  │ • remove_from_content│                                      │
│  │                      │                                      │
│  │ extract(content)     │                                      │
│  └──────────────────────┘                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        转换器层                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐      ┌─────────────────────┐         │
│  │ VlmDirectConverter  │      │   PdfConverter      │         │
│  │  (纯 VLM 模式)      │      │  (Pipeline 模式)    │         │
│  │                     │      │                     │         │
│  │ ✅ 使用 Plugin      │      │ ✅ 使用 Formatter   │         │
│  │ ✅ 使用 Extractor   │      │ ✅ 通过 Renderer    │         │
│  │                     │      │                     │         │
│  └─────────────────────┘      └─────────────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 二、前后端逻辑详解

### 2.1 前端配置 (Streamlit UI)

#### VLM Direct 模式配置

**位置**: `marker/scripts/streamlit_app.py` 行 583-658

```python
# 页码锚点配置
with st.expander("📍 页码锚点配置", expanded=False):
    vlm_direct_enable_page_anchors = st.checkbox(
        "启用页码锚点",
        value=True,
        key="vlm_direct_enable_page_anchors"
    )

    if vlm_direct_enable_page_anchors:
        # 锚点模板选择
        vlm_direct_page_anchor_template = st.selectbox(
            "锚点模板",
            options=["{n}", "{n1}", "{printed}", "{printed-or-n1}", "{printed} ({n1})"],
            index=1,  # 默认 {n1}
            key="vlm_direct_page_anchor_template"
        )

        # 页序起始值
        vlm_direct_page_anchor_start = st.number_input(
            "页序起始值",
            min_value=0,
            max_value=1,
            value=0,
            key="vlm_direct_page_anchor_start"
        )

        # 锚点位置
        vlm_direct_page_anchor_position = st.radio(
            "锚点位置",
            options=["before", "after", "both"],
            index=0,
            key="vlm_direct_page_anchor_position"
        )

        # 提取印刷页码
        vlm_direct_extract_printed_pages = st.checkbox(
            "从 VLM 输出提取印刷页码",
            value=True,
            key="vlm_direct_extract_printed_pages"
        )
```

#### Pipeline 模式配置

**位置**: `marker/scripts/streamlit_app.py` 行 1244-1323

```python
# 页码设置
st.subheader("📄 页码设置")
with st.expander("页码配置", expanded=False):
    # 页锚点模板
    page_anchor_template = st.selectbox(
        "页锚点模板",
        options=["{n}", "{n1}", "{printed}", "{printed-or-n1}", "{printed} ({n1})"],
        index=1,  # 默认 {n1}
    )

    # 页序起始值
    page_anchor_start = st.number_input(
        "页序起始值",
        min_value=0,
        max_value=1,
        value=0,
    )

    # 印刷页码识别
    printed_page_enabled = st.checkbox(
        "启用印刷页码识别",
        value=False,
    )
```

### 2.2 后端核心组件

#### PageAnchorFormatter (格式化器)

**位置**: `marker/formatters.py` 行 10-106

**职责**: 将页码信息格式化为锚点字符串

**关键参数**:
```python
def __init__(self,
             template: str = "{n1}",           # 模板
             page_anchor_start: int = 0,       # 起始值
             wrapper: str = "{{{}}}"):         # 包装格式
```

**核心方法**:
```python
def format(self, page_index: int, printed_page_id: Optional[str] = None) -> str:
    """
    格式化页锚点

    Args:
        page_index: 0-based 页序（从 0 开始）
        printed_page_id: 印刷页码（可选）

    Returns:
        格式化后的锚点字符串，如 "{5}" 或 "{XII}"
    """
    n = page_index
    n1 = page_index + self.page_anchor_start
    printed = printed_page_id or ""
    printed_or_n1 = printed_page_id if printed_page_id else str(n1)

    result = self.template
    result = result.replace("{printed-or-n1}", printed_or_n1)
    result = result.replace("{n}", str(n))
    result = result.replace("{n1}", str(n1))
    result = result.replace("{printed}", printed)

    if self.wrapper:
        result = self.wrapper.format(result)

    return result
```

**逻辑说明**:

1. **page_index**: 始终是 0-based（从 0 开始）
2. **n**: 直接使用 page_index（0, 1, 2, ...）
3. **n1**: page_index + page_anchor_start
   - 如果 page_anchor_start = 0: n1 = 0, 1, 2, ...
   - 如果 page_anchor_start = 1: n1 = 1, 2, 3, ...
4. **printed**: 印刷页码（如果有）
5. **printed_or_n1**: 优先使用 printed，否则使用 n1

**示例**:

```python
formatter = PageAnchorFormatter(template="{n1}", page_anchor_start=0)

# 第一页（page_index=0）
formatter.format(0)  # → "{0}"

# 第二页（page_index=1）
formatter.format(1)  # → "{1}"

# 带印刷页码
formatter.format(0, "XII")  # → "{0}" (因为模板是 {n1}，不是 {printed})

formatter2 = PageAnchorFormatter(template="{printed-or-n1}", page_anchor_start=0)
formatter2.format(0, "XII")  # → "{XII}"
formatter2.format(1, None)   # → "{1}"
```

#### PageAnchorPlugin (插件)

**位置**: `marker/formatters.py` 行 109-180

**职责**: 将锚点插入到页面内容中

**关键参数**:
```python
def __init__(self,
             formatter: Optional[PageAnchorFormatter] = None,
             enabled: bool = True,
             position: str = "before",  # "before", "after", "both"
             separator: str = "\n\n"):
```

**核心方法**:
```python
def wrap_page_content(self, page_index: int, content: str,
                     printed_page_id: Optional[str] = None) -> str:
    """为页面内容添加锚点"""
    if not self.enabled:
        return content

    anchor = self.formatter.format(page_index, printed_page_id)

    if self.position == "before":
        return f"{anchor}{self.separator}{content}"
    elif self.position == "after":
        return f"{content}{self.separator}{anchor}"
    elif self.position == "both":
        return f"{anchor}{self.separator}{content}{self.separator}{anchor}"
    else:
        return content
```

#### PrintedPageExtractor (印刷页码提取器)

**位置**: `marker/formatters.py` 行 183-248

**职责**: 从 VLM 输出中提取印刷页码

**支持的标记格式**:
```python
patterns = [
    r'<!--\s*printed-page:\s*([^\s]+)\s*-->',  # <!-- printed-page: XII -->
    r'<!--\s*page:\s*([^\s]+)\s*-->',          # <!-- page: 308 -->
    r'\[页码:\s*([^\]]+)\]',                    # [页码: 12]
]
```

### 2.3 转换器层实现

#### VLM Direct 模式

**位置**: `marker/converters/vlm_direct_async.py`

**初始化**:
```python
def __init__(self, config: Optional[dict] = None):
    # ... 其他配置 ...

    # 页码锚点配置
    enable_anchors = config.get("vlm_direct_enable_page_anchors", True)
    anchor_template = config.get("vlm_direct_page_anchor_template", "{n}")
    anchor_start = int(config.get("vlm_direct_page_anchor_start", 0))
    anchor_wrapper = config.get("vlm_direct_page_anchor_wrapper", "{{{}}}")
    anchor_position = config.get("vlm_direct_page_anchor_position", "before")
    self.extract_printed_pages = config.get("vlm_direct_extract_printed_pages", True)

    # 初始化页码锚点插件
    formatter = PageAnchorFormatter(
        template=anchor_template,
        page_anchor_start=anchor_start,
        wrapper=anchor_wrapper
    )
    self.page_anchor_plugin = PageAnchorPlugin(
        formatter=formatter,
        enabled=enable_anchors,
        position=anchor_position,
        separator="\n\n"
    )

    # 初始化印刷页码提取器
    self.printed_page_extractor = PrintedPageExtractor() if self.extract_printed_pages else None
```

**处理流程**:
```python
def __call__(self, filepath: str) -> str:
    # 1. 加载文档
    # 2. 获取所有页面图像
    # 3. 异步并发转换
    markdown_pages = asyncio.run(self._convert_all_pages_async(images))

    # 4. 提取印刷页码（如果启用）
    printed_pages = None
    if self.printed_page_extractor:
        markdown_pages, printed_pages = self.printed_page_extractor.extract_batch(markdown_pages)

    # 5. 清理页面分隔符（避免嵌套）
    markdown_pages = self._clean_page_separators(markdown_pages)

    # 6. 添加页码锚点（如果启用）
    if self.page_anchor_plugin.enabled:
        markdown_pages = self.page_anchor_plugin.process_pages(markdown_pages, printed_pages)

    # 7. 拼接所有页面
    full_markdown = self.page_separator.join(markdown_pages)

    return full_markdown
```

#### Pipeline 模式

**位置**: `marker/converters/pdf.py` + `marker/renderers/markdown.py`

**初始化**:
```python
# PdfConverter 配置
config = {
    "page_anchor_template": "{printed-or-n1}",
    "page_anchor_start": 1,
    "paginate_output": True,
}

# MarkdownRenderer 使用
renderer = MarkdownRenderer(
    page_anchor_template=config["page_anchor_template"],
    page_anchor_start=config["page_anchor_start"],
    paginate_output=config["paginate_output"]
)
```

**处理流程**:
```python
# 在 MarkdownRenderer 中
formatter = PageAnchorFormatter(
    template=self.page_anchor_template,
    page_anchor_start=self.page_anchor_start
)

# 在渲染时
page_anchor = formatter.format(page_id, printed_page_id)
pagination_item = "\n\n" + "{" + page_anchor + "}" + self.page_separator + "\n\n"
```

## 三、统一性分析

### 3.1 已统一的部分 ✅

| 组件 | VLM Direct | Pipeline | 统一性 |
|------|-----------|----------|--------|
| **PageAnchorFormatter** | ✅ 使用 | ✅ 使用 | ✅ 完全统一 |
| **模板系统** | ✅ 5种模板 | ✅ 5种模板 | ✅ 完全统一 |
| **page_anchor_start** | ✅ 支持 | ✅ 支持 | ✅ 完全统一 |
| **wrapper 格式** | ✅ 可配置 | ✅ 固定 `{{{}}}` | ⚠️ 部分统一 |
| **锚点格式** | `{X}` | `{X}` | ✅ 完全统一 |

### 3.2 未统一的部分 ⚠️

| 特性 | VLM Direct | Pipeline | 差异 |
|------|-----------|----------|------|
| **锚点位置** | 可配置 (before/after/both) | 固定 before | ⚠️ VLM 更灵活 |
| **印刷页码获取** | VLM 提取 | 自动识别 | ⚠️ 方法不同 |
| **插件架构** | 使用 PageAnchorPlugin | 直接在 Renderer 中 | ⚠️ 架构不同 |
| **配置参数名** | `vlm_direct_*` | `page_anchor_*` | ⚠️ 命名不同 |

### 3.3 统一性评分

**核心逻辑统一度**: ⭐⭐⭐⭐⭐ (5/5)
- 两种模式使用相同的 `PageAnchorFormatter`
- 格式化逻辑完全一致
- 输出格式完全兼容

**配置接口统一度**: ⭐⭐⭐☆☆ (3/5)
- 参数名不同（`vlm_direct_*` vs `page_anchor_*`）
- 配置位置不同（不同的 expander）
- 但配置项基本对应

**架构统一度**: ⭐⭐⭐☆☆ (3/5)
- VLM Direct 使用插件架构
- Pipeline 直接在 Renderer 中处理
- 但底层都使用 Formatter

## 四、可编程性设计

### 4.1 当前可编程性

#### 模板可编程 ✅

**支持的变量**:
```python
{n}              # 0-based 页序
{n1}             # 1-based 页序
{printed}        # 印刷页码
{printed-or-n1}  # 优先印刷页码
{printed} ({n1}) # 组合显示
```

**自定义模板示例**:
```python
# 学术引用格式
template = "p.{n1}"  # → {p.1}, {p.2}, ...

# 档案馆格式
template = "档案-{printed-or-n1}"  # → {档案-308}, {档案-1}, ...

# 章节-页码格式
template = "Ch1-{n1}"  # → {Ch1-1}, {Ch1-2}, ...
```

#### 包装格式可编程 ✅

**支持的包装**:
```python
wrapper = "{{{}}}"   # → {5}
wrapper = "[{}]"     # → [5]
wrapper = "<{}>"     # → <5>
wrapper = "Page {}"  # → Page 5
wrapper = None       # → 5 (无包装)
```

#### 位置可编程 ✅ (仅 VLM Direct)

```python
position = "before"  # 页面前
position = "after"   # 页面后
position = "both"    # 页面前后
```

### 4.2 可编程性增强建议

#### 建议 1: 统一配置接口

**目标**: 让两种模式使用相同的配置参数名

**实现**:
```python
# 统一的配置键
UNIFIED_CONFIG = {
    "page_anchor_enabled": True,
    "page_anchor_template": "{printed-or-n1}",
    "page_anchor_start": 1,
    "page_anchor_wrapper": "{{{}}}",
    "page_anchor_position": "before",
    "page_anchor_extract_printed": True,
}

# VLM Direct 使用
vlm_config = UNIFIED_CONFIG.copy()

# Pipeline 使用
pdf_config = UNIFIED_CONFIG.copy()
```

#### 建议 2: 自定义格式化函数

**目标**: 允许用户提供自定义格式化逻辑

**实现**:
```python
class PageAnchorFormatter:
    def __init__(self,
                 template: str = "{n1}",
                 page_anchor_start: int = 0,
                 wrapper: str = "{{{}}}",
                 custom_formatter: Optional[Callable] = None):  # 新增
        self.custom_formatter = custom_formatter
        # ...

    def format(self, page_index: int, printed_page_id: Optional[str] = None) -> str:
        # 如果提供了自定义格式化函数，优先使用
        if self.custom_formatter:
            return self.custom_formatter(page_index, printed_page_id, self.page_anchor_start)

        # 否则使用默认逻辑
        # ...
```

**使用示例**:
```python
def my_formatter(page_index, printed_page_id, start):
    """自定义格式化：章节-页码"""
    chapter = (page_index // 10) + 1
    page_in_chapter = (page_index % 10) + 1
    return f"{{Ch{chapter}-{page_in_chapter}}}"

formatter = PageAnchorFormatter(custom_formatter=my_formatter)
formatter.format(0)   # → {Ch1-1}
formatter.format(10)  # → {Ch2-1}
formatter.format(15)  # → {Ch2-6}
```

#### 建议 3: 配置文件支持

**目标**: 支持从配置文件加载页码锚点设置

**实现**:
```yaml
# page_anchor_config.yaml
page_anchor:
  enabled: true
  template: "{printed-or-n1}"
  start: 1
  wrapper: "{{{}}}"
  position: "before"
  extract_printed: true

  # 自定义模板（高级）
  custom_templates:
    humanities: "{printed-or-n1}"
    technical: "{n}"
    archive: "档案-{printed-or-n1}"
```

```python
import yaml

def load_page_anchor_config(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config['page_anchor']

# 使用
config = load_page_anchor_config("page_anchor_config.yaml")
formatter = PageAnchorFormatter(
    template=config['template'],
    page_anchor_start=config['start'],
    wrapper=config['wrapper']
)
```

#### 建议 4: 插件注册机制

**目标**: 允许用户注册自定义页码锚点插件

**实现**:
```python
class PageAnchorPluginRegistry:
    """页码锚点插件注册表"""

    _plugins = {}

    @classmethod
    def register(cls, name: str, plugin_class):
        """注册插件"""
        cls._plugins[name] = plugin_class

    @classmethod
    def get(cls, name: str):
        """获取插件"""
        return cls._plugins.get(name)

    @classmethod
    def list(cls):
        """列出所有插件"""
        return list(cls._plugins.keys())

# 注册默认插件
PageAnchorPluginRegistry.register("default", PageAnchorPlugin)

# 用户自定义插件
class MyCustomPlugin(PageAnchorPlugin):
    def wrap_page_content(self, page_index, content, printed_page_id=None):
        # 自定义逻辑
        anchor = f"[Page {page_index + 1}]"
        return f"{anchor}\n\n{content}"

# 注册自定义插件
PageAnchorPluginRegistry.register("my_custom", MyCustomPlugin)

# 使用
plugin_class = PageAnchorPluginRegistry.get("my_custom")
plugin = plugin_class(formatter=formatter)
```

#### 建议 5: API 编程接口

**目标**: 提供 Python API 供编程使用

**实现**:
```python
from marker.formatters import PageAnchorFormatter, PageAnchorPlugin

# 方式 1: 直接使用 Formatter
formatter = PageAnchorFormatter(
    template="{printed-or-n1}",
    page_anchor_start=1,
    wrapper="{{{}}}"
)

pages = ["内容1", "内容2", "内容3"]
printed_pages = ["XII", None, "XIV"]

for idx, (page, printed) in enumerate(zip(pages, printed_pages)):
    anchor = formatter.format(idx, printed)
    print(f"{anchor}\n\n{page}\n")

# 方式 2: 使用 Plugin
plugin = PageAnchorPlugin(
    formatter=formatter,
    enabled=True,
    position="before",
    separator="\n\n"
)

processed_pages = plugin.process_pages(pages, printed_pages)
result = "\n\n---\n\n".join(processed_pages)
print(result)

# 方式 3: 使用 Converter
from marker.converters.vlm_direct_async import VlmDirectAsyncConverter

config = {
    "vlm_direct_enable_page_anchors": True,
    "vlm_direct_page_anchor_template": "{printed-or-n1}",
    "vlm_direct_page_anchor_start": 1,
    # ... 其他配置
}

converter = VlmDirectAsyncConverter(config)
markdown = converter("document.pdf")
```

## 五、向后兼容性

### 5.1 兼容性保证

#### 默认行为兼容 ✅

```python
# 不提供配置时，使用默认值
formatter = PageAnchorFormatter()  # template="{n1}", start=0, wrapper="{{{}}}"
plugin = PageAnchorPlugin()        # enabled=True, position="before"
```

#### 配置向后兼容 ✅

```python
# 旧配置（Pipeline 模式）
old_config = {
    "page_anchor_template": "{n1}",
    "page_anchor_start": 0,
}

# 新配置（VLM Direct 模式）
new_config = {
    "vlm_direct_page_anchor_template": "{n1}",
    "vlm_direct_page_anchor_start": 0,
}

# 两者都能正常工作
```

#### 输出格式兼容 ✅

```python
# 两种模式输出相同格式的锚点
# VLM Direct: {0}, {1}, {2}, ...
# Pipeline:   {0}, {1}, {2}, ...
```

### 5.2 迁移路径

#### 从 Pipeline 迁移到 VLM Direct

```python
# Pipeline 配置
pipeline_config = {
    "page_anchor_template": "{printed-or-n1}",
    "page_anchor_start": 1,
    "paginate_output": True,
}

# 转换为 VLM Direct 配置
vlm_config = {
    "vlm_direct_enable_page_anchors": pipeline_config["paginate_output"],
    "vlm_direct_page_anchor_template": pipeline_config["page_anchor_template"],
    "vlm_direct_page_anchor_start": pipeline_config["page_anchor_start"],
    "vlm_direct_page_anchor_wrapper": "{{{}}}",  # 默认
    "vlm_direct_page_anchor_position": "before",  # 默认
}
```

## 六、总结

### 6.1 当前状态

✅ **核心逻辑已统一**: 两种模式使用相同的 `PageAnchorFormatter`
✅ **输出格式已统一**: 生成相同格式的页码锚点
✅ **基本可编程**: 支持模板、包装、位置配置
⚠️ **配置接口未统一**: 参数名不同
⚠️ **架构部分统一**: VLM 使用插件，Pipeline 直接处理

### 6.2 可编程性评分

**当前可编程性**: ⭐⭐⭐⭐☆ (4/5)
- ✅ 模板可编程
- ✅ 包装可编程
- ✅ 位置可编程（VLM）
- ✅ Python API 可用
- ❌ 自定义函数不支持

**向后兼容性**: ⭐⭐⭐⭐⭐ (5/5)
- ✅ 默认行为兼容
- ✅ 配置向后兼容
- ✅ 输出格式兼容
- ✅ 迁移路径清晰

### 6.3 改进建议优先级

1. **高优先级**: 统一配置接口（参数名）
2. **中优先级**: 支持自定义格式化函数
3. **中优先级**: 配置文件支持
4. **低优先级**: 插件注册机制

### 6.4 最佳实践

**人文学科/档案馆推荐配置**:
```python
{
    "page_anchor_template": "{printed-or-n1}",
    "page_anchor_start": 1,
    "page_anchor_wrapper": "{{{}}}",
    "page_anchor_position": "before",
    "extract_printed": True,
}
```

**技术文档推荐配置**:
```python
{
    "page_anchor_template": "{n}",
    "page_anchor_start": 0,
    "page_anchor_wrapper": "[{}]",
    "page_anchor_position": "before",
    "extract_printed": False,
}
```

这个架构为"兰台·PageAnchor"项目提供了坚实的基础，既保证了统一性，又提供了足够的可编程性和扩展性。
