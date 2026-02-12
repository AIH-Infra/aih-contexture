# LLM Provider Configuration Fix

## 问题描述

当启用 LLM 增强功能时，系统报错：
```
In order to use GoogleGeminiService, you must set the configuration values gemini_api_key
```

即使用户选择了其他 LLM 提供商（如 OpenAI、Claude 等），系统仍然尝试使用 Gemini 服务。

## 根本原因

1. **配置参数不匹配**：
   - Streamlit UI 设置 `llm_provider` 参数（如 "openai", "gemini", "claude"）
   - 但 marker 的 `ConfigParser` 期望 `llm_service` 参数（完整类路径）
   - 当 `llm_service` 未设置时，默认使用 `GoogleGeminiService`

2. **OpenAI 服务类已删除**：
   - `marker/services/openai.py` 已被删除（见 git status）
   - 但 UI 仍然提供 "OpenAI 兼容 API" 选项
   - 导致无法正确实例化服务

## 解决方案

### 1. 添加 Provider 到 Service 的映射

在 `build_config_dict()` 函数中添加映射逻辑：

```python
# 映射 llm_provider 到 llm_service 类路径
provider_to_service = {
    "gemini": "marker.services.gemini.GoogleGeminiService",
    "azure": "marker.services.azure_openai.AzureOpenAIService",
    "claude": "marker.services.claude.ClaudeService",
    "ollama": "marker.services.ollama.OllamaService",
}

# 设置 llm_service 参数（ConfigParser 需要这个）
if llm_provider in provider_to_service:
    cli["llm_service"] = provider_to_service[llm_provider]
```

### 2. 移除 OpenAI 选项，使用 Ollama 替代

由于 OpenAI 服务类已删除，我们：
- 从 UI 中移除 "openai" 选项
- 更新 Ollama 选项说明，标明它支持 OpenAI 兼容 API
- 用户可以通过 Ollama 连接到任何 OpenAI 兼容的 API（LM Studio、vLLM、OpenAI 等）

### 3. 更新 UI 配置

**修改前**：
```python
options=["openai", "gemini", "azure", "claude", "ollama"]
```

**修改后**：
```python
options=["gemini", "ollama", "azure", "claude"]
format_func=lambda x: {
    "gemini": "Google Gemini（推荐）",
    "ollama": "Ollama（支持 OpenAI 兼容 API）",
    "azure": "Azure OpenAI",
    "claude": "Anthropic Claude"
}
```

### 4. 增强 Ollama 配置

Ollama 配置现在支持：
- 本地 Ollama 服务（http://localhost:11434）
- OpenAI 兼容的远程 API（如 http://localhost:1234/v1）
- 可选的 API Key（本地不需要，远程需要）

## 配置示例

### 使用 Gemini

```python
llm_provider = "gemini"
llm_api_key = "your-gemini-api-key"
llm_model = "gemini-2.0-flash-exp"
```

### 使用 Ollama 连接本地模型

```python
llm_provider = "ollama"
llm_base_url = "http://localhost:11434"
llm_model = "llama3.2-vision"
llm_api_key = ""  # 不需要
```

### 使用 Ollama 连接 OpenAI API

```python
llm_provider = "ollama"
llm_base_url = "https://api.openai.com/v1"
llm_model = "gpt-4o-mini"
llm_api_key = "sk-..."
```

### 使用 Ollama 连接 LM Studio

```python
llm_provider = "ollama"
llm_base_url = "http://localhost:1234/v1"
llm_model = "qwen-vl-max"
llm_api_key = "lm-studio"  # 任意值
```

## 配置流程

```
Streamlit UI
  ↓
config_params (llm_provider="gemini")
  ↓
build_config_dict()
  ├─ 映射: llm_provider → llm_service
  ├─ 设置: cli["llm_service"] = "marker.services.gemini.GoogleGeminiService"
  └─ 设置: cli["gemini_api_key"] = "..."
  ↓
ConfigParser(cli)
  ↓
get_llm_service() → 返回 "marker.services.gemini.GoogleGeminiService"
  ↓
PdfConverter 实例化正确的服务类
```

## 测试建议

1. **测试 Gemini**：
   - 选择 Gemini 提供商
   - 输入有效的 API Key
   - 验证能正常处理文档

2. **测试 Ollama（本地）**：
   - 启动本地 Ollama 服务
   - 选择 Ollama 提供商
   - 使用本地模型（如 llama3.2-vision）

3. **测试 Ollama（OpenAI API）**：
   - 选择 Ollama 提供商
   - 设置 OpenAI API URL 和 Key
   - 验证能正常调用 OpenAI API

4. **测试 Azure 和 Claude**：
   - 验证各自的配置参数正确传递
   - 确认服务类正确实例化

## 相关文件

- `marker/scripts/streamlit_app.py`: UI 和配置构建
- `marker/config/parser.py`: 配置解析和服务实例化
- `marker/converters/pdf.py`: 转换器和默认服务
- `marker/services/`: 各个 LLM 服务实现

## 注意事项

1. **API Key 验证**：确保在使用前验证 API Key 是否有效
2. **错误处理**：添加更好的错误提示，告诉用户缺少哪些配置
3. **文档更新**：更新用户文档，说明如何使用 Ollama 连接 OpenAI API
4. **向后兼容**：如果有用户使用旧配置，需要提供迁移指南
