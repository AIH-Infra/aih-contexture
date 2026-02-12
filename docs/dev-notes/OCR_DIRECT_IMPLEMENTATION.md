# OCR Direct 模式 - 实现细节

## 🎨 UI 设计

### Streamlit 界面布局

```python
# 转换模式选择
conversion_mode = st.radio(
    "选择转换模式",
    options=["pipeline", "vlm_direct", "ocr_direct"],
    format_func=lambda x: {
        "pipeline": "🔄 Pipeline 模式（传统流水线）",
        "vlm_direct": "🤖 VLM Direct 模式（视觉语言模型）",
        "ocr_direct": "📚 OCR Direct 模式（专业 OCR）"
    }[x],
    index=0,
    help="选择文档转换方式"
)
```

### 模式说明卡片

```python
if conversion_mode == "pipeline":
    st.info("""
    **适用场景**：标准文档、现代 PDF
    **特点**：可定制、可后处理、速度快
    """)

elif conversion_mode == "vlm_direct":
    st.info("""
    **适用场景**：需要智能理解的文档
    **特点**：AI 理解、灵活 prompt、格式可调
    """)

elif conversion_mode == "ocr_direct":
    st.info("""
    **适用场景**：手写、复杂表格、数学公式、老旧文献
    **特点**：Layout-aware、高精度、结构化输出
    """)
```

## 📂 文件结构

```
marker/
├── converters/
│   ├── pdf.py                    # Pipeline 转换器
│   ├── vlm_direct.py             # VLM Direct 转换器
│   └── ocr_direct.py             # OCR Direct 转换器（新增）
├── services/
│   ├── gemini.py                 # Gemini 服务
│   ├── claude.py                 # Claude 服务
│   └── ocr/                      # OCR 服务（新增目录）
│       ├── __init__.py
│       ├── base.py               # OCR 服务基类
│       ├── chandra.py            # Chandra 服务
│       ├── got_ocr.py            # GOT-OCR 服务（未来）
│       └── nougat.py             # Nougat 服务（未来）
├── builders/
│   └── ocr_parser.py             # OCR 输出解析器（新增）
└── scripts/
    └── streamlit_app.py          # UI（修改）
```

## 🔧 核心代码

### 1. OCR 服务基类

```python
# marker/services/ocr/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any
from PIL import Image


class OCRService(ABC):
    """OCR 服务基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_format = config.get("output_format", "json")

    @abstractmethod
    def process_page(self, image: Image.Image, **kwargs) -> Dict[str, Any]:
        """处理单页图片"""
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, str]:
        """获取模型信息"""
        pass
```

### 2. OCR Direct 转换器

```python
# marker/converters/ocr_direct.py
from marker.converters import BaseConverter
from marker.schema.document import Document
from marker.services.ocr import get_ocr_service
from marker.builders.ocr_parser import OCRParser


class OCRDirectConverter(BaseConverter):
    """OCR Direct 转换器"""

    def __init__(self, config):
        super().__init__(config)
        ocr_model = config.get("ocr_model", "chandra")
        self.ocr_service = get_ocr_service(ocr_model, config)
        self.parser = OCRParser(config)

    def __call__(self, filepath: str) -> Document:
        images = self._load_images(filepath)
        document = Document(filepath=filepath, pages=[])

        for i, img in enumerate(images):
            ocr_output = self.ocr_service.process_page(img)
            page = self.parser.parse(ocr_output, i, img.size)
            document.pages.append(page)

        return document
```

## ✅ 决策总结

**最终方案：独立的 OCR Direct 模式**

**命名**：
- 中文：**专业 OCR 模式**
- 英文：**OCR Direct**
- 代码：`ocr_direct`

**理由**：
1. ✅ 概念清晰（OCR 就是 OCR，不是 VLM）
2. ✅ 配置简洁（每个模式独立配置）
3. ✅ 易于扩展（添加新 OCR 模型简单）
4. ✅ 代码清晰（独立的 Converter 和 Service）
5. ✅ 用户心智模型清晰（三个并列模式）

**架构**：
```
Marker 转换模式
├─ Pipeline 模式（传统流水线）
├─ VLM Direct 模式（视觉语言模型）
└─ OCR Direct 模式（专业 OCR）← 新增
```
