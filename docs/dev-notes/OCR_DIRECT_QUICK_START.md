# OCR Direct 快速开始指南

## 🚀 5 分钟快速测试

### 前置条件

1. ✅ LM Studio 运行中
2. ✅ Chandra 模型已加载
3. ✅ API endpoint: `http://localhost:1234/v1/chat/completions`

---

## 📝 测试步骤

### 1. 运行测试脚本

```bash
python test_ocr_direct.py
```

### 2. 预期输出

```
================================================================================
OCR Direct 功能测试
================================================================================

================================================================================
测试 1: OcrChandraService
================================================================================
✅ 加载图片: (946, 1024)
📡 调用 OCR API...
✅ OCR 成功，识别到 7 个块
  Block 1: [page_header] Entstehung der Theologischen Briefe. 127... @ [286, 63, 650, 80]
  Block 2: [text] und Beruf war? wenn er sich andererseits, sta... @ [25, 96, 921, 138]
  Block 3: [text] „Alles, was Candidat ist," klagt er Ende 178... @ [25, 143, 921, 716]

================================================================================
测试 2: OcrParser
================================================================================
✅ 解析成功
  Page ID: 0
  Blocks: 2
  Block 1: BlockTypes.SectionHeader
  Block 2: BlockTypes.Text

================================================================================
测试 3: OcrDirectAsyncConverter
================================================================================
✅ 转换器创建成功
📄 转换图片: C:\Users\vellichor\Desktop\...
✅ 转换成功
  Pages: 1
  Page 1: 7 blocks

================================================================================
测试总结
================================================================================
✅ 通过 OcrChandraService
✅ 通过 OcrParser
✅ 通过 OcrDirectAsyncConverter

🎉 所有测试通过！
```

---

## 🎯 核心组件

### 1. OcrChandraService
**位置**: `marker/services/ocr_chandra.py`
**功能**: API 调用和响应解析

### 2. OcrParser
**位置**: `marker/builders/ocr_parser.py`
**功能**: 将 OCR 输出转换为 Block 结构

### 3. OcrDirectAsyncConverter
**位置**: `marker/converters/ocr_direct_async.py`
**功能**: 异步并发转换器

---

## 📦 已实现的特性

- ✅ 异步并发处理
- ✅ 批处理与休息间隔
- ✅ API 密钥池管理
- ✅ 图像预处理
- ✅ 重试机制
- ✅ 页码锚点集成
- ✅ 所有输出格式支持

---

## 🔧 配置示例

```python
from pydantic import BaseModel

class Config(BaseModel):
    # OCR 服务
    ocr_endpoint: str = "http://localhost:1234/v1/chat/completions"
    ocr_model: str = "chandra"
    ocr_output_format: str = "json"

    # 并发控制
    ocr_concurrency: int = 5
    ocr_batch_size: int = 10
    ocr_batch_rest: float = 2.0

    # 图像预处理
    ocr_resize_max: int = 2048

    # 页码锚点
    ocr_page_anchor_enabled: bool = True
```

---

## 📚 详细文档

- 📄 [完整实现计划](OCR_DIRECT_IMPLEMENTATION_PLAN.md)
- 📄 [配置参数扩展](OCR_DIRECT_CONFIG_EXTENSION.md)
- 📄 [实现完成报告](OCR_DIRECT_IMPLEMENTATION_COMPLETE.md)

---

## 🐛 故障排除

### 问题 1: 连接失败
```
❌ OCR 调用失败: Connection refused
```

**解决**: 检查 LM Studio 是否运行，端口是否正确

### 问题 2: 模型未加载
```
❌ OCR 调用失败: Model not found
```

**解决**: 在 LM Studio 中加载 Chandra 模型

### 问题 3: 导入错误
```
ModuleNotFoundError: No module named 'marker.services.ocr_chandra'
```

**解决**: 确保在 marker_cuda 目录下运行

---

## ✅ 下一步

测试通过后，可以进行：

1. **Streamlit UI 集成** - 添加 OCR Direct 选项
2. **配置系统集成** - 添加 CLI 参数
3. **生产部署** - 实际文档转换

准备好了吗？运行 `python test_ocr_direct.py` 开始测试！
