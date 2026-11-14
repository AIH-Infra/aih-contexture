# Middle JSON 与 Scholarly Markdown 通用契约

版本：`contexture-middle-json/0.1`  
状态：当前实现契约  
适用范围：Contexture 的 Layout、OCR、VLM、外部文档导入与 Markdown 后处理路径。

## 1. 目的与规范性用语

本契约将人文文献转换定义为**可复核的结构化转写**，而非纯文本 OCR。处理结果必须能回答：某段文字来自哪一页、位于页面何处、属于何种文献结构、经过哪些后端与处理阶段，以及其印刷页码为何。

本文中：

- **必须**：违反即不能通过 Middle JSON 校验或破坏下游互操作性。
- **应当**：当前校验通常记为警告，但生产输出应满足。
- **可以**：按后端能力或输出用途选择。

Middle JSON 是机器处理、审计和再渲染的权威表示。Scholarly Markdown 是从 Middle JSON 导出的面向人工校阅与交换的阅读表示；不得以 Markdown 作为唯一的可追溯原件。

对于 TEI/XML 或 EPUB，适配器必须先生成 `contexture-source-document/0.1`，Scholarly Markdown 再由该中间层渲染；不得伪造成 Middle JSON 的物理页面模型。Source Document 是完整书目元数据、章节树、原生目录、索引和关系的权威表示，Middle JSON 只是条件性版面投影，Markdown 只是阅读投影。第 10 节规定这类输出的逻辑锚点与 sidecar 契约。

## 2. 基本不变量

1. 文档由页组成，页面索引 `index` 使用从 `0` 开始的物理页序号。
2. 物理页锚点与索引绑定：第 `i` 页必须具有 `anchor_start: i` 与 `anchor_end: i + 1`。
3. 每个块属于一个页面，`block.page_index` 必须等于父页面的 `index`；其锚点必须覆盖该页面，即 `anchor_start <= page_index < anchor_end`。
4. 块 `id` 在整个文档中必须唯一；同页块以 `order` 表达阅读顺序。
5. 任何识别文本、版面类别或语义判断都不得替代原始页面坐标与来源记录。
6. PDF/图像物理页和书籍印刷页是两个独立概念，绝不可互相覆盖。
7. 不存在完整真实页界的 EPUB 或 TEI/XML，不得为了满足本 schema 而虚构 `pages`、物理坐标或印刷页码。
8. 来源已有的章节体系、目录、索引、标识符和交叉引用不得只保存在 Markdown 标题或 `attrs` 中；必须进入 Source Document 的类型化结构。
9. Markdown 标题层级是渲染结果，不得反向覆盖来源章节树；算法生成目录不得覆盖来源目录。

## 3. Middle JSON 文档结构

顶层对象必须符合以下形状。`page_count` 由序列化器写入，若存在则必须等于 `pages` 长度。

```json
{
  "schema_version": "contexture-middle-json/0.1",
  "source_name": "optional-source.pdf",
  "page_count": 1,
  "metadata": {},
  "backends": {
    "layout": "surya",
    "ocr": "surya"
  },
  "pages": []
}
```

| 字段 | 类型 | 要求 | 含义 |
| --- | --- | --- | --- |
| `schema_version` | string | 必须为 `contexture-middle-json/0.1` | 结构契约版本。 |
| `pages` | array | 必须 | 按物理页面保存的页面对象。渲染时仍按 `index` 排序。 |
| `page_count` | integer | 可选但建议输出 | 必须等于 `pages.length`。 |
| `source_name` | string/null | 可选 | 原始文件或可识别来源名。 |
| `metadata` | object | 可选 | 文献元数据、语义解析记录等。 |
| `backends` | object | 可选 | 文档级 Layout、OCR 和模型信息。 |

### 3.1 页面对象

```json
{
  "index": 0,
  "anchor_start": 0,
  "anchor_end": 1,
  "width": 2480,
  "height": 3508,
  "printed_page": "170",
  "blocks": [],
  "attrs": {},
  "provenance": []
}
```

| 字段 | 类型 | 要求 | 含义 |
| --- | --- | --- | --- |
| `index` | integer | 必须，文档内唯一 | 从 `0` 开始的物理页索引。 |
| `anchor_start` | integer | 必须，等于 `index` | 本页开始的物理页锚点。 |
| `anchor_end` | integer | 必须，等于 `index + 1` | 本页结束的物理页锚点。 |
| `width` / `height` | finite number/null | 可选；提供时应为正数 | 页面坐标系尺寸。 |
| `printed_page` | string/null | 可选 | 原件印刷页码，用于学术引用；不等同于 `index`。 |
| `blocks` | array | 必须 | 页面中的块。 |
| `attrs` | object | 可选 | 例如机器页码、页面检测状态。 |
| `provenance` | array | 应当 | 页面级来源信息。 |

### 3.2 块对象

```json
{
  "id": "p0-b3",
  "type": "Text",
  "page_index": 0,
  "order": 3,
  "anchor_start": 0,
  "anchor_end": 1,
  "text": "正文内容。",
  "bbox": [180, 420, 2210, 760],
  "polygon": [[180, 420], [2210, 420], [2210, 760], [180, 760]],
  "confidence": 0.98,
  "spans": [],
  "children": [],
  "attrs": {},
  "provenance": []
}
```

| 字段 | 类型 | 要求 | 含义 |
| --- | --- | --- | --- |
| `id` | string | 必须，全局唯一 | 稳定的块标识。 |
| `type` | canonical block type | 必须 | 见第 4 节。未知标签必须归一为 `ComplexRegion`，不能创建私有类型。 |
| `page_index` | integer | 必须 | 必须等于父页 `index`。 |
| `order` | integer | 必须 | 页内阅读顺序；重复或未排序会产生警告。 |
| `anchor_start` / `anchor_end` | integer | 必须 | 必须覆盖 `page_index`。一般为页面的 `[index, index + 1)`。 |
| `text` | string | 可选，默认空串 | 块的转写文本；可由 `spans` 拼接回退。 |
| `bbox` | `[x0, y0, x1, y1]`/null | 可选但应当 | 需满足 `x1 >= x0`、`y1 >= y0`。 |
| `polygon` | 四个 `[x, y]` 点/null | 可选 | 精确区域。 |
| `confidence` | number/null | 可选 | 应归一到 `[0, 1]`。 |
| `spans` | array | 可选 | 细粒度文本、坐标与来源。 |
| `children` | array | 可选 | 嵌套块。 |
| `attrs` | object | 可选 | 后端原始标签、标题级别、语义角色等扩展信息。 |
| `provenance` | array | 应当 | 块级 Layout/OCR/VLM 来历。 |

### 3.3 Span 与 provenance

`spans` 的每项至少应有非空 `text`，并可带 `bbox`、`polygon`、`confidence`、`attrs` 与 `provenance`。当后端可提供字形或行级坐标时，应使用 span 保存它们，而不是只保留块级合并文本。

每个 provenance 项采用：

```json
{
  "backend": "surya",
  "stage": "ocr",
  "raw_label": "paragraph",
  "model": "optional-model-id",
  "confidence": 0.98,
  "source": "optional-source.pdf",
  "notes": "optional"
}
```

`backend` 与 `stage` 应当非空。`stage` 通常为 `layout`、`ocr`、`document`、`official_chunks` 或其他可解释的处理阶段；保留 `raw_label` 可使规范化后的类型能够回溯上游标签。

## 4. 规范块类型

`type` 必须是下列枚举之一：

| 类别 | 类型 |
| --- | --- |
| 正文与层次 | `Text`、`SectionHeader`、`ListItem`、`Reference`、`TableOfContents`、`Code`、`Form`、`Handwriting` |
| 页面附属信息 | `PageHeader`、`PageFooter`、`PageNumber`、`Footnote`、`MarginalNote`、`InlineAnnotation` |
| 图文对象 | `Caption`、`Figure`、`Picture`、`ImageDescription`、`Table`、`Equation`、`ComplexRegion` |

外部后端的 `paragraph`、`title`、`page_footnote`、`aside_text`、`ref_text`、`formula` 等标签必须映射为相应的规范类型。不能可靠映射的结果使用 `ComplexRegion`，并在 `attrs.raw_label` 或 provenance 中保留原始标签。

`SectionHeader` 应当在 `attrs` 中保有：

```json
{
  "heading_level": 2,
  "heading_level_source": "upstream",
  "raw_heading_level": 2,
  "title_role": "section_title"
}
```

标题级别必须落在 `1` 至 `6`；缺失时渲染层采用 `2`。文档标题、普通标题与章节标题可通过 `title_role` 区分，但不改变其规范块类型。

## 5. 人文语义规则

### 5.1 双页码

- **物理锚点**：Markdown 页首输出 `{index}`，用于定位原始 PDF/图像页面。
- **印刷页码**：页面 `printed_page` 输出为 `<!-- Page: value -->`，供文献引用。
- 若 `printed_page` 缺失，渲染器可从 `PageNumber` 块提取，但只接受纯数字或合法罗马数字；其他噪声不得提升为可引用页码。
- `PageNumber` 块本身不进入正文。页眉与页脚同样不进入正文，而以注释保留。

### 5.2 脚注与上标

- `Footnote` 块是脚注定义的权威结构；其首个标记若可识别则作为脚注 ID，否则按页内顺序编号。
- 脚注定义标记为 `attrs.semantic_role: "footnote_definition"`，并记录归一化标记、证据和置信度。
- 正文上标只有在同页存在匹配脚注定义等证据时才可认定为脚注引用；不要把所有上标都解释为脚注。
- 页眉、页脚、页码、目录、公式不参与脚注证据判断；表格、代码、表单中的上标也不作为脚注引用解析。
- 渲染时，行内引用和脚注定义一律使用 HTML 上标：`<sup>n</sup>`。同页的重复脚注定义会去重。

### 5.3 边注与行号

`MarginalNote` 必须保留为独立块，不能并入正文。当它仅为一至四位数字时，可标记为 `attrs.semantic_role: "line_number"`，并排除在脚注证据外。页眉、页脚和页码也必须排除在边注检测之外。

### 5.4 文本保真

- 软换行可在同一段落内合并；空行分隔的段落必须保留。
- 表格、代码、公式和引用块等结构行不得按普通段落合并。
- 长数字编号段落，例如 `201. 内容`，渲染为 `201\. 内容`，防止 Markdown 错当作列表。
- 公式在 `humanities_safe` 模式下，形似校勘索引而非数学表达式的内容可以输出为纯文本；真正公式使用 `$$ ... $$`。

## 6. Scholarly Markdown 输出契约

### 6.1 页面骨架

每页按 `index` 升序输出，标准形态如下：

```markdown
{192}

---

<!-- Page: 170 -->

<!-- PageHeader: 书名 -->

正文。

<!-- PageFooter: 卷一 -->

<sup>1</sup> 脚注正文。

{193}

---
```

文档末尾必须额外输出最终锚点 `{最后物理页索引 + 1}`。页面分隔符默认是 `---`，可配置关闭或替换。

### 6.2 块到 Markdown 的映射

| Middle 类型 | Markdown 表现 |
| --- | --- |
| `Text`、`Reference`、`Handwriting`、`Form` | 原文本，段落间空行分隔。 |
| `SectionHeader` | `#` 重复 `heading_level` 次加空格和标题文本。 |
| `ListItem` | `- 文本`。 |
| `Table` | 保留文本；HTML `<table>` 直接保留。 |
| `Equation` | 默认 `$$` 包裹；人文安全模式可输出为纯文本。 |
| `Caption` | `*文本*`。 |
| `Figure`、`Picture` | `![替代文本]()`；无文本时使用 `Image`。 |
| `Footnote` | 不在块位置渲染；收集到本页正文后，以 `<sup>id</sup> 内容` 输出。 |
| `MarginalNote` | 见第 6.3 节。 |
| `InlineAnnotation`、`ImageDescription`、`ComplexRegion` | 带块 ID 与锚点的 HTML 注释包裹。 |
| `PageHeader`、`PageFooter`、`PageNumber` | 不进入正文；前两者可输出注释，页码作为 `printed_page` 候选。 |

引用块由 `attrs` 或原始标签表明时，输出为 Markdown `>` 块。启用 provenance 注释时，每个块前可输出块 ID、类型、锚点、版面后端与置信度。

### 6.3 边注输出模式

| 模式 | 行为 |
| --- | --- |
| `line_markers` | 纯数字边注输出 `<!-- Line: n -->`；其他边注带左右侧与锚点的注释块。默认模式。 |
| `margin_comments` | 边注作为带方位、ID、锚点的注释块输出。 |
| `plain` | 仅输出边注文本。 |
| `drop` | 不输出边注。 |

当边注检测被禁用时，`line_markers` 与 `margin_comments` 必须退化为 `drop`。

## 7. 最小完整示例

以下示例满足结构约束，并展示标题、正文、脚注、边注、物理页与印刷页的关系。

```json
{
  "schema_version": "contexture-middle-json/0.1",
  "source_name": "example.pdf",
  "page_count": 1,
  "metadata": {},
  "backends": {"layout": "example-layout", "ocr": "example-ocr"},
  "pages": [
    {
      "index": 0,
      "anchor_start": 0,
      "anchor_end": 1,
      "width": 1000,
      "height": 1400,
      "printed_page": "170",
      "attrs": {},
      "provenance": [{"backend": "example-layout", "stage": "document"}],
      "blocks": [
        {
          "id": "p0-b0",
          "type": "SectionHeader",
          "page_index": 0,
          "order": 0,
          "anchor_start": 0,
          "anchor_end": 1,
          "text": "第一章",
          "bbox": [100, 100, 900, 160],
          "attrs": {"heading_level": 1, "heading_level_source": "upstream"},
          "provenance": [{"backend": "example-layout", "stage": "layout", "raw_label": "title"}]
        },
        {
          "id": "p0-b1",
          "type": "Text",
          "page_index": 0,
          "order": 1,
          "anchor_start": 0,
          "anchor_end": 1,
          "text": "正文中的论断<sup>1</sup>。",
          "bbox": [100, 220, 900, 480],
          "attrs": {},
          "provenance": [{"backend": "example-ocr", "stage": "ocr"}]
        },
        {
          "id": "p0-b2",
          "type": "MarginalNote",
          "page_index": 0,
          "order": 2,
          "anchor_start": 0,
          "anchor_end": 1,
          "text": "12",
          "bbox": [20, 260, 60, 290],
          "attrs": {"side": "left", "semantic_role": "line_number"},
          "provenance": [{"backend": "example-layout", "stage": "layout", "raw_label": "aside_text"}]
        },
        {
          "id": "p0-b3",
          "type": "Footnote",
          "page_index": 0,
          "order": 3,
          "anchor_start": 0,
          "anchor_end": 1,
          "text": "1 参见某书，第 10 页。",
          "bbox": [100, 1180, 900, 1260],
          "attrs": {},
          "provenance": [{"backend": "example-layout", "stage": "layout", "raw_label": "page_footnote"}]
        }
      ]
    }
  ]
}
```

在默认 Scholarly Markdown 配置下，预期核心输出为：

```markdown
{0}

---

<!-- Page: 170 -->

# 第一章

正文中的论断<sup>1</sup>。

<!-- Line: 12 -->

<sup>1</sup> 参见某书，第 10 页。

{1}

---
```

## 8. 校验与交付要求

交付 Middle JSON 前必须运行 `validate_middle_json`。至少应确保：

1. `schema_version` 正确，`pages` 是数组，`page_count`（若存在）准确。
2. 页面索引无重复，页锚点严格等于其物理页范围。
3. 块 ID 全局唯一，类型来自规范枚举，块属于其父页，锚点覆盖该页。
4. `bbox`、`polygon`、尺寸和置信度的数值形状正确；置信度应在 `[0, 1]` 内。
5. 每个块和可用的 span 都应保留 backend 与 stage provenance。
6. 对有印刷页码、脚注、边注、复杂版式、手写或 VLM 参与的文献，必须基于原页进行抽检，而不能只检查 Markdown 文本。

## 9. 兼容性与演进

消费者必须拒绝未知 `schema_version`，并拒绝未知规范块类型。生产者遇到上游未知标签时必须使用 `ComplexRegion` 加原始标签/来源信息，不得静默伪装为 `Text`。

新增字段可放入 `attrs`、`metadata` 或 provenance；新增规范块类型、改变锚点语义、改变脚注和页码的渲染语义，均应发布新的 `schema_version` 并提供迁移策略。

## 10. 源格式适配与逻辑锚点契约

### 10.1 适用性决策

| 源格式与证据 | 输出方式 | 禁止事项 |
| --- | --- | --- |
| 扫描 PDF、图像，或含真实页面边界的 TEI/XML（例如 `<pb>`） | 生成本契约的 Middle JSON，并从它渲染页级 Scholarly Markdown。 | 不得把扫描页序号当作印刷页码。 |
| TEI/XML 含 `<pb>` 但缺 `pb@n` | 生成物理页锚点；保留 `pb@facs` 作为扫描页回链。 | 不得由页序、文件名或正文猜造 `printed_page`。 |
| EPUB 有 page-list 或其他可靠页面证据 | 在 Source Document 中生成 `printed_page` 锚点，再渲染页码标记。 | page-list 是印刷页目标，不得当作完整物理分页。 |
| EPUB 无 page-list | 生成带 spine、fragment 和 section 锚点的 Source Document、Scholarly Markdown 与 sidecar。 | 不得伪造 Middle JSON 物理页、坐标或印刷页码。 |

逻辑锚点与物理页锚点是不同坐标系。若未来需要将逻辑文档纳入 Middle JSON，必须先发布允许 `logical` 坐标系的新 schema 版本；不得复用本版本 `pages[index]` 的语义。

### 10.2 可再生性与 sidecar

所有源格式适配器的派生输出必须具有独立、可流式加载的结构化产物，至少保存以下信息：

```yaml
schema: contexture-source-document/0.1
source: dta | tcp | gutenberg
source_id: "..."
expression_id: "source:source_id"
original_path: "..."
original_sha256: "..."
transformer: "tei-source-adapter | epub-source-adapter"
transformer_version: "..."
transformed_at: "ISO-8601 timestamp"
anchor_kind: page_boundary | document_end | digital_page | printed_page | fragment | spine_start | spine_end | section
```

完整书目元数据、锚点映射和转换日志必须分别保存在结构化 sidecar 中，而不能仅放入 Markdown front matter、文件名或 Markdown 行号。每个输出必须能根据原件路径、SHA-256、适配器版本和转换配置重新生成。

### 10.3 各类逻辑锚点

| 来源 | 规范锚点 | 必须保留的回溯信息 |
| --- | --- | --- |
| DTA TEI | 优先 `xml:id`；无 ID 时为稳定 TEI preorder path。 | XPath、输入 SHA、`pb@n` 与 `pb@facs`（如存在）。 |
| TCP TEI | `tcp:{source_id}:div-{n}:p-{n}` 等稳定树遍历 ID。 | TCP ID、XPath、输入 SHA；不得假设存在 XML ID。 |
| Gutenberg EPUB | `gutenberg:{id}:spine-{n}:fragment-{id}`。 | OPF identifier、spine 顺序、XHTML `id`、nav/NCX 证据。 |

逻辑锚点可以写入 Markdown HTML 注释，也必须记录在 package 的 `anchors.jsonl`，以供引用界面和证据追溯使用。不得使用 Markdown 行号作为引用坐标。

### 10.4 源文本保真补充

TEI 转写应保留原始拼写、长 s 和其他排印特征；EPUB 转写应保留 spine 阅读顺序、XHTML 片段 ID 和链接关系。规范化检索文本只能作为附加字段，不能覆盖转写文本。

### 10.5 完整章节、目录和索引

`contexture-source-document/0.1` 至少必须分别提供：

- `structures`：front/body/back、TEI `div`、EPUB spine/章节的连续范围树，包括无标题节点和原始类型；
- `navigations`：来源目录、landmarks/guide、page-list、图表目录和算法生成目录等互不覆盖的视图；
- `indexes`：来源显式索引的多级条目、排序值、locator、see 与 see-also；
- `relations`：目录目标、交叉引用、注释回链、书目引用、图题/表题、资源和索引定位关系；
- `raw_metadata`：完整 TEI header 或 OPF metadata/guide 原片段的内容哈希与 artifact 引用。

Markdown 中的 `#` 层级只渲染有标题的结构节点；无标题节点、原始 `div@type`、多套目录和索引关系继续存在于结构化产物中。若 Markdown 无法无损表达某项结构，应保留可见正文并用稳定锚点连接 sidecar，不得删除、猜造或扁平化权威数据。

原始 XML/EPUB 必须进入内容寻址对象库，或由持久 artifact reference 指向可按 SHA-256 校验的受管仓储。仅记录导入时的本地路径不构成可再生性保证。Source Document 新版本采用不可变版本标识；重跑适配器或迁移 schema 时保留旧版本，并为改变的稳定 ID 提供 alias/tombstone 映射。

面向现有 Markdown 型知识库时，应同时交付 `document.md` 和 `ingest_manifest.json`；后者只提供文档 ID、版本、hash、主书目字段和 companion artifact 引用。切块、embedding、reranking 与知识图谱不属于本契约，也不得反向改变 Source Document 或 Markdown 的来源事实。

### 10.6 Source Package 编码

大文档不得要求消费者一次性加载全部 `blocks`、`anchors` 或 `relations`。应使用 `contexture-source-package/0.1` manifest + UTF-8 JSONL 组件；manifest 提供组件路径、SHA-256、字节数、记录数和排序规则。JSONL 的一行必须是一个完整对象，组件按稳定顺序输出，读取器应能流式验证并在不改 ID 的情况下重组为 Source Document 语义对象。单体数组 JSON 只作为小文档和测试夹具的等价编码。
