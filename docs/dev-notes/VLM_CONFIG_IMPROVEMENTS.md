# VLM/LLM配置改进完成报告

## 已完成的改进

### 1. ✅ 解除VLM Layout和OCR的绑定

**改动:**
- 移除了`vlm_layout_use_separate_config`选项
- VLM Layout和VLM OCR现在完全独立配置
- 不再有"复用OCR VLM配置"的选项

**配置位置:**
- VLM Layout: 版面识别后端 → VLM → VLM 版面识别配置
- VLM OCR: OCR 后端 → VLM → API 配置

**好处:**
- 更清晰的配置结构
- 可以为Layout和OCR使用不同的模型和API
- 避免配置混淆

### 2. ✅ 添加并发配置

所有VLM/LLM位置现在都支持自定义并发数:

#### VLM Layout (版面识别)
- 位置: 版面识别后端 → VLM → VLM 版面识别配置
- 配置项: "最大并发数" (1-20)
- 默认值: 3
- 说明: 同时处理的页面数

#### VLM OCR
- 位置: OCR 后端 → VLM → API 配置
- 配置项: "最大并发数" (1-20)
- 默认值: 3
- 说明: 同时处理的OCR请求数

#### VLM Direct (纯VLM模式)
- 位置: 转换模式 → VLM Direct → 并发配置
- 配置项: "最大并发数" (1-20)
- 默认值: 5
- 说明: 同时处理的页面数
- 包含并发数建议(OpenAI 5-10, 本地模型 1-2)

#### LLM增强
- 位置: LLM 增强 → LLM 配置 → 各提供商配置
- 配置项: "最大并发数" (1-20)
- 默认值: 3
- 说明: LLM处理的并发数
- 每个提供商(Gemini, Ollama, Azure, Claude)都有独立的并发配置

## 待实现: 多API Key支持

### 需求分析

用户希望支持配置多个API Key,失败时自动切换。这需要:

1. **配置界面改进**
   - 支持输入多个API Key(逗号分隔或多行输入)
   - 显示当前使用的Key和失败次数

2. **服务层改进**
   - 实现Key轮换机制
   - 失败重试时自动切换到下一个Key
   - 记录每个Key的使用情况和失败次数

3. **实现位置**
   - VLM Layout Service
   - VLM OCR Service
   - VLM Direct Converter
   - LLM Services (Gemini, Ollama, Azure, Claude)

### 实现方案

#### 方案1: 简单轮换(推荐)

```python
class APIKeyRotator:
    def __init__(self, api_keys: list[str]):
        self.api_keys = api_keys
        self.current_index = 0
        self.failure_counts = {key: 0 for key in api_keys}

    def get_current_key(self) -> str:
        return self.api_keys[self.current_index]

    def mark_failure(self):
        current_key = self.get_current_key()
        self.failure_counts[current_key] += 1
        # 切换到下一个Key
        self.current_index = (self.current_index + 1) % len(self.api_keys)

    def mark_success(self):
        # 成功后重置到第一个Key
        self.current_index = 0
```

#### 方案2: 智能轮换

- 跟踪每个Key的成功率
- 优先使用成功率高的Key
- 自动跳过失败次数过多的Key

### 配置界面设计

```python
# 多Key输入
api_keys_input = st.text_area(
    "API Keys (每行一个)",
    value="",
    height=100,
    help="输入多个API Key,每行一个。失败时自动切换到下一个Key。"
)

# 解析多个Key
api_keys = [k.strip() for k in api_keys_input.split('\n') if k.strip()]

if len(api_keys) > 1:
    st.info(f"✅ 已配置 {len(api_keys)} 个API Key,支持自动切换")
```

### 实现步骤

1. **修改配置界面** (streamlit_app.py)
   - VLM Layout: 支持多Key输入
   - VLM OCR: 支持多Key输入
   - VLM Direct: 支持多Key输入
   - LLM: 支持多Key输入

2. **创建Key轮换器** (marker/utils/api_key_rotator.py)
   - 实现APIKeyRotator类
   - 支持失败重试和自动切换

3. **修改服务层**
   - VlmLayoutService: 集成Key轮换
   - VlmOcrService: 集成Key轮换
   - VlmDirectConverter: 集成Key轮换
   - LLM Services: 集成Key轮换

4. **测试**
   - 测试单Key场景
   - 测试多Key场景
   - 测试失败切换

## 使用示例

### VLM Layout独立配置

```
转换模式: Pipeline (传统模式)
版面识别后端: VLM
  ├─ Base URL: https://api.openai.com/v1
  ├─ 模型名称: gpt-4o-mini
  ├─ API Key: sk-layout-key-xxx
  └─ 最大并发数: 3

OCR 后端: VLM
  ├─ Base URL: https://api.openai.com/v1
  ├─ 模型名称: gpt-4o
  ├─ API Key: sk-ocr-key-xxx
  └─ 最大并发数: 5
```

现在Layout和OCR可以使用不同的模型和Key!

### VLM Direct高并发

```
转换模式: VLM Direct
  ├─ Base URL: https://api.openai.com/v1
  ├─ 模型名称: gpt-4o
  ├─ API Key: sk-xxx
  └─ 最大并发数: 10  ← 可以设置更高的并发
```

### LLM增强并发

```
LLM 增强: 启用
  ├─ API 提供商: Gemini
  ├─ API Key: xxx
  └─ 最大并发数: 5  ← 每个提供商独立配置
```

## 性能建议

### 并发数设置建议

| 场景 | VLM Layout | VLM OCR | VLM Direct | LLM |
|------|------------|---------|------------|-----|
| OpenAI 付费 | 3-5 | 5-10 | 5-10 | 3-5 |
| OpenAI 免费 | 1-2 | 2-3 | 2-3 | 1-2 |
| 通义千问 | 3-5 | 5-10 | 5-10 | 3-5 |
| Claude | 2-3 | 3-5 | 3-5 | 2-3 |
| 本地LM Studio | 1 | 1-2 | 1-2 | 1 |

### 注意事项

1. **API限流**: 并发数过高可能触发API限流
2. **成本控制**: 高并发会增加API调用成本
3. **内存占用**: 高并发会增加内存占用
4. **网络带宽**: 高并发需要足够的网络带宽

## 提交记录

```bash
git add marker/scripts/streamlit_app.py
git commit -m "Add VLM/LLM concurrency config and decouple VLM Layout from OCR

- Removed vlm_layout_use_separate_config option
- VLM Layout and VLM OCR now have independent configurations
- Added max_concurrent slider for VLM Layout (1-20, default 3)
- Added max_concurrent slider for VLM OCR (1-20, default 3)
- VLM Direct already has max_concurrent (1-20, default 5)
- LLM enhancement already has max_concurrency per provider (1-20, default 3)
- All VLM/LLM positions now support custom concurrency settings"
```

## 下一步

如果需要实现多API Key支持,请告诉我,我会继续实现:
1. 创建APIKeyRotator类
2. 修改配置界面支持多Key输入
3. 集成到各个服务层
4. 添加测试

当前的改进已经让VLM/LLM配置更加灵活和强大!
