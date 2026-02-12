# 页码锚点系统增强方案

## 📋 需求分析

### 当前功能
页码锚点系统目前支持以下模板变量：
- `{n}`: 0-based 页序（0, 1, 2...）
- `{n1}`: 1-based 页序（1, 2, 3...）
- `{printed}`: 印刷页码（XII, 308...）
- `{printed-or-n1}`: 优先印刷页码，否则 1-based

### 新增需求
1. **支持自定义档案编号**：如 `sc001`, `sc002`, `档-001` 等
2. **更灵活的模板语法**：支持更多变量和组合
3. **全局统一**：在 VLM Direct 和 Pipeline 两种模式中都能使用
4. **多种编号源**：支持从多个来源获取自定义编号

---

## 🎯 设计方案

### 1. 扩展 PageAnchorFormatter

#### 新增模板变量
```python
{n}              # 0-based 页序（0, 1, 2...）
{n1}             # 1-based 页序（1, 2, 3...）
{printed}        # 印刷页码（XII, 308...）
{custom}         # 自定义编号（sc001, 档-001...）
{printed-or-n1}  # 优先印刷页码，否则 1-based
{custom-or-n1}   # 优先自定义编号，否则 1-based
{custom-or-printed-or-n1}  # 优先级：自定义 > 印刷 > 1-based
```

#### 模板示例
```python
# 基础模板
"{n1}"                    # 输出: {1}, {2}, {3}
"{custom}"                # 输出: {sc001}, {sc002}, {sc003}

# 组合模板
"{custom} (p.{n1})"       # 输出: {sc001 (p.1)}, {sc002 (p.2)}
"{printed} [{custom}]"    # 输出: {XII [sc001]}, {308 [sc002]}

# 优先级模板
"{custom-or-n1}"          # 有自定义编号用自定义，否则用 1-based
"{custom-or-printed-or-n1}"  # 三级优先级
```

### 2. 新增 CustomIDExtractor

类似于 `PrintedPageExtractor`，用于从多种来源提取自定义编号。

#### 支持的编号来源

**来源 1：VLM 输出中的标记**
```markdown
<!-- custom-id: sc001 -->
页面内容...
```

**来源 2：用户提供的映射文件（CSV）**
```csv
page_index,custom_id
0,sc001
1,sc002
2,sc003
```

**来源 3：用户提供的映射文件（JSON）**
```json
{
  "0": "sc001",
  "1": "sc002",
  "2": "sc003"
}
```

**来源 4：UI 中手动输入**
```python
# 用户在 UI 中输入逗号分隔的列表
"sc001, sc002, sc003, sc004"
```

**来源 5：自动生成模式**
```python
# 用户指定前缀和起始编号
prefix = "sc"
start = 1
padding = 3
# 自动生成: sc001, sc002, sc003...
```

### 3. 实现架构

```
┌─────────────────────────────────────────────────────────────┐
│                    页码锚点系统架构                          │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  编号源管理器     │
│ IDSourceManager  │
└────────┬─────────┘
         │
         ├─── PDF 页码（page_index）
         ├─── 印刷页码（PrintedPageExtractor）
         └─── 自定义编号（CustomIDExtractor）
                │
                ├─── VLM 输出标记
                ├─── CSV/JSON 文件
                ├─── UI 手动输入
                └─── 自动生成

         ↓

┌──────────────────┐
│  页锚点格式化器   │
│PageAnchorFormatter│
└────────┬─────────┘
         │
         ├─── 模板解析
         ├─── 变量替换
         └─── 优先级处理

         ↓

┌──────────────────┐
│  页锚点插件       │
│ PageAnchorPlugin │
└────────┬─────────┘
         │
         ├─── VLM Direct 模式
         └─── Pipeline 模式

         ↓

┌──────────────────┐
│  最终输出         │
│  {sc001 (p.1)}   │
└──────────────────┘
```

---

## 🔧 实现细节

### 1. CustomIDExtractor 类

```python
class CustomIDExtractor:
    """
    自定义编号提取器

    支持从多种来源提取自定义页面编号：
    - VLM 输出中的标记
    - CSV/JSON 文件
    - 用户手动输入的列表
    - 自动生成模式
    """

    def __init__(self,
                 source_type: str = "vlm",  # "vlm" | "csv" | "json" | "list" | "auto"
                 source_data: Optional[Any] = None,
                 auto_prefix: str = "page",
                 auto_start: int = 1,
                 auto_padding: int = 3):
        """
        Args:
            source_type: 编号来源类型
            source_data: 来源数据（文件路径、列表等）
            auto_prefix: 自动生成模式的前缀
            auto_start: 自动生成模式的起始编号
            auto_padding: 自动生成模式的补零位数
        """
        pass

    def extract(self, content: str, page_index: int) -> tuple[str, Optional[str]]:
        """
        从内容中提取自定义编号

        Args:
            content: 页面内容（Markdown）
            page_index: 页面索引

        Returns:
            (处理后的内容, 自定义编号)
        """
        pass

    def extract_batch(self, contents: list) -> tuple[list, list]:
        """批量提取自定义编号"""
        pass
```

### 2. 增强 PageAnchorFormatter

```python
class PageAnchorFormatter:
    def __init__(self,
                 template: str = "{n1}",
                 page_anchor_start: int = 0,
                 wrapper: str = "{{{}}}"):
        self.template = template
        self.page_anchor_start = page_anchor_start
        self.wrapper = wrapper

    def format(self,
               page_index: int,
               printed_page_id: Optional[str] = None,
               custom_id: Optional[str] = None) -> str:
        """
        格式化页锚点（增强版）

        Args:
            page_index: 0-based 页序
            printed_page_id: 印刷页码
            custom_id: 自定义编号（新增）

        Returns:
            格式化后的锚点字符串
        """
        n = page_index
        n1 = page_index + self.page_anchor_start
        printed = printed_page_id or ""
        custom = custom_id or ""

        # 优先级处理
        printed_or_n1 = printed_page_id if printed_page_id else str(n1)
        custom_or_n1 = custom_id if custom_id else str(n1)
        custom_or_printed_or_n1 = custom_id if custom_id else (printed_page_id if printed_page_id else str(n1))

        result = self.template
        # 按优先级替换（长的先替换，避免误替换）
        result = result.replace("{custom-or-printed-or-n1}", custom_or_printed_or_n1)
        result = result.replace("{custom-or-n1}", custom_or_n1)
        result = result.replace("{printed-or-n1}", printed_or_n1)
        result = result.replace("{n}", str(n))
        result = result.replace("{n1}", str(n1))
        result = result.replace("{printed}", printed)
        result = result.replace("{custom}", custom)

        # 应用包装格式
        if self.wrapper:
            result = self.wrapper.format(result)

        return result
```

### 3. 增强 PageAnchorPlugin

```python
class PageAnchorPlugin:
    def __init__(self,
                 formatter: Optional[PageAnchorFormatter] = None,
                 enabled: bool = True,
                 position: str = "before",
                 separator: str = "\n\n"):
        self.formatter = formatter or PageAnchorFormatter()
        self.enabled = enabled
        self.position = position
        self.separator = separator

    def wrap_page_content(self,
                         page_index: int,
                         content: str,
                         printed_page_id: Optional[str] = None,
                         custom_id: Optional[str] = None) -> str:
        """
        为页面内容添加锚点（增强版）

        Args:
            page_index: 0-based 页序
            content: 页面内容
            printed_page_id: 印刷页码
            custom_id: 自定义编号（新增）
        """
        if not self.enabled:
            return content

        anchor = self.formatter.format(page_index, printed_page_id, custom_id)

        if self.position == "before":
            return f"{anchor}{self.separator}{content}"
        elif self.position == "after":
            return f"{content}{self.separator}{anchor}"
        elif self.position == "both":
            return f"{anchor}{self.separator}{content}{self.separator}{anchor}"
        else:
            return content

    def process_pages(self,
                     pages: list,
                     printed_pages: Optional[list] = None,
                     custom_ids: Optional[list] = None) -> list:
        """
        批量处理多个页面（增强版）

        Args:
            pages: 页面内容列表
            printed_pages: 印刷页码列表
            custom_ids: 自定义编号列表（新增）
        """
        if not self.enabled:
            return pages

        printed_pages = printed_pages or [None] * len(pages)
        custom_ids = custom_ids or [None] * len(pages)

        return [
            self.wrap_page_content(idx, content, printed_id, custom_id)
            for idx, (content, printed_id, custom_id) in enumerate(zip(pages, printed_pages, custom_ids))
        ]
```

---

## 🎨 UI 设计

### 页码锚点配置界面

```python
st.subheader("📍 页码锚点配置")

# 1. 启用页码锚点
enable_page_anchors = st.checkbox("启用页码锚点", value=True)

if enable_page_anchors:
    # 2. 锚点模板选择
    col1, col2 = st.columns(2)

    with col1:
        template_preset = st.selectbox(
            "锚点模板预设",
            [
                "{n}",
                "{n1}",
                "{printed}",
                "{custom}",
                "{printed-or-n1}",
                "{custom-or-n1}",
                "{custom-or-printed-or-n1}",
                "{custom} (p.{n1})",
                "{printed} [{custom}]",
                "自定义..."
            ]
        )

    with col2:
        if template_preset == "自定义...":
            custom_template = st.text_input(
                "自定义模板",
                value="{n1}",
                help="支持变量: {n}, {n1}, {printed}, {custom}, {printed-or-n1}, {custom-or-n1}, {custom-or-printed-or-n1}"
            )
        else:
            custom_template = template_preset

    # 3. 自定义编号配置
    st.markdown("**自定义编号配置**")

    custom_id_source = st.selectbox(
        "自定义编号来源",
        [
            "无（不使用自定义编号）",
            "从 VLM 输出提取",
            "上传 CSV 文件",
            "上传 JSON 文件",
            "手动输入列表",
            "自动生成"
        ]
    )

    if custom_id_source == "上传 CSV 文件":
        csv_file = st.file_uploader("上传 CSV 文件", type=["csv"])
        st.info("CSV 格式：page_index,custom_id\\n0,sc001\\n1,sc002")

    elif custom_id_source == "上传 JSON 文件":
        json_file = st.file_uploader("上传 JSON 文件", type=["json"])
        st.info('JSON 格式：{"0": "sc001", "1": "sc002"}')

    elif custom_id_source == "手动输入列表":
        custom_id_list = st.text_area(
            "自定义编号列表（每行一个或逗号分隔）",
            value="sc001, sc002, sc003",
            help="按页面顺序输入自定义编号"
        )

    elif custom_id_source == "自动生成":
        col1, col2, col3 = st.columns(3)
        with col1:
            auto_prefix = st.text_input("前缀", value="sc")
        with col2:
            auto_start = st.number_input("起始编号", value=1, min_value=0)
        with col3:
            auto_padding = st.number_input("补零位数", value=3, min_value=0, max_value=10)

        st.info(f"示例：{auto_prefix}{str(auto_start).zfill(auto_padding)}, {auto_prefix}{str(auto_start+1).zfill(auto_padding)}, ...")

    # 4. 其他配置
    page_anchor_start = st.number_input("页序起始值", value=0, min_value=0)

    page_anchor_position = st.radio(
        "锚点位置",
        ["before", "after", "both"],
        format_func=lambda x: {"before": "页面前", "after": "页面后", "both": "两端"}[x]
    )
```

---

## 🔄 两种模式的集成

### VLM Direct 模式

```python
# 在 vlm_direct_async.py 中

# 1. 初始化自定义编号提取器
if custom_id_source != "无":
    self.custom_id_extractor = CustomIDExtractor(
        source_type=custom_id_source,
        source_data=custom_id_data,
        auto_prefix=auto_prefix,
        auto_start=auto_start,
        auto_padding=auto_padding
    )
else:
    self.custom_id_extractor = None

# 2. 提取自定义编号
custom_ids = None
if self.custom_id_extractor:
    markdown_pages, custom_ids = self.custom_id_extractor.extract_batch(markdown_pages)

# 3. 提取印刷页码
printed_pages = None
if self.printed_page_extractor:
    markdown_pages, printed_pages = self.printed_page_extractor.extract_batch(markdown_pages)

# 4. 添加页码锚点
if self.page_anchor_plugin.enabled:
    markdown_pages = self.page_anchor_plugin.process_pages(
        markdown_pages,
        printed_pages=printed_pages,
        custom_ids=custom_ids  # 新增参数
    )
```

### Pipeline 模式

```python
# 在 MarkdownRenderer 中

# 1. 从配置中获取自定义编号
custom_ids = config.get("custom_ids", None)

# 2. 在渲染时使用
for page in pages:
    page_index = page.page_id
    printed_page_id = page.get("data-printed-page", None)
    custom_id = custom_ids[page_index] if custom_ids else None

    anchor = self.page_anchor_formatter.format(
        page_index,
        printed_page_id,
        custom_id  # 新增参数
    )
```

---

## ✅ 实现步骤

### 阶段 1：核心功能（必须）
1. ✅ 扩展 `PageAnchorFormatter.format()` 添加 `custom_id` 参数
2. ✅ 添加新的模板变量：`{custom}`, `{custom-or-n1}`, `{custom-or-printed-or-n1}`
3. ✅ 创建 `CustomIDExtractor` 类
4. ✅ 实现自动生成模式（最简单）
5. ✅ 更新 `PageAnchorPlugin` 支持自定义编号

### 阶段 2：多种来源（重要）
6. ✅ 实现从 VLM 输出提取（`<!-- custom-id: xxx -->`）
7. ✅ 实现从手动输入列表提取
8. ✅ 实现从 CSV 文件提取
9. ✅ 实现从 JSON 文件提取

### 阶段 3：UI 集成（必须）
10. ✅ 更新 Streamlit UI 添加自定义编号配置
11. ✅ 在 VLM Direct 模式中集成
12. ✅ 在 Pipeline 模式中集成

### 阶段 4：测试和文档（重要）
13. ✅ 编写单元测试
14. ✅ 编写使用文档
15. ✅ 创建示例文件

---

## 📝 使用示例

### 示例 1：自动生成档案编号

```python
# 配置
custom_id_source = "自动生成"
auto_prefix = "sc"
auto_start = 1
auto_padding = 3
template = "{custom} (p.{n1})"

# 输出
{sc001 (p.1)}
{sc002 (p.2)}
{sc003 (p.3)}
```

### 示例 2：从 CSV 文件导入

```csv
page_index,custom_id
0,档-2024-001
1,档-2024-002
2,档-2024-003
```

```python
# 配置
custom_id_source = "上传 CSV 文件"
template = "{custom-or-n1}"

# 输出
{档-2024-001}
{档-2024-002}
{档-2024-003}
```

### 示例 3：VLM 识别档案编号

```markdown
<!-- custom-id: 档-2024-001 -->
<!-- printed-page: 308 -->

档案内容...
```

```python
# 配置
custom_id_source = "从 VLM 输出提取"
template = "{custom} [印刷页: {printed}]"

# 输出
{档-2024-001 [印刷页: 308]}
```

### 示例 4：三级优先级

```python
# 配置
template = "{custom-or-printed-or-n1}"

# 页面 0：有自定义编号 "sc001"，有印刷页码 "XII"
# 输出: {sc001}

# 页面 1：无自定义编号，有印刷页码 "308"
# 输出: {308}

# 页面 2：无自定义编号，无印刷页码
# 输出: {3}
```

---

## 🎯 优势

1. **灵活性**：支持多种编号来源和模板组合
2. **统一性**：在两种转换模式中使用相同的系统
3. **可扩展性**：易于添加新的编号来源和模板变量
4. **向后兼容**：不影响现有功能，默认行为不变
5. **用户友好**：提供预设模板和自动生成选项

---

## 🔍 技术细节

### 模板变量替换顺序

为了避免误替换，必须按照从长到短的顺序替换：

```python
# 正确顺序
result = result.replace("{custom-or-printed-or-n1}", ...)  # 最长
result = result.replace("{custom-or-n1}", ...)
result = result.replace("{printed-or-n1}", ...)
result = result.replace("{n}", ...)
result = result.replace("{n1}", ...)
result = result.replace("{printed}", ...)
result = result.replace("{custom}", ...)  # 最短
```

### 自定义编号的存储

在处理过程中，自定义编号以列表形式存储：

```python
custom_ids = [
    "sc001",  # 页面 0
    "sc002",  # 页面 1
    None,     # 页面 2（无自定义编号）
    "sc004",  # 页面 3
]
```

### VLM 提示词增强

需要在 VLM 提示词中添加自定义编号识别指导：

```markdown
### Custom ID Recognition (Optional)

If you see a custom document ID or archive number on this page, output it using this format:

```
<!-- custom-id: CUSTOM_ID -->
```

Examples:
- If you see "档-2024-001": output `<!-- custom-id: 档-2024-001 -->`
- If you see "SC001": output `<!-- custom-id: SC001 -->`
- If NO custom ID visible: do NOT output this tag
```

---

## 📊 对比表

| 功能 | 当前系统 | 增强后系统 |
|------|---------|-----------|
| 支持的变量 | 4 个 | 7 个 |
| 编号来源 | 2 种 | 6 种 |
| 模板灵活性 | 中等 | 高 |
| VLM 模式支持 | ✅ | ✅ |
| Pipeline 模式支持 | ✅ | ✅ |
| 自定义档案编号 | ❌ | ✅ |
| 自动生成编号 | ❌ | ✅ |
| CSV/JSON 导入 | ❌ | ✅ |

---

## 🚀 下一步

1. 实现 `CustomIDExtractor` 类
2. 增强 `PageAnchorFormatter` 和 `PageAnchorPlugin`
3. 更新 VLM Direct 和 Pipeline 模式的集成代码
4. 更新 Streamlit UI
5. 编写测试和文档
