# WebUI LLM 配置 - 重复元素 ID 修复

## 问题描述

在添加 LLM 配置界面后,Streamlit 报错:

```
streamlit.errors.StreamlitDuplicateElementId: There are multiple number_input elements with the same auto-generated ID.
```

**症状:**
- 选择 Calamari OCR 后端时出现错误
- "开始转换" 按钮消失
- 界面无法正常渲染

## 问题原因

Streamlit 根据元素类型和参数自动生成元素 ID。当多个 `st.number_input` 或 `st.text_input` 使用相同的标签(如 "最大并发数")时,会生成相同的 ID,导致冲突。

在 LLM 配置中,不同提供商(OpenAI、Gemini、Azure 等)都有相同名称的输入框:
- "最大并发数" (在 OpenAI 和 Gemini 中)
- "API Key" (在多个提供商中)
- "模型名称" (在多个提供商中)

## 解决方案

为所有可能重复的输入框添加唯一的 `key` 参数。

### 修复的元素

#### OpenAI 配置
```python
llm_base_url = st.text_input(..., key="llm_openai_base_url")
llm_model = st.text_input(..., key="llm_openai_model")
llm_api_key = st.text_input(..., key="llm_openai_api_key")
llm_max_concurrency = st.number_input(..., key="llm_openai_max_concurrency")
llm_timeout = st.number_input(..., key="llm_openai_timeout")
```

#### Gemini 配置
```python
llm_api_key = st.text_input(..., key="llm_gemini_api_key")
llm_model = st.text_input(..., key="llm_gemini_model")
llm_max_concurrency = st.number_input(..., key="llm_gemini_max_concurrency")
```

#### Azure 配置
```python
llm_base_url = st.text_input(..., key="llm_azure_endpoint")
llm_api_key = st.text_input(..., key="llm_azure_api_key")
llm_model = st.text_input(..., key="llm_azure_deployment")
```

#### Claude 配置
```python
llm_api_key = st.text_input(..., key="llm_claude_api_key")
llm_model = st.selectbox(..., key="llm_claude_model")
```

#### Ollama 配置
```python
llm_base_url = st.text_input(..., key="llm_ollama_base_url")
llm_model = st.text_input(..., key="llm_ollama_model")
```

## 验证

修复后,应该能够:
1. ✅ 正常切换不同的 LLM 提供商
2. ✅ 所有输入框正常显示和工作
3. ✅ "开始转换" 按钮正常显示
4. ✅ 选择 Calamari OCR 后端不再报错

## 最佳实践

在 Streamlit 中,当有多个相似的输入框时,应该:
1. 始终为可能重复的元素添加唯一的 `key` 参数
2. 使用描述性的 key 名称(如 `llm_openai_api_key` 而不是 `key1`)
3. 在条件分支中使用不同的 key 前缀(如 `llm_openai_*`, `llm_gemini_*`)

## 相关文件

- [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py) - 主要修改文件

## 更新日志

- 2026-01-26: 修复重复元素 ID 问题,为所有 LLM 配置输入框添加唯一 key

