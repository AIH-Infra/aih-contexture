# VLM Direct 模式实现逻辑分析

## 一、实现逻辑概述

### 1.1 核心流程

VLM Direct 模式完全跳过 Marker 的传统流水线（Layout → OCR → Structure → Processors），直接使用 VLM 处理 PDF 页面图像：

```
PDF 文件
  ↓
Provider 加载 (PdfProvider)
  ↓
获取所有页面图像 (get_images)
  ↓
异步并发转换 (asyncio + aiohttp)
  ├─ 页面 1 → VLM API → Markdown
  ├─ 页面 2 → VLM API → Markdown
  ├─ 页面 3 → VLM API → Markdown
  └─ ...
  ↓
按页码排序
  ↓
简单拼接 (page_separator)
  ↓
返回完整 Markdown
```

### 1.2 关键代码位置

**文件**: `marker/converters/vlm_direct_async.py`

**核心方法**:
- `__call__(filepath)`: 主入口，返回完整 Markdown
- `_convert_all_pages_async(images)`: 异步并发转换所有页面
- `_convert_page_async(session, img, page_num, semaphore)`: 转换单个页面

## 二、返回格式

### 2.1 单页返回格式

每个页面通过 VLM API 返回的是**纯 Markdown 文本**，格式由 prompt 控制：

**默认 Prompt**:
```
Convert this document page to Markdown format.

Requirements:
1. Preserve the exact structure and formatting
2. Use proper Markdown syntax for:
   - Headings (# ## ###)
   - Lists (- or 1. 2. 3.)
   - Tables (| col1 | col2 |)
   - Code blocks (```language```)
   - Math equations ($inline$ or $$block$$)
   - Bold (**text**) and italic (*text*)
3. Maintain reading order (top-to-bottom, left-to-right for LTR documents)
4. Do NOT add any explanations or comments
5. Output ONLY the Markdown content
```

**返回示例**:
```markdown
# 第一章 引言

本文档介绍了...

## 1.1 背景

- 项目背景
- 研究意义

| 指标 | 数值 |
|------|------|
| 准确率 | 95% |
```

### 2.2 错误处理

如果页面转换失败（API 错误、超时等），返回错误注释：

```markdown
<!-- Error converting page 5: API error 500: Internal Server Error -->
```

## 三、拼装逻辑

### 3.1 简单拼接策略

VLM Direct 使用**最简单的字符串拼接**，没有任何结构化处理：

```python
# 代码位置: vlm_direct_async.py:277
full_markdown = self.page_separator.join(markdown_pages)
```

**默认分隔符**: `"\n\n---\n\n"` (两个换行 + 水平线 + 两个换行)

**拼接示例**:
```markdown
# 第一页内容

这是第一页的文本...

---

# 第二页内容

这是第二页的文本...

---

# 第三页内容

这是第三页的文本...
```

### 3.2 页码顺序保证

虽然是异步并发处理，但最终会按页码排序：

```python
# 代码位置: vlm_direct_async.py:243-245
results.sort(key=lambda x: x[0])  # 按页码排序
return [markdown for _, markdown in results]
```

## 四、与原流水线的兼容性分析

### 4.1 ❌ 不兼容的功能

#### 1. **页码锚点 (Page Anchors)**

**原流水线**:
- 使用 `PageAnchorFormatter` 生成结构化页码锚点
- 支持多种模板: `{n}`, `{n1}`, `{printed}`, `{printed-or-n1}`, `{printed} ({n1})`
- 锚点格式: `{page-5}` 或 `{XII (5)}`
- 位置: 每页开头，由 MarkdownRenderer 自动插入

**VLM Direct**:
- ❌ **完全没有页码锚点**
- 只有简单的分隔符 `---`
- 无法识别印刷页码（printed page）
- 无法生成结构化锚点

**影响**:
- 无法通过锚点跳转到特定页面
- 无法区分物理页码和印刷页码
- 不适合需要精确页码引用的学术文献

#### 2. **印刷页码识别 (Printed Page Detection)**

**原流水线**:
- 通过 `PageHeaderProcessor` 从页眉/页脚提取印刷页码
- 支持阿拉伯数字、罗马数字、中文数字
- 支持自动检测和格式化

**VLM Direct**:
- ❌ **完全不支持**
- VLM 可能在 Markdown 中包含页码文本，但不会结构化识别
- 无法用于锚点生成

#### 3. **文档结构 (Document Structure)**

**原流水线**:
- 构建完整的 `Document` 对象树
- 包含 `Page` → `Block` → `Line` → `Span` 层级结构
- 支持 TOC（目录）提取
- 支持引用（Reference）链接

**VLM Direct**:
- ❌ **没有结构化对象**
- 只有扁平的 Markdown 字符串
- 无法提取 TOC
- 无法处理内部链接

#### 4. **处理器链 (Processor Pipeline)**

**原流水线**:
- 20+ 个专门的处理器（Processor）
- 包括: 表格优化、公式识别、页眉页脚、列表、引用、脚注等
- 每个处理器针对特定问题优化

**VLM Direct**:
- ❌ **完全跳过所有处理器**
- 依赖 VLM 的"一次性"理解能力
- 质量完全取决于 VLM 模型和 prompt

#### 5. **元数据 (Metadata)**

**原流水线**:
- 提取 PDF 元数据（标题、作者、创建日期等）
- 识别字体、颜色、样式
- 保留 bbox 坐标信息

**VLM Direct**:
- ❌ **不提取任何元数据**
- 只有纯文本内容

### 4.2 ✅ 兼容的功能

#### 1. **基本 Markdown 输出**

两种模式都输出 Markdown 格式，可以用相同的工具查看和编辑。

#### 2. **图像处理**

两种模式都使用 `Provider.get_images()` 获取页面图像，DPI 可配置。

#### 3. **批量处理**

两种模式都支持多页 PDF 处理。

### 4.3 ⚠️ 部分兼容的功能

#### 1. **页面分隔**

**原流水线**:
```markdown
{page-0}

第一页内容...

{page-1}

第二页内容...
```

**VLM Direct**:
```markdown
第一页内容...

---

第二页内容...
```

**兼容性**: 都有分隔，但格式不同，无法互换。

#### 2. **LLM 增强**

**原流水线**: 可选的 LLM 处理器（表格、公式、手写等）

**VLM Direct**: 完全依赖 VLM，相当于"全程 LLM"

**兼容性**: 理念相似，但实现完全不同。

## 五、适用场景对比

### 5.1 VLM Direct 适合的场景

✅ **优势场景**:
1. **复杂布局文档**: 多栏、混排、不规则布局
2. **手写文档**: 古籍、手稿、笔记
3. **多语言混排**: 中英日韩混合
4. **图文混排**: 大量图表、公式
5. **快速原型**: 不需要精确结构，只要内容
6. **强大 VLM 可用**: GPT-4o, Claude 3.5 Sonnet 等

❌ **不适合场景**:
1. **需要精确页码引用**: 学术论文、法律文档
2. **需要结构化数据**: 需要提取 TOC、引用、元数据
3. **需要后处理**: 需要基于结构进行二次处理
4. **成本敏感**: VLM API 调用成本高（每页 $0.01-0.05）
5. **离线环境**: 必须联网调用 API

### 5.2 原流水线适合的场景

✅ **优势场景**:
1. **标准文档**: 规范排版的书籍、论文、报告
2. **需要精确结构**: 学术文献、档案馆文档
3. **需要页码锚点**: 人文学科研究、引用管理
4. **批量处理**: 大规模文档转换（成本低）
5. **离线处理**: 本地模型（Surya）
6. **可定制**: 可以添加自定义处理器

❌ **不适合场景**:
1. **极复杂布局**: Surya 可能识别不准
2. **手写文档**: OCR 效果差
3. **低质量扫描**: 需要强大的理解能力

## 六、兼容性改进建议

### 6.1 短期改进（可快速实现）

#### 1. **添加简单页码锚点**

在 VLM Direct 中添加基本的页码锚点支持：

```python
# 修改拼接逻辑
markdown_pages_with_anchors = []
for idx, markdown in enumerate(markdown_pages):
    page_num = idx + 1
    anchor = f"{{page-{idx}}}"  # 或 {page_num} 根据配置
    markdown_pages_with_anchors.append(f"{anchor}\n\n{markdown}")

full_markdown = self.page_separator.join(markdown_pages_with_anchors)
```

**效果**:
```markdown
{page-0}

第一页内容...

---

{page-1}

第二页内容...
```

#### 2. **支持页码锚点配置**

添加配置参数，使 VLM Direct 可以使用类似的锚点格式：

```python
vlm_direct_page_anchor_template: str = "{n}"  # 或 "{n1}"
vlm_direct_page_anchor_start: int = 0
```

#### 3. **提示词优化**

在 prompt 中要求 VLM 识别并标注页码：

```
If you see a page number (printed page number) in the header or footer,
include it as a comment at the beginning: <!-- printed-page: XII -->
```

### 6.2 中期改进（需要一定开发）

#### 1. **混合模式**

结合两种模式的优势：
- 使用 Surya 快速检测布局和页码
- 使用 VLM 处理复杂内容
- 使用原流水线的 Renderer 生成最终输出

#### 2. **结构化输出**

让 VLM 返回 JSON 格式，包含结构信息：

```json
{
  "page_number": 1,
  "printed_page": "XII",
  "sections": [
    {"type": "heading", "level": 1, "text": "第一章"},
    {"type": "paragraph", "text": "..."}
  ]
}
```

然后转换为 Document 对象，进入原流水线。

### 6.3 长期改进（架构级）

#### 1. **统一 Renderer**

让 VLM Direct 也使用 `MarkdownRenderer`，而不是简单拼接。

#### 2. **可插拔架构**

设计统一的接口，让 VLM Direct 可以选择性地使用某些处理器。

## 七、总结

### 7.1 核心差异

| 维度 | 原流水线 | VLM Direct |
|------|---------|-----------|
| **架构** | 多阶段流水线 | 单阶段直接转换 |
| **结构** | Document 对象树 | 扁平字符串 |
| **页码锚点** | ✅ 完整支持 | ❌ 不支持 |
| **印刷页码** | ✅ 自动识别 | ❌ 不支持 |
| **处理器** | ✅ 20+ 专门处理器 | ❌ 无 |
| **元数据** | ✅ 完整提取 | ❌ 无 |
| **成本** | 低（本地模型） | 高（API 调用） |
| **速度** | 中等 | 快（并发） |
| **质量** | 稳定 | 依赖 VLM |
| **复杂布局** | 中等 | 优秀 |
| **手写识别** | 差 | 优秀 |

### 7.2 兼容性评估

**页码锚点等设置**: ❌ **目前完全不兼容**

VLM Direct 是一个**完全独立的转换路径**，不使用原流水线的任何高级功能（页码锚点、印刷页码、处理器、结构化对象等）。

**如果需要兼容**，必须进行改进（见第六节建议）。

### 7.3 推荐使用策略

1. **人文学科/档案馆文献**: 使用**原流水线** + 页码锚点配置
2. **复杂手写古籍**: 使用 **VLM Direct** + 后期手动添加页码
3. **标准现代文档**: 使用**原流水线**（成本低、质量稳定）
4. **快速原型/演示**: 使用 **VLM Direct**（速度快、效果好）

### 7.4 未来方向

建议开发**混合模式**，结合两者优势：
- 保留原流水线的结构化能力（页码锚点、处理器等）
- 在关键环节使用 VLM 增强（复杂布局、手写识别等）
- 提供统一的配置接口和输出格式
