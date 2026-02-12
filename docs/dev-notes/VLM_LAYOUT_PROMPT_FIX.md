# VLM 版面识别提示词配置修复

## 问题描述

使用 VLM 版面识别后端时，系统报错：
```
AssertionError: In order to use VlmLayoutService, you must set the configuration values `vlm_layout_prompt, `.
```

然后自动回退到 Surya 版面识别。

## 根本原因

VlmLayoutService 要求至少设置以下配置之一：
- `vlm_layout_prompt`: 自定义提示词
- `vlm_layout_prompt_template`: 预制模板名称

但在某些情况下，两个参数都可能是空字符串：
1. 用户选择"使用预制模板"时，`vlm_layout_prompt` 被设置为空字符串
2. 用户选择"自定义提示词"时，`vlm_layout_prompt_template` 被设置为空字符串
3. 如果用户没有与 UI 交互，两者都可能为空

在配置传递过程中：
```python
# 原代码
if vlm_layout_prompt:  # 空字符串是 falsy，跳过
    vlm_layout_config["vlm_layout_prompt"] = vlm_layout_prompt
elif vlm_layout_prompt_template:  # 如果也是空字符串，也跳过
    vlm_layout_config["vlm_layout_prompt_template"] = vlm_layout_prompt_template
# 结果：两个都没有设置！
```

## 解决方案

### 1. 在配置传递时添加默认值

**位置**: `streamlit_app.py` 第 1269-1283 行

```python
# 版面识别 VLM 配置
if layout_backend == "vlm":
    vlm_layout_config = {
        "vlm_layout_timeout": vlm_layout_timeout,
    }

    # 提示词配置：优先使用直接指定的 prompt，否则使用模板
    # 确保至少有一个被设置（不能都为空）
    if vlm_layout_prompt and vlm_layout_prompt.strip():
        vlm_layout_config["vlm_layout_prompt"] = vlm_layout_prompt
    elif vlm_layout_prompt_template and vlm_layout_prompt_template.strip():
        vlm_layout_config["vlm_layout_prompt_template"] = vlm_layout_prompt_template
    else:
        # 如果都为空，使用默认模板
        vlm_layout_config["vlm_layout_prompt_template"] = "modern"
```

**改进点**：
- 使用 `.strip()` 检查字符串是否真的有内容（不只是空白）
- 如果两者都为空，自动设置默认模板 "modern"

### 2. 在 build_config_dict 中添加保护

**位置**: `streamlit_app.py` 第 100-118 行

```python
# 版面识别 VLM 配置
if layout_backend == "vlm":
    vlm_config = {
        "vlm_layout_timeout": int(config_params.get("vlm_layout_timeout", 120)),
    }

    # 提示词配置 - 确保至少有一个被设置
    has_prompt = False
    if config_params.get("vlm_layout_prompt"):
        vlm_config["vlm_layout_prompt"] = config_params["vlm_layout_prompt"]
        has_prompt = True
    if config_params.get("vlm_layout_prompt_template"):
        vlm_config["vlm_layout_prompt_template"] = config_params["vlm_layout_prompt_template"]
        has_prompt = True

    # 如果都没有设置，使用默认模板
    if not has_prompt:
        vlm_config["vlm_layout_prompt_template"] = "modern"
```

**改进点**：
- 双重保护：即使前面的逻辑失败，这里也会确保有默认值
- 使用 `has_prompt` 标志跟踪是否至少设置了一个

## 配置流程

```
Streamlit UI
  ↓
用户选择提示词配置方式
  ├─ 使用预制模板 → vlm_layout_prompt_template = "modern" (或其他)
  │                  vlm_layout_prompt = ""
  └─ 自定义提示词 → vlm_layout_prompt = "用户输入的内容"
                     vlm_layout_prompt_template = ""
  ↓
配置传递 (第 1269-1283 行)
  ├─ 检查 vlm_layout_prompt 是否有内容
  ├─ 否则检查 vlm_layout_prompt_template 是否有内容
  └─ 都没有 → 设置默认 "modern"
  ↓
build_config_dict (第 100-118 行)
  ├─ 再次检查并设置
  └─ 双重保护：确保至少有一个
  ↓
ConfigParser → config_dict
  ↓
VlmLayoutService 初始化
  ↓
✅ 成功！至少有一个提示词配置
```

## 可用的提示词模板

- `modern`: 现代出版物（默认）
- `chinese_ancient`: 中文古籍（竖排、右到左）
- `gothic_german`: 哥特体/德文古籍
- `archive`: 档案文件（手写/印章）
- `table_form`: 表格/表单密集
- `scientific`: 科技论文（公式/代码/多栏）

## 测试建议

1. **测试默认配置**：
   - 选择 VLM 版面识别
   - 不修改任何提示词设置
   - 验证使用 "modern" 模板

2. **测试预制模板**：
   - 选择"使用预制模板"
   - 选择不同的模板（如 "chinese_ancient"）
   - 验证正确应用

3. **测试自定义提示词**：
   - 选择"自定义提示词"
   - 输入自定义内容
   - 验证使用自定义提示词

4. **测试空输入**：
   - 选择"自定义提示词"
   - 留空或只输入空格
   - 验证回退到默认模板

## 相关文件

- `marker/scripts/streamlit_app.py`: UI 和配置构建
- `marker/services/layout_vlm.py`: VLM 版面识别服务
- `marker/services/__init__.py`: BaseService 和配置验证

## 注意事项

1. **提示词优先级**：
   - 自定义提示词 > 预制模板 > 默认模板

2. **空白处理**：
   - 使用 `.strip()` 确保不会将纯空白字符串视为有效输入

3. **向后兼容**：
   - 如果旧配置没有设置提示词，自动使用 "modern" 模板
   - 不会破坏现有配置

4. **错误处理**：
   - 双重保护确保即使一处失败，另一处也能兜底
