# Marker CUDA 故障排除指南

## 问题 1: LM Studio "Channel Error"

### 症状
```
[layout-qwen-7b-best@q8_0] Running chat completion on conversation with 1 messages.
[layout-qwen-7b-best@q8_0] Error: Channel Error
```

### 原因分析

"Channel Error" 是 LM Studio 的内部错误，通常由以下原因引起：

1. **模型未完全加载**：模型正在加载过程中或加载失败
2. **内存不足**：GPU 或系统内存不足以运行模型
3. **请求格式不兼容**：模型不支持当前的请求格式（如 vision 输入）
4. **LM Studio 内部错误**：服务器状态异常

### 解决方案

#### 方案 1: 重启 LM Studio
1. 完全关闭 LM Studio
2. 重新启动 LM Studio
3. 重新加载模型
4. 等待模型完全加载（状态显示为 "Ready"）

#### 方案 2: 检查模型兼容性
VLM Layout 需要支持 **视觉输入** 的模型。确保您的模型：
- 支持图像输入（vision-capable）
- 支持 OpenAI 兼容的 chat completion API
- 有足够的上下文长度处理图像

**推荐的 VLM Layout 模型**：
- `gpt-4o` / `gpt-4o-mini`（OpenAI API）
- `qwen-vl-max` / `qwen-vl-plus`（通义千问）
- `claude-3-5-sonnet`（Anthropic）
- 本地模型：`llava`, `bakllava`, `qwen2-vl`

**不推荐用于 VLM Layout**：
- 纯文本模型（如 `llama3`, `mistral`）
- 小型 OCR 专用模型（如 `churro-3b`）- 这些适合 OCR，不适合 Layout

#### 方案 3: 调整配置

在 Streamlit UI 中：

1. **使用独立的 VLM Layout 配置**：
   - 勾选 "使用独立的 API 配置"
   - 为 Layout 和 OCR 使用不同的模型
   - Layout 使用大模型（如 gpt-4o-mini）
   - OCR 使用专用模型（如 churro-3b）

2. **调整超时时间**：
   - 增加 "超时时间" 到 180-300 秒
   - 给模型更多时间处理复杂页面

3. **降低图像分辨率**：
   - 减小 "图像最大边长" 到 1024 或更低
   - 降低 JPEG 质量到 70-80
   - 减少模型处理负担

#### 方案 4: 切换到其他 Layout 后端

如果 VLM Layout 持续出错，可以切换到其他后端：

1. **Surya Layout**（推荐）：
   - 内置深度学习模型
   - 无需外部 API
   - 稳定可靠

2. **YOLO Layout**：
   - 需要 Docker 服务
   - 速度快，准确度高
   - 适合批量处理

#### 方案 5: 检查 LM Studio 日志

在 LM Studio 中查看详细日志：
1. 打开 LM Studio 的 "Server Logs" 标签
2. 查找具体的错误信息
3. 检查是否有内存溢出、模型加载失败等错误

### 诊断命令

检查 LM Studio 服务状态：
```bash
curl http://localhost:1234/v1/models
```

测试简单的文本请求：
```bash
curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "layout-qwen-7b-best@q8_0",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }'
```

---

## 问题 2: Streamlit Duplicate Element ID

### 症状
```
streamlit.errors.StreamlitDuplicateElementId: There are multiple `number_input` elements with the same auto-generated ID.
```

### 原因分析

Streamlit 为每个 UI 元素自动生成 ID。当多个元素具有相同的类型和参数时，会生成相同的 ID，导致冲突。

在 Marker 中，这通常发生在：
- 多个后端配置区域有相似的参数（如 "超时时间"）
- 切换后端时，新旧配置区域同时存在

### 解决方案

**已修复**：为所有 Calamari 配置元素添加了唯一的 `key` 参数。

修复的元素：
- `calamari_batch_size` → `key="calamari_batch_size_input"`
- `calamari_timeout` → `key="calamari_timeout_input"`
- `calamari_footnote_y_frac` → `key="calamari_footnote_y_frac_slider"`
- `calamari_sequential_mode` → `key="calamari_sequential_mode_checkbox"`
- `calamari_require_ordering_info` → `key="calamari_require_ordering_info_checkbox"`
- `calamari_fallback_to_sequential_on_ordering_failure` → `key="calamari_fallback_checkbox"`
- `calamari_trust_batch_order` → `key="calamari_trust_batch_order_checkbox"`

### 如何避免此问题

在添加新的 UI 元素时，始终提供唯一的 `key` 参数：

```python
# ❌ 错误：没有 key
timeout = st.number_input("超时时间（秒）", min_value=30, max_value=300, value=120)

# ✅ 正确：有唯一的 key
timeout = st.number_input(
    "超时时间（秒）",
    min_value=30,
    max_value=300,
    value=120,
    key="my_unique_timeout_key"  # 唯一标识符
)
```

**命名规范**：
- 使用描述性的 key 名称
- 包含功能模块前缀（如 `calamari_`, `vlm_`, `llm_`）
- 包含元素类型后缀（如 `_input`, `_checkbox`, `_slider`）
- 示例：`calamari_timeout_input`, `vlm_layout_prompt_textarea`

---

## 问题 3: VLM Layout Prompt 配置错误

### 症状
```
AssertionError: In order to use VlmLayoutService, you must set the configuration values `vlm_layout_prompt, `.
```

### 解决方案

**已修复**：详见 [VLM_LAYOUT_PROMPT_FIX_COMPLETE.md](VLM_LAYOUT_PROMPT_FIX_COMPLETE.md)

关键修复：
1. 修改 `VlmLayoutService` 类属性默认值从 `None` 到 `""`
2. 在配置传递时确保至少有一个提示词参数被设置
3. 添加默认模板 "modern" 作为回退

---

## 问题 4: LLM Provider 配置错误

### 症状
```
AssertionError: In order to use GoogleGeminiService, you must set the configuration values gemini_api_key
```

### 解决方案

**已修复**：详见 [LLM_PROVIDER_FIX.md](LLM_PROVIDER_FIX.md)

关键修复：
1. 添加 provider-to-service 映射
2. 移除已删除的 OpenAI 服务选项
3. 使用 Ollama 支持 OpenAI 兼容 API

---

## 常见问题速查

### Q: 如何选择合适的 Layout 后端？

| 后端 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **Surya** | 内置、稳定、无需配置 | 准确度中等 | 通用文档、快速测试 |
| **VLM** | 准确度高、支持复杂布局 | 需要 API、速度慢、成本高 | 复杂文档、高质量要求 |
| **YOLO** | 速度快、准确度高 | 需要 Docker | 批量处理、生产环境 |

### Q: 如何选择合适的 OCR 后端？

| 后端 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **Surya** | 内置、多语言、稳定 | 准确度中等 | 通用文档、现代印刷 |
| **VLM** | 准确度高、支持复杂布局 | 需要 API、速度慢 | 复杂文档、手写、古籍 |
| **Calamari** | 历史文档专用、高准确度 | 需要 Docker、配置复杂 | 古籍、哥特体、历史档案 |
| **None** | 速度快 | 仅适用于有文本层的 PDF | 原生 PDF、Google Books |

### Q: 如何优化处理速度？

1. **减少批次大小**：降低 GPU 内存占用
2. **使用 FP16**：启用半精度推理
3. **调整图像分辨率**：降低输入图像尺寸
4. **选择合适的后端**：Surya/YOLO 比 VLM 快
5. **禁用不需要的 LLM 模块**：只启用必要的增强功能

### Q: 如何处理内存不足错误？

1. **减少批次大小**：OCR batch size 从 32 降到 16 或 8
2. **启用批次间冷却**：设置 5-10 秒冷却时间
3. **使用 FP16**：减少 50% 内存占用
4. **分批处理**：将大文档分成多个小批次
5. **关闭其他程序**：释放 GPU 内存

### Q: 如何提高 OCR 准确度？

1. **使用 VLM OCR**：对于复杂文档
2. **启用 LLM 增强**：修正 OCR 错误
3. **调整图像质量**：提高 JPEG 质量到 90-95
4. **使用合适的模型**：Calamari 用于历史文档
5. **自定义提示词**：针对特定文档类型优化

---

## 获取帮助

如果问题仍未解决：

1. **查看日志**：
   - Streamlit 控制台输出
   - LM Studio 服务器日志
   - Docker 容器日志（如果使用）

2. **检查配置**：
   - API 密钥是否正确
   - 服务地址是否可访问
   - 模型是否已加载

3. **测试连接**：
   - 使用 curl 测试 API 端点
   - 检查网络连接
   - 验证防火墙设置

4. **报告问题**：
   - 提供完整的错误信息
   - 包含配置参数
   - 说明复现步骤
