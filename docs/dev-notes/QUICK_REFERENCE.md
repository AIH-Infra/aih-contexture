# 🚀 快速参考：服务重命名

## 一句话总结
所有 OCR 和 Layout 服务已重命名，建立清晰的命名规范，完全向后兼容。

## 快速对照

### 导入语句更新

```python
# ❌ 旧代码（仍然工作，但会有弃用警告）
from marker.services.openai import OpenAIService
from marker.services.calamari import CalamariService
from marker.services.vlm_layout import VlmLayoutService
from marker.services.doclayout_yolo import DocLayoutYoloService
from marker.services.layout_service import BaseLayoutService

# ✅ 新代码（推荐）
from marker.services.ocr_vlm import VlmOcrService
from marker.services.ocr_calamari import CalamariOcrService
from marker.services.layout_vlm import VlmLayoutService
from marker.services.layout_yolo import YoloLayoutService
from marker.services.layout_base import BaseLayoutService
```

### 类名更新

| 旧类名 | 新类名 | 用途 |
|-------|-------|------|
| `OpenAIService` | `VlmOcrService` | VLM OCR |
| `CalamariService` | `CalamariOcrService` | Calamari OCR |
| `DocLayoutYoloService` | `YoloLayoutService` | YOLO Layout |
| `VlmLayoutService` | `VlmLayoutService` | VLM Layout (不变) |
| `BaseLayoutService` | `BaseLayoutService` | Layout 基类 (不变) |

## 命名规范

### Services: `{功能}_{技术}.py`
- `ocr_vlm.py` - OCR 功能 + VLM 技术
- `layout_yolo.py` - Layout 功能 + YOLO 技术

### Builders: `{技术}_{功能}.py`
- `vlm_ocr.py` - VLM 技术 + OCR 功能
- `yolo_layout.py` - YOLO 技术 + Layout 功能

## 重要提示

✅ **所有旧代码继续工作** - 无需立即修改
✅ **配置参数不变** - `openai_base_url` 等保持不变
✅ **LLM 服务不受影响** - Gemini、Claude 等不变
⚠️ **会看到弃用警告** - 这是预期行为

## 文件位置

- 📖 完整文档: `RENAMING_GUIDE.md`
- 📊 总结: `RENAMING_SUMMARY.md`
- 🧪 验证脚本: `verify_renaming.py`

## 下一步

1. 继续使用现有代码（会有弃用警告）
2. 逐步更新到新的导入路径
3. 1-2个月后移除弃用代码

---
**完成日期**: 2026-01-26
