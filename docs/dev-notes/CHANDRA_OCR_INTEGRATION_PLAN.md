# Chandra-OCR 集成方案

## 概述

Chandra-OCR 是一个专为 OCR 设计的模型，在德文古籍识别上表现优异。本文档描述如何将其集成到 Marker 的 Pipeline 模式中。

---

## 🎯 集成位置

**正确位置**：作为 **OCR Backend**（文字识别后端）

**错误位置**：❌ 不要作为 VLM Direct 模式使用

### 为什么？

| 特性 | Chandra-OCR | VLM Direct 需求 |
|------|-------------|-----------------|
| 版面分析能力 | ❌ 无 | ✅ 需要 |
| OCR 准确度 | ✅ 极高 | ✅ 需要 |
| LLM 理解能力 | ❌ 无 | ✅ 需要 |
| Prompt 可调 | ❌ 固定输出 | ✅ 需要 |
| 输出格式 | HTML + 坐标 | JSON 结构化 |

**结论**：Chandra-OCR 应该与 Surya Layout 配合使用，而不是替代整个 Pipeline。

---

## 📐 推荐架构

```
用户选择：Pipeline 模式
    ↓
┌─────────────────────────────────────┐
│ 1. Layout Backend (版面识别)         │
│    选择：Surya Layout               │
│    作用：识别块类型和位置            │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. OCR Backend (文字识别)            │
│    选择：Chandra OCR ← 新增！        │
│    作用：高精度文字识别              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. Processors (后处理)               │
│    - Markdown Noise Removal         │
│    - Line Merge (可选)              │
│    - Blockquote (可选)              │
└─────────────────────────────────────┘
```

---

## 🔧 实现步骤

### 步骤 1: 创建 Chandra OCR Service

**文件**: `marker/services/ocr_chandra.py`

```python
"""
Chandra OCR Service

专为德文古籍优化的 OCR 服务
"""

from typing import List, Dict, Any
from marker.services.ocr_base import OCRService
from PIL import Image


class ChandraOCRService(OCRService):
    """
    Chandra OCR 服务

    特点：
    - 极高的 OCR 准确度
    - 原生 HTML 输出
    - 支持坐标信息
    - 支持块类型标签
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("chandra_api_key")
        self.endpoint = config.get("chandra_endpoint", "https://api.im.studio/v1/chandra")

    def recognize_text(
        self,
        image: Image.Image,
        bbox: tuple = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        识别图片中的文字

        Args:
            image: PIL Image 对象
            bbox: 可选的边界框 (x1, y1, x2, y2)

        Returns:
            {
                "text": "识别的文本",
                "html": "HTML 格式",
                "bbox": [x1, y1, x2, y2],
                "confidence": 0.95
            }
        """
        # TODO: 实现 Chandra API 调用
        pass

    def batch_recognize(
        self,
        images: List[Image.Image],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """批量识别"""
        # TODO: 实现批量调用
        pass
```

---

### 步骤 2: 创建 Chandra OCR Builder

**文件**: `marker/builders/chandra_ocr.py`

```python
"""
Chandra OCR Builder

使用 Chandra OCR 进行文字识别
"""

from typing import List
from marker.builders.ocr import OCRBuilder
from marker.schema.document import Document
from marker.schema.blocks import Block
from marker.services.ocr_chandra import ChandraOCRService


class ChandraOCRBuilder(OCRBuilder):
    """
    Chandra OCR Builder

    在 Layout 识别后，使用 Chandra OCR 进行高精度文字识别
    """

    def __init__(self, config):
        super().__init__(config)
        self.chandra_service = ChandraOCRService(config)

    def __call__(self, document: Document) -> Document:
        """
        对文档中的所有块进行 OCR 识别

        流程：
        1. Layout Backend 已经识别了块类型和位置
        2. 对每个文本块使用 Chandra OCR 识别文字
        3. 解析 HTML 输出，提取文本和格式信息
        4. 更新 Block 的 text 和 structure
        """

        for page in document.pages:
            for block in page.children:
                # 只对文本块进行 OCR
                if block.block_type not in self.text_block_types:
                    continue

                # 获取块的图片
                block_image = block.get_image(document, highres=True)

                # 调用 Chandra OCR
                ocr_result = self.chandra_service.recognize_text(
                    block_image,
                    bbox=block.polygon.bbox
                )

                # 解析 HTML 输出
                self._parse_html_to_structure(block, ocr_result, document)

        return document

    def _parse_html_to_structure(
        self,
        block: Block,
        ocr_result: Dict,
        document: Document
    ):
        """
        解析 Chandra OCR 的 HTML 输出

        Chandra 输出示例：
        <div data-bbox="[72, 77, 160, 95]" data-label="Text">
            jünger Theolog zu hören...
        </div>

        需要：
        1. 提取文本内容
        2. 提取坐标信息
        3. 创建 Line 和 Span 对象
        4. 保留格式信息（<sup>, <b>, <i> 等）
        """
        # TODO: 实现 HTML 解析逻辑
        pass
```

---

### 步骤 3: 在 Streamlit UI 中添加选项

**文件**: `marker/scripts/streamlit_app.py`

**位置**: 在 Surya Layout 配置区域，添加 OCR Backend 选择

```python
# 在 Surya Layout 分支中
if layout_backend == "surya":
    st.markdown("#### 🔮 Surya 版面识别配置")

    # ... 现有的 Surya 配置 ...

    # 🆕 OCR Backend 选择
    st.markdown("---")
    st.markdown("#### 📝 OCR 后端选择")

    ocr_backend = st.radio(
        "选择 OCR 引擎",
        options=["surya", "chandra", "calamari", "none"],
        format_func=lambda x: {
            "surya": "🔮 Surya OCR（内置，通用）",
            "chandra": "📚 Chandra OCR（德文古籍专用，高精度）",
            "calamari": "🦑 Calamari OCR（可训练）",
            "none": "❌ 无（使用 PDF 原生文本）"
        }[x],
        index=0,
        help="选择文字识别引擎"
    )

    # Chandra OCR 配置
    if ocr_backend == "chandra":
        with st.expander("⚙️ Chandra OCR 配置", expanded=True):
            chandra_api_key = st.text_input(
                "API Key",
                type="password",
                help="IM Studio 的 API Key"
            )

            chandra_endpoint = st.text_input(
                "API Endpoint",
                value="https://api.im.studio/v1/chandra",
                help="Chandra API 端点"
            )

            st.info("💡 Chandra OCR 特别适合德文古籍和复杂排版")
```

---

## 🎨 HTML 解析策略

Chandra OCR 输出的 HTML 包含丰富的格式信息，需要正确解析：

### 需要处理的 HTML 标签

| HTML 标签 | Marker 对应 | 说明 |
|-----------|------------|------|
| `<sup>` | Span.formats = ["superscript"] | 上标（脚注引用）|
| `<b>` | Span.formats = ["bold"] | 粗体 |
| `<i>` | Span.formats = ["italic"] | 斜体 |
| `<u>` | Span.formats = ["underline"] | 下划线 |
| `<br/>` | 换行 | 诗歌分行 |
| `<h3>` | BlockTypes.SectionHeader | 章节标题 |
| `<hr/>` | BlockTypes.HorizontalRule | 分隔线 |

### 解析示例

**输入（Chandra HTML）**：
```html
<div data-bbox="[72, 104, 865, 193]" data-label="Text">
    <p>Kant war es, durch den ihm die Philosophie, wie er einmal
    in einem Briefe an Eichhorn<sup>1)</sup>) sagt...</p>
</div>
```

**输出（Marker Structure）**：
```python
Block(
    block_type=BlockTypes.Text,
    polygon=PolygonBox(x_start=72, y_start=104, x_end=865, y_end=193),
    structure=[
        Line(
            structure=[
                Span(text="Kant war es...", formats=["plain"]),
                Span(text="1)", formats=["superscript"]),
                Span(text=") sagt...", formats=["plain"])
            ]
        )
    ]
)
```

---

## 🔄 与现有系统的对比

### 方案 A: Chandra 作为 OCR Backend（推荐）

```
Surya Layout → Chandra OCR → Processors → Markdown
     ↓              ↓              ↓            ↓
  块类型+位置    高精度文字    后处理清理    最终输出
```

**优点**：
- ✅ 充分利用 Chandra 的 OCR 优势
- ✅ 保留 Surya 的版面分析能力
- ✅ 可以使用所有 Processors
- ✅ 架构清晰，易于维护

**缺点**：
- ⚠️ 需要两次 API 调用（Layout + OCR）
- ⚠️ 需要解析 HTML 输出

---

### 方案 B: Chandra 作为 VLM Direct（不推荐）

```
Chandra 一步完成 → 直接输出 Markdown
```

**优点**：
- ✅ 只需一次 API 调用

**缺点**：
- ❌ Chandra 没有版面分析能力
- ❌ 无法使用 Processors
- ❌ 输出格式固定，无法调整
- ❌ 不符合 Chandra 的设计定位

---

## 📋 实现优先级

### Phase 1: 基础集成（必需）

1. ✅ 创建 `ChandraOCRService`
2. ✅ 创建 `ChandraOCRBuilder`
3. ✅ 在 Streamlit UI 添加选项
4. ✅ 实现基础的 HTML 解析

### Phase 2: 格式保留（重要）

1. ✅ 解析 `<sup>` 标签（上标）
2. ✅ 解析 `<b>`, `<i>`, `<u>` 标签
3. ✅ 解析 `<br/>` 标签（诗歌分行）
4. ✅ 解析 `data-bbox` 坐标信息

### Phase 3: 高级功能（可选）

1. ⚪ 批量处理优化
2. ⚪ 缓存机制
3. ⚪ 错误重试
4. ⚪ 进度显示

---

## 🧪 测试计划

### 测试用例 1: 德文古籍（你的场景）

**输入**: 包含诗歌、脚注、上标的德文文档

**配置**:
- Layout Backend: Surya
- OCR Backend: Chandra
- Processors: 禁用 Line Merge 和 Blockquote

**预期输出**:
- ✅ 诗歌保持分行
- ✅ 上标正确识别
- ✅ 德文特殊字符正确
- ✅ 脚注引用保留

---

### 测试用例 2: 对比测试

**同一文档，不同 OCR Backend**:

| OCR Backend | 准确度 | 格式保留 | 速度 |
|-------------|--------|---------|------|
| Surya OCR | 中等 | 基础 | 快 |
| Chandra OCR | 极高 | 丰富 | 中等 |
| PDF Native | 取决于 PDF | 无 | 最快 |

---

## 💡 使用建议

### 何时使用 Chandra OCR？

✅ **推荐使用**：
- 德文古籍文档
- 复杂排版（诗歌、脚注、上标）
- 需要极高 OCR 准确度
- 扫描质量较差的文档

❌ **不推荐使用**：
- 现代 PDF（有原生文本）
- 简单排版文档
- 需要快速处理
- 成本敏感场景

---

## 🔗 相关文件

- `marker/services/ocr_chandra.py` - Chandra OCR 服务（待创建）
- `marker/builders/chandra_ocr.py` - Chandra OCR Builder（待创建）
- `marker/scripts/streamlit_app.py` - UI 配置（需修改）
- `marker/converters/pdf.py` - Pipeline 配置（需修改）

---

## ✅ 下一步行动

1. **确认方案**：你同意将 Chandra 作为 OCR Backend 吗？
2. **API 测试**：提供 Chandra API 的调用示例（请求/响应格式）
3. **开始实现**：从 `ChandraOCRService` 开始

**需要你提供的信息**：
- Chandra API 的完整调用方式（endpoint, headers, body）
- API 的响应格式（完整的 JSON 结构）
- 是否有批量处理接口？
- 是否有速率限制？
