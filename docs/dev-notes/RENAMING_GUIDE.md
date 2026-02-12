# 服务重命名文档 (Service Renaming Documentation)

## 概述 (Overview)

本次重构对 marker 项目的服务层进行了系统性重命名，建立了清晰的命名规范，避免了命名冲突，并为未来的 LLM 辅助功能预留了命名空间。

## 重命名对照表 (Renaming Reference)

### Services 层 (marker/services/)

| 旧文件名 | 新文件名 | 旧类名 | 新类名 | 状态 |
|---------|---------|-------|-------|------|
| `openai.py` | `ocr_vlm.py` | `OpenAIService` | `VlmOcrService` | ✅ 已重命名，保留向后兼容 |
| `calamari.py` | `ocr_calamari.py` | `CalamariService` | `CalamariOcrService` | ✅ 已重命名，保留向后兼容 |
| `vlm_layout.py` | `layout_vlm.py` | `VlmLayoutService` | `VlmLayoutService` | ✅ 已重命名，保留向后兼容 |
| `doclayout_yolo.py` | `layout_yolo.py` | `DocLayoutYoloService` | `YoloLayoutService` | ✅ 已重命名，保留向后兼容 |
| `layout_service.py` | `layout_base.py` | `BaseLayoutService` | `BaseLayoutService` | ✅ 已重命名，保留向后兼容 |

### Builders 层 (marker/builders/)

Builders 层文件名保持不变，仅更新了导入语句：

| 文件名 | 类名 | 更新内容 |
|-------|------|---------|
| `vlm_ocr.py` | `VlmOcrBuilder` | ✅ 导入语句已更新 |
| `calamari_ocr.py` | `CalamariOcrBuilder` | ✅ 导入语句已更新 |
| `vlm_layout.py` | `VlmLayoutBuilder` | ✅ 导入语句已更新 |
| `yolo_layout.py` | `YoloLayoutBuilder` | ✅ 导入语句已更新 |

## 命名规范 (Naming Convention)

### Services 层命名规则
- **格式**: `{功能}_{技术}.py`
- **示例**:
  - `ocr_vlm.py` - VLM OCR 服务
  - `ocr_calamari.py` - Calamari OCR 服务
  - `layout_vlm.py` - VLM 版面识别服务
  - `layout_yolo.py` - YOLO 版面识别服务

### Builders 层命名规则
- **格式**: `{技术}_{功能}.py`
- **示例**:
  - `vlm_ocr.py` - VLM OCR Builder
  - `calamari_ocr.py` - Calamari OCR Builder
  - `vlm_layout.py` - VLM Layout Builder
  - `yolo_layout.py` - YOLO Layout Builder

**设计理念**: Services 和 Builders 使用不同的命名顺序，避免文件名冲突。

## 向后兼容性 (Backward Compatibility)

所有旧的导入路径和类名都保留了向后兼容性：

### 方式 1: 弃用警告 (Deprecation Warnings)

旧文件（如 `openai.py`）现在会导入新类并发出弃用警告：

```python
# marker/services/openai.py
import warnings
from marker.services.ocr_vlm import VlmOcrService

class OpenAIService(VlmOcrService):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "OpenAIService is deprecated. Use VlmOcrService instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)
```

### 方式 2: 类别名 (Class Aliases)

新文件末尾添加了向后兼容别名：

```python
# marker/services/ocr_vlm.py
class VlmOcrService(BaseService):
    # ... 实现 ...

# Backward compatibility alias
OpenAIService = VlmOcrService
```

## 迁移指南 (Migration Guide)

### 推荐的迁移步骤

1. **立即可用** (当前状态)
   - 所有旧代码继续工作
   - 会看到弃用警告
   - 新代码应使用新的导入路径

2. **短期内** (1-2 周)
   - 逐步更新代码中的导入语句
   - 更新配置文件中的类名引用

3. **中期** (1-2 个月后)
   - 移除所有弃用警告
   - 删除旧的兼容性文件

### 代码更新示例

#### 旧代码 (Old Code)
```python
from marker.services.openai import OpenAIService
from marker.services.calamari import CalamariService
from marker.services.vlm_layout import VlmLayoutService
from marker.services.doclayout_yolo import DocLayoutYoloService

# 实例化
ocr_service = OpenAIService(config)
calamari = CalamariService(config)
layout_service = VlmLayoutService(config)
yolo_service = DocLayoutYoloService(config)
```

#### 新代码 (New Code)
```python
from marker.services.ocr_vlm import VlmOcrService
from marker.services.ocr_calamari import CalamariOcrService
from marker.services.layout_vlm import VlmLayoutService
from marker.services.layout_yolo import YoloLayoutService

# 实例化
ocr_service = VlmOcrService(config)
calamari = CalamariOcrService(config)
layout_service = VlmLayoutService(config)
yolo_service = YoloLayoutService(config)
```

## 未来扩展 (Future Extensions)

### LLM 辅助服务命名空间

现在 `openai` 命名空间已经释放，可以用于未来的 LLM 辅助功能：

```
marker/services/
├── ocr_vlm.py          # VLM OCR (原 openai.py)
├── ocr_calamari.py     # Calamari OCR
├── layout_vlm.py       # VLM Layout
├── layout_yolo.py      # YOLO Layout
├── layout_base.py      # Layout 基类
│
├── llm_openai.py       # ✨ 未来：OpenAI LLM 辅助服务
├── llm_claude.py       # ✨ 未来：Claude LLM 辅助服务
├── llm_gemini.py       # ✅ 已存在：Gemini LLM 服务
└── llm_base.py         # ✨ 未来：LLM 基类
```

### 现有 LLM 服务

项目中已经存在以下 LLM 辅助服务（用于文档理解、表格处理等）：
- `gemini.py` - Google Gemini 服务
- `claude.py` - Anthropic Claude 服务
- `ollama.py` - Ollama 本地 LLM 服务
- `vertex.py` - Google Vertex AI 服务
- `azure_openai.py` - Azure OpenAI 服务

这些服务保持不变，专注于 LLM 辅助功能（非 OCR）。

## 已更新的文件列表 (Updated Files)

### 新创建的文件
- ✅ `marker/services/ocr_vlm.py`
- ✅ `marker/services/ocr_calamari.py`
- ✅ `marker/services/layout_vlm.py`
- ✅ `marker/services/layout_yolo.py`
- ✅ `marker/services/layout_base.py`

### 修改为兼容性包装的文件
- ✅ `marker/services/openai.py` (现在是弃用包装)
- ✅ `marker/services/calamari.py` (现在是弃用包装)
- ✅ `marker/services/vlm_layout.py` (现在是弃用包装)
- ✅ `marker/services/doclayout_yolo.py` (现在是弃用包装)
- ✅ `marker/services/layout_service.py` (现在是弃用包装)

### 更新了导入的文件
- ✅ `marker/builders/vlm_ocr.py`
- ✅ `marker/builders/calamari_ocr.py`
- ✅ `marker/builders/vlm_layout.py`
- ✅ `marker/builders/yolo_layout.py`
- ✅ `marker/converters/pdf.py`
- ✅ 其他测试和示例文件

## 验证清单 (Verification Checklist)

- [x] 所有新服务文件已创建
- [x] 所有旧服务文件已转换为兼容性包装
- [x] Builders 中的导入已更新
- [x] Converters 中的导入已更新
- [x] 向后兼容性别名已添加
- [x] 弃用警告已实现
- [ ] 运行测试套件验证功能正常
- [ ] 更新用户文档和 README

## 注意事项 (Notes)

1. **不要删除旧文件**: 旧的服务文件（如 `openai.py`）现在是兼容性包装，不应删除。
2. **弃用警告**: 使用旧导入路径时会看到 `DeprecationWarning`，这是预期行为。
3. **配置兼容性**: 配置参数名称保持不变（如 `openai_base_url`），确保配置文件无需修改。
4. **LLM 服务不受影响**: 现有的 LLM 辅助服务（Gemini、Claude 等）完全不受此次重构影响。

## 联系方式 (Contact)

如有问题或建议，请在项目 issue 中反馈。

---

**重构完成日期**: 2026-01-26
**重构版本**: v1.0
