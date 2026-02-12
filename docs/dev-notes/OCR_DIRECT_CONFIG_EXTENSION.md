# OCR Direct 配置参数扩展

## 需要添加到 config/parser.py 的配置项

### 1. OCR 服务配置

```python
# OCR 模式和服务
ocr_mode: str = "chandra"  # OCR 引擎类型
ocr_endpoint: str = "http://localhost:1234/v1/chat/completions"
ocr_model: str = "chandra"
ocr_api_key: Optional[str] = None
ocr_api_keys: List[str] = []  # 多个 API 密钥支持

# 输出格式
ocr_output_format: str = "json"  # json, html, markdown

# API 参数
ocr_max_tokens: int = 4096
ocr_temperature: float = 0.1
ocr_timeout: int = 120
ocr_max_retries: int = 3
```

### 2. 并发控制配置

```python
# 并发控制
ocr_concurrency: int = 5  # 最大并发请求数
ocr_batch_size: int = 10  # 批次大小
ocr_batch_rest: float = 2.0  # 批次间休息时间(秒)
```

### 3. 图像预处理配置

```python
# 图像预处理
ocr_resize_max: int = 2048  # 最大图像尺寸
ocr_image_format: str = "PNG"  # PNG 或 JPEG
ocr_image_quality: int = 95  # JPEG 质量 (1-100)
```

### 4. 页码锚点配置

```python
# 页码锚点
ocr_page_anchor_enabled: bool = True
ocr_page_anchor_format: str = "{n}"
```

---

## CLI 选项添加

需要在 `common_options` 方法中添加：

```python
fn = click.option(
    "--ocr_endpoint",
    type=str,
    default="http://localhost:1234/v1/chat/completions",
    help="OCR API endpoint (OpenAI compatible)"
)(fn)

fn = click.option(
    "--ocr_model",
    type=str,
    default="chandra",
    help="OCR model name"
)(fn)

fn = click.option(
    "--ocr_output_format",
    type=click.Choice(["json", "html", "markdown"]),
    default="json",
    help="OCR output format"
)(fn)

fn = click.option(
    "--ocr_concurrency",
    type=int,
    default=5,
    help="Maximum concurrent OCR requests"
)(fn)

fn = click.option(
    "--ocr_batch_size",
    type=int,
    default=10,
    help="Batch size for processing pages"
)(fn)
```

---

## 配置字典生成

在 `generate_config_dict` 方法中添加：

```python
case "ocr_endpoint":
    config["ocr_endpoint"] = v
case "ocr_model":
    config["ocr_model"] = v
case "ocr_output_format":
    config["ocr_output_format"] = v
case "ocr_concurrency":
    config["ocr_concurrency"] = v
case "ocr_batch_size":
    config["ocr_batch_size"] = v
case "ocr_batch_rest":
    config["ocr_batch_rest"] = v
case "ocr_resize_max":
    config["ocr_resize_max"] = v
case "ocr_page_anchor_enabled":
    config["ocr_page_anchor_enabled"] = v
```

---

## 使用示例

### 命令行使用

```bash
# 基础使用
python convert.py input.pdf --converter_cls marker.converters.ocr_direct_async.OcrDirectAsyncConverter

# 自定义配置
python convert.py input.pdf \
  --converter_cls marker.converters.ocr_direct_async.OcrDirectAsyncConverter \
  --ocr_endpoint http://localhost:1234/v1/chat/completions \
  --ocr_model chandra \
  --ocr_output_format json \
  --ocr_concurrency 10 \
  --ocr_batch_size 20
```

### JSON 配置文件

```json
{
  "converter_cls": "marker.converters.ocr_direct_async.OcrDirectAsyncConverter",
  "ocr_endpoint": "http://localhost:1234/v1/chat/completions",
  "ocr_model": "chandra",
  "ocr_output_format": "json",
  "ocr_concurrency": 5,
  "ocr_batch_size": 10,
  "ocr_batch_rest": 2.0,
  "ocr_resize_max": 2048,
  "ocr_page_anchor_enabled": true
}
```

使用：
```bash
python convert.py input.pdf --config_json ocr_config.json
```

---

## 注意事项

1. **向后兼容**: 所有新参数都有默认值，不影响现有功能
2. **类型安全**: 使用 Pydantic 的 Annotated 类型提示
3. **验证**: 在 converter 初始化时验证配置
4. **文档**: 每个参数都有清晰的 help 文本

---

## 下一步

由于 config/parser.py 文件较大且复杂，建议：

1. 先测试核心功能（OcrChandraService + OcrParser + OcrDirectAsyncConverter）
2. 确认功能正常后再集成到配置系统
3. 或者创建独立的配置类 `OcrDirectConfig`
