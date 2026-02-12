# VLM 版面识别提示词配置修复（完整版）

## 问题描述

使用 VLM 版面识别后端时，系统报错：
```
AssertionError: In order to use VlmLayoutService, you must set the configuration values `vlm_layout_prompt, `.
```

然后自动回退到 Surya 版面识别。

## 根本原因分析

### 问题 1: 配置传递逻辑不完善

在 `streamlit_app.py` 中，VLM Layout 提示词配置可能出现两个参数都为空字符串的情况：

1. 用户选择"使用预制模板"时，`vlm_layout_prompt` 被设置为空字符串
2. 用户选择"自定义提示词"时，`vlm_layout_prompt_template` 被设置为空字符串
3. 如果用户没有与 UI 交互，两者都可能为空

在配置传递过程中：
```python
# 原代码（有问题）
if vlm_layout_prompt:  # 空字符串是 falsy，跳过
    vlm_layout_config["vlm_layout_prompt"] = vlm_layout_prompt
elif vlm_layout_prompt_template:  # 如果也是空字符串，也跳过
    vlm_layout_config["vlm_layout_prompt_template"] = vlm_layout_prompt_template
# 结果：两个都没有设置！
```

### 问题 2: 类属性默认值为 None

在 `marker/services/layout_vlm.py` 中，VlmLayoutService 类定义：

```python
# 原代码（有问题）
vlm_layout_prompt: Annotated[
    str,
    "版面识别提示词（直接指定，优先级最高）"
] = None  # ← 这个 None 导致 verify_config_keys 失败！
```

**关键问题**：
- `verify_config_keys` 在 `BaseService.__init__` 中被调用
- 它检查所有 `Annotated` 类型的属性是否为 `None`
- 即使我们在配置中设置了 `vlm_layout_prompt_template`，`vlm_layout_prompt` 属性仍然是 `None`
- 验证在配置处理逻辑之前就失败了

## 完整解决方案

### 修复 1: 在配置传递时添加默认值

**位置**: `marker/scripts/streamlit_app.py` 第 1284-1290 行

```python
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

### 修复 2: 在 build_config_dict 中添加保护

**位置**: `marker/scripts/streamlit_app.py` 第 106-117 行

```python
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

### 修复 3: 修改类属性默认值（关键修复）

**位置**: `marker/services/layout_vlm.py` 第 56-91 行

**修改前**：
```python
vlm_layout_base_url: Annotated[str, "..."] = None
vlm_layout_model: Annotated[str, "..."] = None
vlm_layout_api_key: Annotated[str, "..."] = None
vlm_layout_prompt: Annotated[str, "..."] = None
```

**修改后**：
```python
vlm_layout_base_url: Annotated[str, "..."] = ""
vlm_layout_model: Annotated[str, "..."] = ""
vlm_layout_api_key: Annotated[str, "..."] = ""
vlm_layout_prompt: Annotated[str, "..."] = ""
```

**为什么这样修复有效**：

1. **通过 verify_config_keys 检查**：
   - 空字符串 `""` 不是 `None`
   - `verify_config_keys` 只检查 `value is None`
   - 因此检查通过

2. **保持原有逻辑不变**：
   - `__init__` 中的逻辑：`if config.get("vlm_layout_prompt")`
   - 空字符串是 falsy，所以会跳过
   - 代码会正确地使用 `vlm_layout_prompt_template`

3. **向后兼容**：
   - 不影响现有的配置处理逻辑
   - 所有的 `or` 链式回退仍然正常工作

## 配置流程（修复后）

```
Streamlit UI
  ↓
用户选择提示词配置方式
  ├─ 使用预制模板 → vlm_layout_prompt_template = "modern" (或其他)
  │                  vlm_layout_prompt = ""
  └─ 自定义提示词 → vlm_layout_prompt = "用户输入的内容"
                     vlm_layout_prompt_template = ""
  ↓
配置传递 (第 1284-1290 行)
  ├─ 检查 vlm_layout_prompt 是否有内容
  ├─ 否则检查 vlm_layout_prompt_template 是否有内容
  └─ 都没有 → 设置默认 "modern"
  ↓
build_config_dict (第 106-117 行)
  ├─ 再次检查并设置
  └─ 双重保护：确保至少有一个
  ↓
ConfigParser → config_dict
  ↓
VlmLayoutService.__init__
  ├─ 类属性默认值: vlm_layout_prompt = ""（不是 None）
  ├─ verify_config_keys 检查通过 ✅
  └─ 处理配置：
      ├─ if config.get("vlm_layout_prompt"): → False（空字符串）
      └─ else: 使用 vlm_layout_prompt_template
  ↓
✅ 成功！VLM Layout 服务正常工作
```

## 技术细节

### verify_config_keys 的工作原理

```python
def verify_config_keys(obj):
    annotations = inspect.get_annotations(obj.__class__)

    none_vals = ""
    for attr_name, annotation in annotations.items():
        if isinstance(annotation, type(Annotated[str, ""])):
            value = getattr(obj, attr_name)
            if value is None:  # ← 只检查 None，不检查空字符串
                none_vals += f"{attr_name}, "

    if none_vals:
        raise AssertionError(f"In order to use {obj.__class__.__name__}, you must set the configuration values {none_vals}.")
```

**关键点**：
- 只检查 `value is None`
- 不检查空字符串、空列表等其他 falsy 值
- 因此将默认值从 `None` 改为 `""` 可以通过检查

### 为什么空字符串不影响现有逻辑

在 `VlmLayoutService.__init__` 中：

```python
# API 配置回退链
self.base_url = (
    config.get("vlm_layout_base_url")  # 如果是 ""，返回 ""（falsy）
    or config.get("openai_base_url")   # 尝试这个
    or "http://127.0.0.1:1234/v1"      # 最终默认值
)

# 提示词配置
if config.get("vlm_layout_prompt"):  # 空字符串是 falsy
    self.prompt = str(config["vlm_layout_prompt"])
else:
    # 使用模板（这是我们想要的行为）
    template_name = config.get("vlm_layout_prompt_template", "modern")
    self.prompt = get_layout_prompt(template_name)
```

**工作原理**：
- `config.get("vlm_layout_prompt")` 返回空字符串 `""`
- 空字符串在布尔上下文中是 `False`
- `or` 运算符会继续尝试下一个选项
- `if` 语句会跳到 `else` 分支

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
   - 验证使用 "modern" 模板 ✅

2. **测试预制模板**：
   - 选择"使用预制模板"
   - 选择不同的模板（如 "chinese_ancient"）
   - 验证正确应用 ✅

3. **测试自定义提示词**：
   - 选择"自定义提示词"
   - 输入自定义内容
   - 验证使用自定义提示词 ✅

4. **测试空输入**：
   - 选择"自定义提示词"
   - 留空或只输入空格
   - 验证回退到默认模板 ✅

## 相关文件

- `marker/scripts/streamlit_app.py`: UI 和配置构建
- `marker/services/layout_vlm.py`: VLM 版面识别服务（已修复）
- `marker/services/__init__.py`: BaseService 和配置验证
- `marker/util.py`: verify_config_keys 函数

## 总结

这个问题需要三层修复：

1. **UI 层**：确保配置传递时至少有一个参数被设置
2. **配置层**：在 build_config_dict 中添加双重保护
3. **服务层**：修改类属性默认值从 `None` 到 `""`（关键修复）

第三层修复是最关键的，因为它解决了 `verify_config_keys` 在配置处理之前就失败的根本问题。通过将默认值改为空字符串，我们既通过了验证检查，又保持了原有的回退逻辑不变。
