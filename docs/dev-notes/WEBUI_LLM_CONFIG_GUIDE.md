# WebUI LLM 增强配置指南

## 概述

Marker WebUI 现在支持详细的 LLM 增强配置,允许您:
- 选择不同的 LLM 提供商(OpenAI、Gemini、Azure、Claude、Ollama)
- 自定义模型和 API 配置
- 独立控制每个 LLM 处理模块的开关
- 使用 OpenAI 兼容协议,支持各种第三方服务

## 配置界面

### 1. 启用 LLM 增强

在侧边栏找到 **🧠 LLM 增强** 部分,勾选 **"启用 LLM 增强"** 复选框。

### 2. 选择 API 提供商

支持以下提供商:

#### OpenAI 兼容 API (推荐)

适用于:
- OpenAI 官方 API
- LM Studio 本地服务
- vLLM 部署
- Ollama (通过兼容层)
- 各种第三方 OpenAI 兼容服务

配置项:
- **Base URL**: API 基础地址
  - OpenAI 官方: `https://api.openai.com/v1`
  - LM Studio: `http://127.0.0.1:1234/v1`
  - 自定义服务: 根据实际情况填写
- **模型名称**: 如 `gpt-4o-mini`, `qwen-vl-max`, `deepseek-chat`
- **API Key**: API 密钥(LM Studio 可填任意值)
- **最大并发数**: 同时处理的请求数(1-20,默认3)
- **超时时间**: 请求超时时间(30-300秒,默认120)

#### Google Gemini

配置项:
- **Gemini API Key**: Google AI Studio 获取的 API 密钥
- **模型名称**: 如 `gemini-2.0-flash-exp`, `gemini-1.5-pro`
- **最大并发数**: 默认3

#### Azure OpenAI

配置项:
- **Azure Endpoint**: Azure OpenAI 端点 URL
- **API Key**: Azure 订阅密钥
- **Deployment Name**: Azure 部署名称

#### Anthropic Claude

配置项:
- **Claude API Key**: Anthropic 控制台获取的密钥
- **模型**: 选择 Claude 模型版本

#### Ollama 本地模型

配置项:
- **Ollama URL**: Ollama 服务地址(默认 `http://localhost:11434`)
- **模型名称**: 如 `llama3.2-vision`, `qwen2-vl`

### 3. LLM 处理模块配置

可以独立控制每个 LLM 增强功能:

#### 默认启用的模块

- **表格优化**: 修正表格结构,确保列对齐正确
- **公式识别**: 识别和转换数学公式

#### 可选模块

- **图片描述**: 为图片生成描述性文本
- **手写识别**: 识别手写内容
- **页面校正**: 修正页面结构和阅读顺序
- **��节识别**: 识别和标记章节标题
- **表单识别**: 识别和提取表单内容
- **复杂区域处理**: 处理复杂布局区域

#### 自定义提示词

如果启用了 **页面校正** 模块,可以自定义提示词来指导 LLM 如何修正页面结构。留空则使用默认提示词。

## 使用示例

### 示例 1: 使用 LM Studio 本地模型

1. 启动 LM Studio 并加载支持视觉的模型(如 `llava-v1.6-34b`)
2. 在 WebUI 中:
   - 勾选 "启用 LLM 增强"
   - 选择 "OpenAI 兼容 API"
   - Base URL: `http://127.0.0.1:1234/v1`
   - 模型名称: `llava-v1.6-34b`
   - API Key: 任意值(如 `lm-studio`)
   - 启用需要的模块(如表格优化、公式识别)

### 示例 2: 使用 OpenAI 官方 API

1. 获取 OpenAI API Key
2. 在 WebUI 中:
   - 勾选 "启用 LLM 增强"
   - 选择 "OpenAI 兼容 API"
   - Base URL: `https://api.openai.com/v1`
   - 模型名称: `gpt-4o-mini`
   - API Key: 您的 OpenAI API Key
   - 根据需要调整并发数和超时时间

### 示例 3: 使用 Gemini

1. 从 Google AI Studio 获取 API Key
2. 在 WebUI 中:
   - 勾选 "启用 LLM 增强"
   - 选择 "Google Gemini"
   - Gemini API Key: 您的 API Key
   - 模型名称: `gemini-2.0-flash-exp`

### 示例 4: 人文社科文献处理

处理古籍或历史文献时:
1. 启用 LLM 增强
2. 选择合适的 API 提供商和模型
3. 启用以下模块:
   - ✅ 表格优化
   - ✅ 页面校正
   - ✅ 章节识别
   - ✅ 手写识别(如有手写内容)
4. 在页面校正自定义提示词中添加:
   ```
   这是一份中文古籍文献,采用竖排版式,从右到左阅读。
   请修正页面结构,确保阅读顺序正确,并识别章节标题。
   ```

## 环境变量配置

可以通过环境变量设置默认值:

```bash
# OpenAI 兼容 API
export LLM_BASE_URL="http://127.0.0.1:1234/v1"
export LLM_MODEL="gpt-4o-mini"
export LLM_API_KEY="your-api-key"

# Gemini
export GEMINI_API_KEY="your-gemini-key"
export GEMINI_MODEL="gemini-2.0-flash-exp"

# Azure
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-azure-key"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"

# Claude
export CLAUDE_API_KEY="your-claude-key"

# Ollama
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="llama3.2-vision"
```

## 性能建议

1. **并发数设置**:
   - 本地模型(LM Studio/Ollama): 1-3
   - 云端 API: 3-10
   - 根据 API 限流和机器性能调整

2. **超时时间**:
   - 简单文档: 60-120秒
   - 复杂文档: 120-300秒

3. **模块选择**:
   - 只启用必要的模块以提高速度
   - 表格优化和公式识别通常最有用
   - 页面校正适合复杂布局文档

## 故障排除

### LLM 请求失败

1. 检查 Base URL 是否正确
2. 确认 API Key 有效
3. 检查网络连接
4. 查看超时时间是否足够
5. 检查模型名称是否正确

### 处理速度慢

1. 减少并发数
2. 只启用必要的模块
3. 使用更快的模型(如 gpt-4o-mini 而不是 gpt-4o)
4. 考虑使用本地模型

### 结果不理想

1. 尝试不同的模型
2. 调整自定义提示词
3. 检查是否启用了正确的模块
4. 对于特定文档类型,使用针对性的配置

## 技术细节

### 配置传递流程

```
WebUI 界面
  ↓
config_params 字典
  ↓
build_config_dict() 函数
  ↓
ConfigParser
  ↓
PdfConverter
  ↓
LLM Processors
```

### 支持的配置参数

```python
{
    "use_llm": True,
    "llm_provider": "openai",  # openai, gemini, azure, claude, ollama
    "llm_base_url": "http://127.0.0.1:1234/v1",
    "llm_model": "gpt-4o-mini",
    "llm_api_key": "your-key",
    "llm_max_concurrency": 3,
    "llm_timeout": 120,
    
    # 模块开关
    "llm_table_enabled": True,
    "llm_equation_enabled": True,
    "llm_image_description_enabled": False,
    "llm_handwriting_enabled": False,
    "llm_page_correction_enabled": False,
    "llm_section_header_enabled": False,
    "llm_form_enabled": False,
    "llm_complex_region_enabled": False,
    
    # 自定义提示词
    "llm_page_correction_prompt": "..."
}
```

## 更新日志

### v2.0 (2026-01-26)

- ✨ 新增详细的 LLM 配置界面
- ✨ 支持多种 LLM 提供商(OpenAI、Gemini、Azure、Claude、Ollama)
- ✨ 独立的模块开关控制
- ✨ OpenAI 兼容协议支持
- ✨ 自定义提示词功能
- 🔧 改进配置传递机制
- 📚 完善文档和示例

