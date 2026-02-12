# WebUI LLM 配置增强 - 更新说明

## 更新概述

将 WebUI 中的 LLM 增强功能从简单的开关升级为完整的配置系统,支持多种 LLM 提供商、模块化控制和自定义配置。

## 主要变更

### 1. 新增 LLM 配置界面

**位置**: 侧边栏 "🧠 LLM 增强" 部分

**功能**:
- ✅ 支持 5 种 LLM 提供商选择
- ✅ 详细的 API 配置选项
- ✅ 8 个独立的模块开关
- ✅ 自定义提示词支持

### 2. 支持的 LLM 提供商

| 提供商 | 配置项 | 适用场景 |
|--------|--------|----------|
| **OpenAI 兼容 API** | Base URL, Model, API Key, 并发数, 超时 | 通用,支持 LM Studio、vLLM 等 |
| **Google Gemini** | API Key, Model, 并发数 | Google 生态用户 |
| **Azure OpenAI** | Endpoint, API Key, Deployment | 企业用户 |
| **Anthropic Claude** | API Key, Model | Claude 用户 |
| **Ollama** | URL, Model | 本地部署 |

### 3. LLM 处理模块

#### 默认启用
- ✅ **表格优化**: 修正表格结构
- ✅ **公式识别**: 识别数学公式

#### 可选启用
- ⬜ **图片描述**: 生成图片描述
- ⬜ **手写识别**: 识别手写内容
- ⬜ **页面校正**: 修正页面结构
- ⬜ **章节识别**: 识别章节标题
- ⬜ **表单识别**: 提取表单内容
- ⬜ **复杂区域处理**: 处理复杂布局

### 4. 代码变更

#### 文件: `marker/scripts/streamlit_app.py`

**变更 1: 移除简单的 LLM 开关**
```python
# 旧代码 (第 573 行)
use_llm = st.checkbox("🧠 启用 LLM 增强", value=False, help="使用 Gemini 优化文档结构")

# 新代码
# LLM 增强配置移到独立区块
```

**变更 2: 新增详细的 LLM 配置界面**
```python
# 新增 (第 743 行之后)
st.subheader("🧠 LLM 增强")
use_llm = st.checkbox("启用 LLM 增强", value=False, help="使用大语言模型优化文档结构和内容")

if use_llm:
    with st.expander("LLM 配置", expanded=True):
        # API 提供商选择
        llm_provider = st.selectbox(...)
        
        # 各提供商的详细配置
        if llm_provider == "openai":
            llm_base_url = st.text_input(...)
            llm_model = st.text_input(...)
            llm_api_key = st.text_input(...)
            # ...
        
        # LLM 处理模块配置
        llm_table_enabled = st.checkbox(...)
        llm_equation_enabled = st.checkbox(...)
        # ...
```

**变更 3: 移除高级选项中的旧 LLM 配置**
```python
# 删除 (原第 870-877 行)
if use_llm:
    st.markdown("---")
    st.markdown("**LLM 配置（Gemini）**")
    gemini_api_key = st.text_input("Gemini API Key", value=gemini_api_key, type="password")
    gemini_model = st.text_input("Gemini Model", value=gemini_model)
```

**变更 4: 更新 build_config_dict 函数**
```python
# 旧代码 (第 168-173 行)
if config_params.get("use_llm"):
    if config_params.get("gemini_api_key"):
        cli["gemini_api_key"] = config_params["gemini_api_key"]
    if config_params.get("gemini_model"):
        cli["gemini_model"] = config_params["gemini_model"]

# 新代码
if config_params.get("use_llm"):
    llm_provider = config_params.get("llm_provider", "openai")
    
    # 通用 LLM 配置
    cli["use_llm"] = True
    cli["llm_max_concurrency"] = config_params.get("llm_max_concurrency", 3)
    
    # 模块开关
    cli["llm_table_enabled"] = config_params.get("llm_table_enabled", True)
    cli["llm_equation_enabled"] = config_params.get("llm_equation_enabled", True)
    # ... 其他模块
    
    # 根据提供商配置
    if llm_provider == "openai":
        cli["llm_provider"] = "openai"
        cli["llm_base_url"] = config_params.get("llm_base_url")
        cli["llm_model"] = config_params.get("llm_model")
        # ...
    elif llm_provider == "gemini":
        # Gemini 配置
    # ... 其他提供商
```

**变更 5: 更新配置参数传递**
```python
# 旧代码 (第 1090-1094 行)
if use_llm:
    config_params.update({
        "gemini_api_key": gemini_api_key,
        "gemini_model": gemini_model,
    })

# 新代码
if use_llm:
    config_params.update({
        "llm_provider": llm_provider,
        "llm_base_url": llm_base_url if llm_provider in ["openai", "azure", "ollama"] else None,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "llm_max_concurrency": llm_max_concurrency,
        "llm_timeout": llm_timeout if llm_provider == "openai" else 120,
        "llm_table_enabled": llm_table_enabled,
        "llm_equation_enabled": llm_equation_enabled,
        # ... 其他模块开关
        "llm_page_correction_prompt": llm_page_correction_prompt,
    })
```

**变更 6: 移除旧的默认值初始化**
```python
# 删除 (原第 316-317 行)
gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
gemini_model = os.environ.get("GEMINI_MODEL", "")
```

## 配置参数映射

### 新增配置参数

```python
# 通用配置
"llm_provider"              # LLM 提供商: openai, gemini, azure, claude, ollama
"llm_max_concurrency"       # 最大并发数: 1-20, 默认 3

# OpenAI 兼容配置
"llm_base_url"              # API 基础 URL
"llm_model"                 # 模型名称
"llm_api_key"               # API 密钥
"llm_timeout"               # 超时时间(秒)

# 模块开关
"llm_table_enabled"         # 表格优化
"llm_equation_enabled"      # 公式识别
"llm_image_description_enabled"  # 图片描述
"llm_handwriting_enabled"   # 手写识别
"llm_page_correction_enabled"    # 页面校正
"llm_section_header_enabled"     # 章节识别
"llm_form_enabled"          # 表单识别
"llm_complex_region_enabled"     # 复杂区域处理

# 自定义提示词
"llm_page_correction_prompt"     # 页面校正提示词
```

### 保留的配置参数(向后兼容)

```python
"gemini_api_key"            # Gemini API 密钥
"gemini_model"              # Gemini 模型名称
"azure_endpoint"            # Azure 端点
"azure_api_key"             # Azure API 密钥
"azure_deployment"          # Azure 部署名称
"claude_api_key"            # Claude API 密钥
"claude_model"              # Claude 模型
"ollama_base_url"           # Ollama URL
"ollama_model"              # Ollama 模型
```

## 使用示例

### 示例 1: 使用 LM Studio

```python
# WebUI 配置
启用 LLM 增强: ✅
API 提供商: OpenAI 兼容 API
Base URL: http://127.0.0.1:1234/v1
模型名称: llava-v1.6-34b
API Key: lm-studio
最大并发数: 3

模块配置:
✅ 表格优化
✅ 公式识别
⬜ 其他模块
```

### 示例 2: 使用 OpenAI 官方 API

```python
# WebUI 配置
启用 LLM 增强: ✅
API 提供商: OpenAI 兼容 API
Base URL: https://api.openai.com/v1
模型名称: gpt-4o-mini
API Key: sk-...
最大并发数: 5
超时时间: 120

模块配置:
✅ 表格优化
✅ 公式识别
✅ 页面校正
⬜ 其他模块
```

### 示例 3: 处理古籍文献

```python
# WebUI 配置
启用 LLM 增强: ✅
API 提供商: OpenAI 兼容 API
Base URL: https://api.openai.com/v1
模型名称: gpt-4o
API Key: sk-...

模块配置:
✅ 表格优化
✅ 页面校正
✅ 章节识别
✅ 手写识别

页面校正自定义提示词:
这是一份中文古籍文献,采用竖排版式,从右到左阅读。
请修正页面结构,确保阅读顺序正确,并识别章节标题。
```

## 环境变量支持

可以通过环境变量设置默认值:

```bash
# OpenAI 兼容
export LLM_BASE_URL="http://127.0.0.1:1234/v1"
export LLM_MODEL="gpt-4o-mini"
export LLM_API_KEY="your-key"

# Gemini
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-2.0-flash-exp"

# Azure
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"

# Claude
export CLAUDE_API_KEY="your-key"

# Ollama
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="llama3.2-vision"
```

## 向后兼容性

- ✅ 保留了原有的 Gemini 配置参数
- ✅ 默认行为不变(LLM 增强默认关闭)
- ✅ 环境变量继续有效
- ✅ 旧的配置文件仍然可用

## 测试建议

1. **基础测试**:
   - 启用/禁用 LLM 增强
   - 切换不同的提供商
   - 测试各个模块开关

2. **API 测试**:
   - OpenAI 官方 API
   - LM Studio 本地服务
   - Gemini API
   - 其他兼容服务

3. **功能测试**:
   - 表格优化效果
   - 公式识别准确性
   - 页面校正功能
   - 自定义提示词效果

4. **性能测试**:
   - 不同并发数的影响
   - 超时设置的合理性
   - 多模块同时启用的性能

## 文档

- 📚 [WebUI LLM 配置指南](WEBUI_LLM_CONFIG_GUIDE.md)
- 📚 [LLM 辅助系统技术设计](HUMANITIES_LLM_TECHNICAL_DESIGN.md)
- 📚 [LLM 辅助功能完整指南](LLM_ASSISTANCE_GUIDE.md)

## 后续计划

1. **后端实现**:
   - 实现 OpenAI 兼容的 LLM 服务适配器
   - 添加模块开关的实际控制逻辑
   - 实现自定义提示词功能

2. **功能增强**:
   - 添加更多 LLM 处理模块
   - 支持更多提供商
   - 优化提示词模板

3. **用户体验**:
   - 添加配置预设
   - 保存/加载配置
   - 配置验证和错误提示

