# LLM 增强 UI 配置分析报告

## 执行摘要

经过详细的代码审查，发现 **Streamlit UI 中的 LLM 模块开关存在严重的集成问题**：UI 显示了 11 个独立的模块开关，但这些开关**并未真正控制后端处理器的启用/禁用**。

---

## 1. UI 配置界面分析

### 1.1 UI 结构

**代码位置**: [marker/scripts/streamlit_app.py:1519-1756](marker/scripts/streamlit_app.py#L1519-L1756)

UI 包含以下配置项：

#### A. 全局开关
```python
use_llm = st.checkbox("启用 LLM 增强", value=False)
```

#### B. API 提供商配置
- **选项**: Gemini (推荐), Ollama, Azure OpenAI, Claude
- **配置项**:
  - API Keys (Gemini 支持多个)
  - 模型名称
  - 最大并发数 (max_concurrency)
  - Base URL (部分提供商)

#### C. LLM 处理模块开关 (11 个)

**代码位置**: [marker/scripts/streamlit_app.py:1666-1722](marker/scripts/streamlit_app.py#L1666-L1722)

| 模块 | UI 变量名 | 默认值 | 说明 |
|------|-----------|--------|------|
| 表格优化 | `llm_table_enabled` | True | 修正表格结构 |
| 公式识别 | `llm_equation_enabled` | True | 识别数学公式 |
| 图片描述 | `llm_image_description_enabled` | False | 生成图片描述 |
| 手写识别 | `llm_handwriting_enabled` | False | 识别手写内容 |
| 智能降噪 | `llm_noise_removal_enabled` | False | 过滤无关符号 |
| 页面校正 | `llm_page_correction_enabled` | False | 修正页面结构 |
| 章节识别 | `llm_section_header_enabled` | False | 标记章节标题 |
| 表单识别 | `llm_form_enabled` | False | 提取表单内容 |
| 复杂区域处理 | `llm_complex_region_enabled` | False | 处理复杂布局 |
| 印刷页码修正 | `llm_printed_page_correction_enabled` | False | 修正印刷页码 |
| 启发式版面增强 | `llm_heuristic_layout_enabled` | False | 优化版面检测 |

---

## 2. 配置传递流程

### 2.1 配置收集

UI 收集的配置通过 `config_params` 字典传递：

```python
config_params = {
    "use_llm": use_llm,
    "llm_provider": llm_provider,
    "llm_api_key": llm_api_key,
    "llm_model": llm_model,
    "llm_max_concurrency": llm_max_concurrency,
    "llm_table_enabled": llm_table_enabled,
    "llm_equation_enabled": llm_equation_enabled,
    # ... 其他模块开关 ...
}
```

### 2.2 配置处理

**代码位置**: [marker/scripts/streamlit_app.py:81-269](marker/scripts/streamlit_app.py#L81-L269)

`build_config_dict` 函数处理配置：

```python
def build_config_dict(config_params: dict) -> dict:
    # ...

    # LLM 配置
    if config_params.get("use_llm"):
        llm_provider = config_params.get("llm_provider", "gemini")

        # 通用 LLM 配置
        cli["use_llm"] = True
        cli["llm_max_concurrency"] = config_params.get("llm_max_concurrency", 3)

        # 模块开关 - 这些被设置到 config 中
        cli["llm_table_enabled"] = config_params.get("llm_table_enabled", True)
        cli["llm_equation_enabled"] = config_params.get("llm_equation_enabled", True)
        cli["llm_image_description_enabled"] = config_params.get("llm_image_description_enabled", False)
        cli["llm_handwriting_enabled"] = config_params.get("llm_handwriting_enabled", False)
        cli["llm_page_correction_enabled"] = config_params.get("llm_page_correction_enabled", False)
        cli["llm_section_header_enabled"] = config_params.get("llm_section_header_enabled", False)
        cli["llm_form_enabled"] = config_params.get("llm_form_enabled", False)
        cli["llm_complex_region_enabled"] = config_params.get("llm_complex_region_enabled", False)
        cli["llm_noise_removal_enabled"] = config_params.get("llm_noise_removal_enabled", False)
        cli["llm_printed_page_correction_enabled"] = config_params.get("llm_printed_page_correction_enabled", False)

        # 映射 provider 到 service 类
        provider_to_service = {
            "gemini": "marker.services.gemini.GoogleGeminiService",
            "azure": "marker.services.azure_openai.AzureOpenAIService",
            "claude": "marker.services.claude.ClaudeService",
            "ollama": "marker.services.ollama.OllamaService",
        }

        cli["llm_service"] = provider_to_service[llm_provider]

        # 设置 provider 特定配置
        if llm_provider == "gemini":
            cli["gemini_api_key"] = config_params["llm_api_key"]
            cli["gemini_model"] = config_params["llm_model"]
        # ... 其他 provider ...
```

### 2.3 配置使用

配置被传递到 PdfConverter：

**代码位置**: [marker/converters/pdf.py:110-152](marker/converters/pdf.py#L110-L152)

```python
def __init__(self, artifact_dict, processor_list=None, renderer=None, llm_service=None, config=None):
    super().__init__(config)

    # 初始化处理器列表
    if processor_list is not None:
        processor_list = strings_to_classes(processor_list)
    else:
        processor_list = self.default_processors  # 使用默认处理器列表

    # 初始化 LLM service
    if config.get("use_llm", False):
        llm_service = self.resolve_dependencies(self.default_llm_service)

    self.artifact_dict["llm_service"] = llm_service
    self.llm_service = llm_service

    # 初始化处理器
    processor_list = self.initialize_processors(processor_list)
    self.processor_list = processor_list
```

---

## 3. 🔴 发现的严重问题

### 3.1 问题描述

**UI 中的 11 个 LLM 模块开关并未真正控制处理器的启用/禁用！**

#### 证据 1: 配置被设置但未使用

配置中设置了这些标志：
```python
cli["llm_table_enabled"] = True
cli["llm_equation_enabled"] = True
# ...
```

但是搜索整个代码库：
```bash
$ grep -r "llm_table_enabled" marker/
marker/scripts/streamlit_app.py:  cli["llm_table_enabled"] = ...
# 只在 streamlit_app.py 中出现！
```

#### 证据 2: 处理器不检查这些标志

**LLMTableProcessor** 代码：
```python
class LLMTableProcessor(BaseLLMComplexBlockProcessor):
    block_types = (BlockTypes.Table, BlockTypes.TableOfContents)
    # 没有 llm_table_enabled 参数
    # 没有检查 config["llm_table_enabled"]
```

**BaseLLMProcessor** 只检查全局 `use_llm` 标志：
```python
class BaseLLMProcessor(BaseProcessor):
    use_llm: bool = False  # 只有这一个开关

    def __init__(self, llm_service: BaseService, config=None):
        super().__init__(config)

        self.llm_service = None
        if not self.use_llm:  # 只检查 use_llm
            return

        self.llm_service = llm_service
```

#### 证据 3: 所有 LLM 处理器都在默认列表中

**代码位置**: [marker/converters/pdf.py:77-107](marker/converters/pdf.py#L77-L107)

```python
default_processors: Tuple[BaseProcessor, ...] = (
    OrderProcessor,
    # ... 其他处理器 ...
    LLMTableProcessor,           # 总是包含
    LLMTableMergeProcessor,      # 总是包含
    LLMFormProcessor,            # 总是包含
    LLMComplexRegionProcessor,   # 总是包含
    LLMImageDescriptionProcessor,# 总是包含
    LLMEquationProcessor,        # 总是包含
    LLMHandwritingProcessor,     # 总是包含
    LLMMathBlockProcessor,       # 总是包含
    LLMSectionHeaderProcessor,   # 总是包含
    LLMPageCorrectionProcessor,  # 总是包含
    # ... 其他处理器 ...
)
```

所有 LLM 处理器都在默认列表中，没有根据配置动态添加/移除的逻辑。

### 3.2 实际行为

**当前实际行为**:
1. 用户勾选 "启用 LLM 增强" → 所有 LLM 处理器都运行
2. 用户取消勾选某个模块（如"图片描述"）→ **该处理器仍然运行**
3. 用户只勾选"表格优化"和"公式识别" → **所有 10 个处理器都运行**

**用户期望行为**:
1. 用户勾选 "启用 LLM 增强" + 只勾选"表格优化" → 只运行 LLMTableProcessor
2. 用户取消勾选"图片描述" → LLMImageDescriptionProcessor 不运行
3. 用户勾选所有模块 → 所有处理器运行

### 3.3 影响

#### 性能影响
- 用户以为只启用了 2 个模块，实际运行了 10 个模块
- 浪费 API 调用次数和费用
- 处理时间比预期长得多

#### 用户体验影响
- UI 显示的开关是"假开关"，误导用户
- 用户无法精确控制哪些 LLM 功能运行
- 无法针对特定文档类型优化处理流程

#### 成本影响
- 不必要的 API 调用导致额外费用
- 特别是图片描述等高成本功能，用户以为关闭了但实际在运行

---

## 4. 并发配置分析

### 4.1 并发数配置

**UI 配置**: [marker/scripts/streamlit_app.py:1567-1574](marker/scripts/streamlit_app.py#L1567-L1574)

```python
llm_max_concurrency = st.number_input(
    "最大并发数",
    min_value=1,
    max_value=50,
    value=3,
    help="同时处理的LLM请求数。多Key时可设置更高值。",
)
```

### 4.2 配置传递

**代码位置**: [marker/scripts/streamlit_app.py:187](marker/scripts/streamlit_app.py#L187)

```python
cli["llm_max_concurrency"] = config_params.get("llm_max_concurrency", 3)
```

### 4.3 后端使用

**代码位置**: [marker/processors/llm/__init__.py:42-45](marker/processors/llm/__init__.py#L42-L45)

```python
class BaseLLMProcessor(BaseProcessor):
    max_concurrency: int = 3  # 默认值
```

配置通过 `assign_config(self, config)` 传递到处理器实例。

### 4.4 多 Key 支持

**UI 智能提示**: [marker/scripts/streamlit_app.py:1553-1559](marker/scripts/streamlit_app.py#L1553-L1559)

```python
if llm_api_key:
    keys = [k.strip() for k in llm_api_key.replace('\n', ',').split(',') if k.strip()]
    key_count = len(keys)
    if key_count > 1:
        st.success(f"✅ 检测到 {key_count} 个API Key")
        suggested_concurrent = key_count * 3
        st.info(f"💡 建议并发数: {suggested_concurrent} (Key数量 × 3)")
```

**后端实现**: [marker/services/gemini.py:59-73](marker/services/gemini.py#L59-L73)

```python
# 如果有多个密钥，增加重试次数
if hasattr(self, 'key_rotator') and self.key_rotator.get_key_count() > 1:
    max_retries = max(max_retries, self.key_rotator.get_key_count())

# 每次重试使用不同的密钥
current_key = self.key_rotator.get_current_key()
client = self.get_google_client(timeout=timeout, api_key=current_key)
```

### 4.5 并发配置评估

✅ **工作正常**:
- UI 配置正确传递到后端
- ThreadPoolExecutor 使用配置的并发数
- 多 Key 轮换机制工作正常
- UI 提供智能建议

---

## 5. 解决方案

### 5.1 方案 A: 动态过滤处理器列表 (推荐)

在 PdfConverter 初始化时，根据配置过滤处理器列表：

```python
def __init__(self, artifact_dict, processor_list=None, renderer=None, llm_service=None, config=None):
    super().__init__(config)

    # ... 现有代码 ...

    if processor_list is None:
        processor_list = self.default_processors

    # 🆕 根据配置过滤 LLM 处理器
    if config and config.get("use_llm"):
        processor_list = self._filter_llm_processors(processor_list, config)

    # ... 现有代码 ...

def _filter_llm_processors(self, processor_list, config):
    """根据配置过滤 LLM 处理器"""
    # 处理器类到配置键的映射
    processor_config_map = {
        LLMTableProcessor: "llm_table_enabled",
        LLMTableMergeProcessor: "llm_table_enabled",  # 表格合并依赖表格优化
        LLMEquationProcessor: "llm_equation_enabled",
        LLMImageDescriptionProcessor: "llm_image_description_enabled",
        LLMHandwritingProcessor: "llm_handwriting_enabled",
        LLMPageCorrectionProcessor: "llm_page_correction_enabled",
        LLMSectionHeaderProcessor: "llm_section_header_enabled",
        LLMFormProcessor: "llm_form_enabled",
        LLMComplexRegionProcessor: "llm_complex_region_enabled",
        LLMMathBlockProcessor: "llm_equation_enabled",  # 数学块依赖公式识别
    }

    filtered_list = []
    for processor_cls in processor_list:
        # 非 LLM 处理器，保留
        if processor_cls not in processor_config_map:
            filtered_list.append(processor_cls)
            continue

        # LLM 处理器，检查配置
        config_key = processor_config_map[processor_cls]
        if config.get(config_key, False):
            filtered_list.append(processor_cls)
        else:
            logger.info(f"Skipping {processor_cls.__name__} (disabled in config)")

    return tuple(filtered_list)
```

### 5.2 方案 B: 处理器内部检查

在每个 LLM 处理器的 `__call__` 方法中检查配置：

```python
class LLMTableProcessor(BaseLLMComplexBlockProcessor):
    llm_table_enabled: bool = True  # 新增配置项

    def __call__(self, document: Document):
        # 🆕 检查模块是否启用
        if not self.llm_table_enabled:
            logger.info(f"{self.__class__.__name__} disabled, skipping")
            return

        # 现有逻辑
        if not self.use_llm or self.llm_service is None:
            return

        try:
            self.rewrite_blocks(document)
        except Exception as e:
            logger.warning(f"Error rewriting blocks: {e}")
```

需要为每个处理器添加对应的配置项。

### 5.3 方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **方案 A** | - 处理器不会被初始化，节省内存<br>- 集中管理，易于维护<br>- 不需要修改每个处理器 | - 需要维护映射表 | ⭐⭐⭐⭐⭐ |
| **方案 B** | - 每个处理器独立控制<br>- 更灵活 | - 需要修改所有处理器<br>- 处理器仍会被初始化<br>- 分散管理，难以维护 | ⭐⭐⭐ |

**推荐**: 方案 A

---

## 6. 其他发现

### 6.1 智能降噪功能未实现

UI 中有"智能降噪"选项：
```python
llm_noise_removal_enabled = st.checkbox("智能降噪", value=False)
```

但是代码库中没有对应的处理器：
```bash
$ grep -r "NoiseRemoval" marker/
# 没有结果
```

**建议**: 移除 UI 中的这个选项，或者实现对应的处理器。

### 6.2 启发式版面增强功能未实现

UI 中有"启发式版面增强"选项：
```python
llm_heuristic_layout_enabled = st.checkbox("启发式版面增强", value=False)
```

但是代码库中没有对应的处理器：
```bash
$ grep -r "HeuristicLayout" marker/
# 没有结果
```

**建议**: 移除 UI 中的这个选项，或者实现对应的处理器。

### 6.3 印刷页码修正功能未关联

UI 中有"印刷页码修正"选项，但这个功能实际上不是 LLM 处理器，而是一个独立的后处理模块。

**建议**: 将这个选项移到其他配置区域，不要放在 LLM 模块中。

---

## 7. 总结

### 7.1 核心问题

🔴 **严重**: UI 中的 11 个 LLM 模块开关是"假开关"，不控制实际行为

### 7.2 次要问题

⚠️ **中等**:
- "智能降噪"功能未实现但显示在 UI 中
- "启发式版面增强"功能未实现但显示在 UI 中
- "印刷页码修正"不是 LLM 功能但放在 LLM 区域

### 7.3 工作正常的部分

✅ **正常**:
- 全局 "启用 LLM 增强" 开关工作正常
- API 提供商配置正确传递
- 并发数配置工作正常
- 多 Key 轮换机制工作正常

### 7.4 行动建议

**立即**:
1. 在 UI 中添加警告说明：当前模块开关不生效，启用 LLM 后所有模块都会运行
2. 或者暂时隐藏模块开关，只保留全局开关

**短期** (1-2 周):
1. 实现方案 A：动态过滤处理器列表
2. 移除未实现的功能选项（智能降噪、启发式版面增强）
3. 将印刷页码修正移到合适的配置区域

**中期** (1-2 月):
1. 添加处理器依赖关系管理（如表格合并依赖表格优化）
2. 添加配置验证和冲突检测
3. 改进 UI 反馈，显示实际运行的处理器列表

---

## 8. 测试建议

### 8.1 验证问题

创建测试脚本验证当前行为：

```python
# test_llm_module_switches.py
import os
os.environ["GEMINI_API_KEY"] = "test-key"

from marker.converters.pdf import PdfConverter

# 测试 1: 只启用表格优化
config = {
    "use_llm": True,
    "llm_table_enabled": True,
    "llm_equation_enabled": False,
    "llm_image_description_enabled": False,
    # ... 其���都是 False
}

converter = PdfConverter(artifact_dict={}, config=config)

# 检查处理器列表
llm_processors = [p for p in converter.processor_list
                  if "LLM" in p.__class__.__name__]

print(f"Expected: 1-2 LLM processors (Table + TableMerge)")
print(f"Actual: {len(llm_processors)} LLM processors")
for p in llm_processors:
    print(f"  - {p.__class__.__name__}")

# 预期结果: 应该只有 LLMTableProcessor 和 LLMTableMergeProcessor
# 实际结果: 会有所有 10 个 LLM 处理器
```

### 8.2 验证修复

修复后运行相同的测试，确保：
1. 只启用的模块对应的处理器在列表中
2. 未启用的模块对应的处理器不在列表中
3. 依赖关系正确处理（如表格合并依赖表格优化）

---

## 9. 参考文件

### UI 相关
- [marker/scripts/streamlit_app.py:1519-1756](marker/scripts/streamlit_app.py#L1519-L1756) - LLM UI 配置
- [marker/scripts/streamlit_app.py:81-269](marker/scripts/streamlit_app.py#L81-L269) - build_config_dict

### 后端相关
- [marker/converters/pdf.py:77-152](marker/converters/pdf.py#L77-L152) - PdfConverter 初始化
- [marker/converters/__init__.py:43-63](marker/converters/__init__.py#L43-L63) - initialize_processors
- [marker/processors/llm/__init__.py](marker/processors/llm/__init__.py) - LLM 处理器基类
- [marker/processors/llm/llm_meta.py](marker/processors/llm/llm_meta.py) - 元处理器

### 处理器
- [marker/processors/llm/llm_table.py](marker/processors/llm/llm_table.py)
- [marker/processors/llm/llm_equation.py](marker/processors/llm/llm_equation.py)
- [marker/processors/llm/llm_image_description.py](marker/processors/llm/llm_image_description.py)
- [marker/processors/llm/llm_handwriting.py](marker/processors/llm/llm_handwriting.py)
- [marker/processors/llm/llm_form.py](marker/processors/llm/llm_form.py)
- [marker/processors/llm/llm_complex.py](marker/processors/llm/llm_complex.py)
- [marker/processors/llm/llm_page_correction.py](marker/processors/llm/llm_page_correction.py)
- [marker/processors/llm/llm_sectionheader.py](marker/processors/llm/llm_sectionheader.py)

---

**报告生成时间**: 2026-02-03
**分析工具**: Claude Code (Sonnet 4.5)
**代码库**: marker_cuda
**问题严重程度**: 🔴 高 - UI 功能与实际行为不符
