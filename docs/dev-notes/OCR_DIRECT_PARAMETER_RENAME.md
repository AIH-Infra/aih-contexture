# OCR Direct 参数重命名方案

## 🎯 重命名原因

避免与现有 Pipeline 模式的参数冲突：
- `ocr_backend` - Pipeline 模式使用
- `ocr_batch_size` - Pipeline 模式使用

## 📋 参数重命名映射表

### OcrChandraService 参数

| 原参数名 | 新参数名 | 说明 |
|---------|---------|------|
| `ocr_endpoint` | `ocr_direct_endpoint` | API endpoint |
| `ocr_model` | `ocr_direct_model` | 模型名称 |
| `ocr_api_key` | `ocr_direct_api_key` | API 密钥 |
| `ocr_output_format` | `ocr_direct_output_format` | 输出格式 |
| `ocr_max_tokens` | `ocr_direct_max_tokens` | 最大 tokens |
| `ocr_temperature` | `ocr_direct_temperature` | Temperature |
| `ocr_timeout` | `ocr_direct_timeout` | 超时时间 |

### OcrDirectAsyncConverter 参数

| 原参数名 | 新参数名 | 说明 |
|---------|---------|------|
| `ocr_concurrency` | `ocr_direct_concurrency` | 并发数 |
| `ocr_batch_size` | `ocr_direct_batch_size` | 批次大小 |
| `ocr_batch_rest` | `ocr_direct_batch_rest` | 批次休息 |
| `ocr_resize_max` | `ocr_direct_resize_max` | 最大尺寸 |
| `ocr_image_format` | `ocr_direct_image_format` | 图像格式 |
| `ocr_image_quality` | `ocr_direct_image_quality` | 图像质量 |
| `ocr_page_anchor_enabled` | `ocr_direct_page_anchor_enabled` | 页码锚点 |
| `ocr_max_retries` | `ocr_direct_max_retries` | 重试次数 |
| `ocr_api_keys` | `ocr_direct_api_keys` | API 密钥列表 |

## 🔧 需要修改的文件

1. ✅ `marker/services/ocr_chandra.py`
2. ✅ `marker/converters/ocr_direct_async.py`
3. ✅ `test_ocr_direct.py`
4. ⚠️ 配置文档

## 📝 修改策略

为了保持向后兼容，我们采用以下策略：

1. **内部使用新参数名**
2. **初始化时支持两种参数名**（过渡期）
3. **文档使用新参数名**

示例：
```python
class OcrChandraService(BaseService):
    ocr_direct_endpoint: str = "http://localhost:1234/v1/chat/completions"

    def __init__(self, **kwargs):
        # 支持旧参数名（过渡期）
        if 'ocr_endpoint' in kwargs and 'ocr_direct_endpoint' not in kwargs:
            kwargs['ocr_direct_endpoint'] = kwargs.pop('ocr_endpoint')
        super().__init__(**kwargs)
```

## ✅ 实施计划

### Phase 1: 核心服务重命名
- [x] 创建重命名映射文档
- [ ] 修改 OcrChandraService
- [ ] 修改 OcrDirectAsyncConverter
- [ ] 修改测试脚本

### Phase 2: 前端集成
- [ ] Streamlit UI 配置界面
- [ ] build_config_dict 集成

### Phase 3: 测试验证
- [ ] 单元测试
- [ ] 集成测试
- [ ] 端到端测试

准备开始实施！
