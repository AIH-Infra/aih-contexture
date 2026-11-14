# Middle JSON 与 Scholarly Markdown 通用契约

2026-10-18更新：诊断输出遵循[独立诊断约定](READING_DIAGNOSTICS.md)，优先于下文历史的待核显示与附属报告约定。

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

- `Footnote` 块保留上游脚注分类；其首个标记有来源支持时作为脚注 ID，缺少可确认注号时保留原文并使用中性 `Footnote` 标签，不按块数量自动编号。
- 脚注定义标记为 `attrs.semantic_role: "footnote_definition"`，并记录归一化标记、证据和置信度。
- 正文上标只有在同页存在匹配脚注定义等证据时才可认定为脚注引用；不要把所有上标都解释为脚注。
- 页眉、页脚、页码、目录、公式不参与脚注证据判断；表格、代码、表单中的上标也不作为脚注引用解析。
- 渲染时，行内引用和脚注定义一律使用 HTML 上标：`<sup>n</sup>`。同页的重复脚注定义会去重。

### 5.3 边注与行号

`MarginalNote` 必须保留为独立块，不能并入正文。仅有一至四位数字的形状不足以确认行号；须有序列及版面证据，存疑数字保留。页眉、页脚和页码必须排除在边注检测之外。

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
| `Footnote` | 收集到本页正文后；有可确认注号时输出 `<sup>id</sup> 内容`，无注号时输出 `**Footnote** 原文`。 |
| `MarginalNote` | 见第 6.3 节。 |
| `InlineAnnotation`、`ImageDescription`、`ComplexRegion` | 带块 ID 与锚点的 HTML 注释包裹。 |
| `PageHeader`、`PageFooter`、`PageNumber` | 不进入正文；前两者可输出注释，页码作为 `printed_page` 候选。 |

引用块由 `attrs` 或原始标签表明时，输出为 Markdown `>` 块。启用 provenance 注释时，每个块前可输出块 ID、类型、锚点、版面后端与置信度。

### 6.3 兼容模式的边注输出

| 模式 | 行为 |
| --- | --- |
| `line_markers` | 纯数字边注输出 `<!-- Line: n -->`；其他边注带左右侧与锚点的注释块。默认模式。 |
| `margin_comments` | 边注作为带方位、ID、锚点的注释块输出。 |
| `plain` | 仅输出边注文本。 |
| `drop` | 不输出边注。 |

当边注检测被禁用时，`line_markers` 与 `margin_comments` 必须退化为 `drop`。

### 6.4 古典文献边码与文字边注

古典文献使用独立配置，默认保持兼容旧输出：

```yaml
classical_marginalia_mode: off | page_locators  # 默认 off
classical_text_marginalia_mode: separate | drop # 默认 separate
```

启用 `page_locators` 时，渲染器使用 Middle 页级 `attrs.classical_marginalia` 分析，将可确认的定位点/范围放在印刷页码注释之后；原始 block 文本、类型和物理页锚点不因输出选项改写。文字边注按 `separate` 独立呈现，或在仅影响 Markdown 的 `drop` 模式中隐藏已确认的文字边注；未判定内容与手写待核仍可见，分析记录仍保存在 compact Middle JSON 中。重渲染入口必须使用相同配置，不得静默回退到 legacy 边码渲染。

分析能力按可靠页尺寸和有限、页内的正文坐标逐页判定。缺坐标、归一化坐标或坏坐标不能作为删除文本的几何证据；整本文档不可用时保留原有输出并报告原因，部分页可用时只分析有效页，其余边注保留待核。具备脚注语义的 Text 不得因形似边码而删除。此开关只派生阅读 Markdown，各模型的原生 JSON/XML/HTML 仍按原协议保存。

通用 Markdown 校验器默认不启用古典定位语法检查，以兼容日期等普通数字注释；古典导出与启用古典模式的质量报告显式开启该检查。独立文件检查使用 `python -m aih_contexture.scripts.evaluate_markdown ... --validate-classical-locators`。

页级分析由 `resolve_classical_marginalia` 生成，持久化需保留每页 `attrs.classical_marginalia` 和文档 `metadata.classical_marginalia_resolution`。compact JSON 保留原生词级 spans 的文本、字符范围、坐标、字号和来源，以及重现渲染所需分析、编辑记录和稳定字段；不能通过清空 spans 丢失版面证据。另输出同目录 `{basename}_classical_marginalia.jsonl`，每行一页，并由 `{basename}_classical_manifest.json`（`contexture-classical-marginalia/0.1`）记录其相对路径、SHA-256、记录数和源标识。缓存应带分析版本、配置签名、源内容指纹及补充证据指纹；指纹不得包含派生缓存本身。PDF words 或人工审定 evidence 是可选内存补充参数，不是 UI 配置序列化字段；有来源哈希的人工证据仅可用于匹配的源。

定位点注释中的省略号仅表示已证实对应方向的正文延展超出所报告定位点，不表示文本缺失或定位点不存在。无省略号不代表边界精确，只代表没有声明延展。HTML 注释只在常规 Markdown 显示中隐藏；原始 Markdown 提交给语言模型时，注释内容仍可被模型读取，语义正文读取应另用明确排除定位元数据的投影接口。

范围的边界判定使用显示端点的实际位置：页首提供页列上下文的 `415a` 不能代替位于页中的首个行号 `5` 的位置。低精度列终点（如 `438a10-b`）只声明到达 b 栏，不能补造末行号。文字边注放在本页正文之后、脚注之前，用独立引用块呈现。方位有可靠证据时，英文标签为 `Left marginal note` 或 `Right marginal note`；方位不明或证据冲突时，沿用默认标签 `Margin`。未判定内容追加 `(needs review)`，手写待核追加 `(handwritten; needs review)`。原文不翻译。来源 ID、坐标、方位和判定证据只保留在 Middle JSON 及 sidecar 中，阅读 Markdown 不输出 `ClassicalTextMarginalia`、坐标、块 ID 或配套闭合注释。

已有输入可直接运行 `python -m aih_contexture.scripts.export_classical_markdown --middle-json INPUT_middle.json --source-pdf INPUT.pdf --document-id L288 --output-dir OUTPUT`，不重新 OCR。批量输入使用 `--inventory SOURCES.json --evidence-dir REVIEW_DIR`；清单中的 `code` 必须唯一，人工证据文件命名为 `CODE.evidence.json` 并绑定输入指纹。输出包括阅读 Markdown、保留原始块文本的 Middle、分析 JSONL/manifest、仅正文 `.body.txt`、逐页字符范围 `.body_map.jsonl` 与复核事件 `.review.jsonl`。正文文件不注入页码或定位注释；数字本身属于原文时仍保留。复核事件同时包含人工修正记录和未决问题，事件数不能当作错误数；当前未决候选另见页分析的 `undetermined`。导出会核对源哈希、精确编辑与 compact 重载一致性，拒绝覆写输入、重复卷号或过期证据。

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

## 11. 阅读输出的边界与复核信息（2026-10-16）

### 11.1 结构校验与正式导出

内部对象可用 `validate_middle_json` 检查；正式保存 Middle JSON 或从它导出阅读 Markdown 时，使用 `validate_middle_for_publication` / `require_middle_for_publication`。除原有结构错误外，正式导出拒绝零页对象，以及整份文档没有内容块且存在上游错误的情况。没有上游错误的全空文档保留并警告。有部分可用页面或内容块的文档保留上游失败页的诊断信息与警告，不能被描述为全部识别成功。

仅含 Markdown 的 VLM JSON 不能当作带 `regions` 的结构化 VLM 输出导入；应走 Markdown 输入方式。CLI 遇到不支持的协议或发布校验错误应以失败状态结束，不能用空的阅读文件表示成功。

### 11.2 输入物理页与模型逻辑页

Churro 等模型在同一输入图像中返回多个逻辑页时，一个输入帧仍对应一个 Middle 物理页。逻辑页次序和印刷页信息放入页面的 `attrs.logical_pages`，块保留逻辑页归属；页面标记 `logical_page_mapping="needs_review"`，阅读输出显示分页待复核提示。不得擅自把一个输入帧扩成多个物理页，或据此重排后续 `{n}` 锚点。

### 11.3 古典边码与坐标

`{n}` 是从 0 开始的输入物理页；`<!-- Page: … -->` 是本版印刷页；确认属于旧版的页码另行保存。`<!-- 415a5-a25 -->` 一类注释记录当前页可见的定位点；它不是内容起止的闭区间。有证据的跨页延展才使用 `…`，不能仅凭首末可见数字猜测整页边界。数字可能表示行、章或节。

几何判定要求可靠页面尺寸与同一坐标系。适配器仅按明确声明换算归一化坐标；不猜测未知单位。可疑的小数范围或块/页单位冲突时，保留文本并要求复核，不能借几何位置删除正文。分析器版本 `0.13` 仅迁移满足来源、配置、证据指纹及全量几何检查的 `0.4` 缓存；其他旧缓存重新分析。`off` 仍是默认设置。

### 11.4 表格与 HTML

规范的完整 OTSL 序列在通过矩形单元格及跨行跨列校验后，转换为标准 HTML 表格。损坏或混杂的序列保留现有单元格的文字顺序，并显示“表格待复核，合并关系未确认”；不能宣称已经恢复原表结构。原始表格内容继续保存在 Middle JSON，并在 `*_table_review.jsonl` 中记录原文、SHA-256 与投影状态。无结构标记的原生表格不作此转换。

阅读 HTML 使用项目已声明的 `markdown2`，支持 Markdown 表格、代码块、脚注及内联上标。原生 JSON/XML/HTML 按其保存流程保留；表格阅读投影不反写来源文本。

### 11.5 前端预览

结果区可按需开启“预览阅读 Markdown”，读取实际已保存的文件并按输入物理页查看。它不随转换设置即时重算。HTML 定位注释在阅读视图中隐藏，可在“本页 Markdown 源码”展开查看；源码保留原文。正文限制阅读行宽，宽表格允许横向滚动。原页和审计附属文件仍是查对依据。

### 11.6 JSON 重渲染与前后端一致性（2026-10-17）

前端 Markdown 后处理中的 Middle JSON 重渲染、MinerU 官方 JSON 转换与公共运行入口使用同一 `prepare_middle_rerender` 契约：先发布校验，再解析语义与古典边码，最后按有效选项生成阅读输出。无效输入不得先写出成功 Markdown；失败摘要沿用该文档已经分配的目录。原始来源文件不被改写。

重渲染默认不创建 Markdown 后处理引擎，不调用 OCR、LLM 或 API；遗留的模型配置不能触发调用。公共入口只有明确设置 `middle_rerender_apply_postprocess` 时才附加后处理；review 模式保留生成的阅读正文，仅输出复核结果。

古典模式开启后，文字边注由古典选项控制，常规边注输出选择器禁用。Pipeline 原生边码去重和坐标启发式恢复是独立的兼容处理，不是古典模式总开关；这些 Pipeline 控件不作用于 VLM。输入完全缺少可靠坐标时，古典提取降级并保留普通边注文本，显示复核警告；不能借常规 `drop` 设置静默删除未分析的文字。

Middle 和 MinerU 两组重渲染偏好分别保存，切换模式后恢复；预设保存包含边注、公式、页码和古典选项。必需 Middle 核心文件在界面中明确标为只读开启。边码、表格复核记录以及发布警告传递到实际输出、文档摘要和下载包。成功工件登记到任务上下文，终态在渲染结果区之前同步到会话，使快速完成的任务也能直接预览，并可从输出目录恢复。

### 11.7 模型直出链路验收与文字坐标（2026-10-17）

质量主验收必须使用实际模型输出经生产适配器生成的 Middle，再经常规保存路径重新读取并渲染。人工修订的 Middle、人工页审证据和渲染时外补 PDF 坐标只可作为诊断对照，不能证明这条生产链路已经达标。模块测试通过与首次/二次输出一致也不能替代原页质量验收。

识别阶段已有的文字坐标不能在常规 Middle 保存时丢弃。核心文件保留精简 spans：原始文本、有效 bbox、精确 char_range、可用字号/上标信息与来源阶段。缓存指纹包括这些坐标。一个多词 span 不能通过插值伪造逐词坐标；不存在的、错位的、非法的证据不能触发正文删改。原始块文本保持不变，阅读投影按精确源文本和坐标验证后应用派生拆分。

在古典模式中，重复正文行边界与原生文字框用于分离混入正文的边码、方括号旧版页码、窄边注片段及有独立小字号底行证据的脚注。连续节号与 Bekker 行号采用不同规则。可见端点之外的原生正文文字可证明范围延展并显示省略号。缺少注号时使用英文中性标签 Footnote，不能自动编号；普通正文章号不因处于页面下半部就变成脚注。已有旧 Middle 缺少文字坐标且不能可靠拆分时，原文保留；复核建议仅进入用户主动开启的独立诊断，不能宣布已清理干净。

精简文件会比过去仅含块框的版本更大，这是保留可重渲染证据的成本。对于只提供块级坐标或无坐标的模型，保留它实际提供的信息并报告能力边界，不能声称获得了与逐词坐标模型相同的拆分能力。
### 11.8 保存合同、配置快照与历史导入（2026-10-17）

项目原生 Pipeline 渲染树 JSON 使用独立的离线导入协议：
`python -m aih_contexture.scripts.import_pipeline_json INPUT.json --output-dir OUTPUT`。
Middle CLI 与前端 JSON 重渲染也可自动识别此协议。导入解析真实来源引用，保留物理页身份，包括 ID 为 `/page/N` 的空页；不补造缺失词框。

精简 Middle 保存保留可选功能字段：原生表格 HTML/单元格、图片资源身份与已有路径、原始列表标记和分组。旧文件缺这些字段仍可读取，但对应能力受限。标准块类型名称保持自身身份映射。

阅读输出共用准备服务，优先级为“显式覆盖 → 文档快照 → 兼容默认”。显式 `false`、`off` 与未设置不同。`metadata.reading_render_options` 保存规范化的请求选项；坐标提取是否降级另由能力检查和警告说明。无坐标时，原生独立边注仍按请求以英文在页末保留。快照不含 OCR、模型调用参数，也不会使离线重渲染自动调用模型。

通用行号与 Bekker 独立：精确词框、正文行距、页边位置及至少三个递增观测点共同确认后，或仅有块框时通过独立边注整块的长递增序列与严格位置、间距检查后，按 `generic_line_output_mode` 控制阅读 Markdown：`drop` 为默认值，舍去已确认行号；`page_comments` 在页首输出 `<!-- Lines: 5, 10, 15, ... -->` 形式的实际观测点列表。两种方式均保留 JSON 中的来源证据，不得通过插值补点。开关不影响 Bekker 定位；古典提取关闭时不执行通用行号剔除。未确认数字不删除，缺字框的粘连区域明确提示复核。在已有通用行号证据的页内，额外的较小页边数字可抽离为待核边注，不能据此确定它是行号或旧版页码。相邻正文块只在词框、字号、缩进、间距与文字连续性均支持时合并阅读字符串，源块不变；真实句末、缩进、引用和结构块保持边界，原始连字符保留。

前端只过滤重复页的空接缝；真实空页与非空重复页均保留。源块中的独立花括号数字转义为正文，物理页锚点统一由文档层生成。旧扁平 Markdown 若已失去块身份，独立 `{123}` 仍可能有歧义，应优先从 Middle 重渲染。

历史空图引用可能来自提取后主动清理，按用户澄清不计入文本/语义验收失败。近期输出已有的相对图片路径和同目录资源必须保留，不能猜资源身份或生成替代图片。

### 11.9 导入、投影和局部复核闭环（2026-10-17）

专用 VLM、OCR-direct、外部文档及 Paddle 结构导入 CLI 与普通 Middle 重渲染共用 `prepare_middle_rerender`。保存该服务返回的文档及阅读配置快照，并直接采用同一次准备得到的 Markdown。未指定的选项使用 `None`，显式 `False/off` 可以覆盖；相互矛盾的显式别名必须报错。各 CLI 对通用行号选项说明一致：须开启古典定位分析才生效，仅处理已确认行号，不影响正文数字或 Bekker 定位。导入产生的待核告警须可见，结构验证失败不得发布空 Middle 或阅读 Markdown。

字符编辑只能影响派生阅读视图。存活词的原生坐标保持不变，字符范围精确映射至编辑后的块文本；已删除词和无法验证的范围不得作为新的词级几何证据。不能用首词坐标代表全块文字，也不能通过扩大首词框来修补段落连接。跨块正文连接仍须满足同页、同语流、字号、缩进和间距条件，保留标题、列表、代码、数学、表格和真实段落边界。

书帖签名的页脚复核同时要求可靠页底几何、签名结构、无对应正文注号，以及其他页的原生页脚模板在书名、卷次和位置上的一致证据。低置信度或较大的数字均不能单独改变块类型。只有签名样式但缺少独立模板时，保留原文字并标为待核；普通低置信度脚注和无坐标输入维持原有语义。`semantic_source_type`、`semantic_rendered_type`、`page_furniture_review` 及原始置信度必须在压缩保存后保留，重新解析能恢复源类型；修改文字、版面或置信度须使语义缓存失效。

开启古典分析后，`metadata.classical_marginalia_review` 保存逐页待核区域及原因。短的无词框复杂区域不能仅因长度不足而漏报；本页其他区域已处理成功也不代表整页完成。前端批次结果展示待核页数，阅读预览从该工件相邻的 Middle JSON 读取所选输入页的待核状态。`no_geometry_gap_detected` 只表示未发现这一类几何缺口，不表示 OCR 或整页语义已通过人工验收。切换到关闭模式后不沿用旧的分析状态。待核报告是派生结果，不应导致源内容指纹变化。

