# VLM 模板系统 - 问题修复报告

## 🐛 发现的问题

### 问题 1: API 参数未正确传导

**症状**: 无论如何调整配置（temperature, top_p 等），对同一个样本输出的结果都一样。

**根本原因**:
在 `vlm_direct_async.py` 第180行的条件判断有误：

```python
# 错误的判断
if "vlm_direct_prompt" in config and config["vlm_direct_prompt"] != DEFAULT_PROMPT:
```

当用户在 Streamlit UI 中留空自定义提示词输入框时，`config["vlm_direct_prompt"]` 是空字符串 `""`，这不等于 `DEFAULT_PROMPT`，导致：
1. 进入旧模式分支
2. `self.api_params = {}` - API 参数被设置为空字典
3. 所有 API 参数（temperature, top_p 等）都没有传递给 API

**修复方案**:
```python
# 修复后的判断
if "vlm_direct_prompt" in config and config["vlm_direct_prompt"] and config["vlm_direct_prompt"].strip():
```

只有当明确提供了非空的自定义提示词时才使用旧模式。

### 问题 2: 语法标识不完整

**症状**: 提示词中缺少 Marker 支持的某些语法标识。

**根本原因**:
基础模板中缺少上标和下标的语法说明。

**修复方案**:
在 `marker/prompts/base.py` 的 `_get_base_syntax()` 方法中添加：

```markdown
## Formatting
**Bold** *Italic* `Code`
Subscript: <sub>text</sub>
Superscript: <sup>text</sup>
```

---

## ✅ 已修复的文件

### 1. `marker/converters/vlm_direct_async.py`

**修改位置**: 第180行

**修改前**:
```python
if "vlm_direct_prompt" in config and config["vlm_direct_prompt"] != DEFAULT_PROMPT:
```

**修改后**:
```python
if "vlm_direct_prompt" in config and config["vlm_direct_prompt"] and config["vlm_direct_prompt"].strip():
```

**新增**: 第344-351行添加调试日志
```python
if hasattr(self, 'api_params') and self.api_params:
    payload.update(self.api_params)
    # 调试日志：显示实际使用的 API 参数
    if page_num == 1:  # 只在第一页打印，避免日志过多
        logger.info(f"[VlmDirectAsyncConverter] Using API params: {self.api_params}")
else:
    # 向后兼容：使用旧的 max_tokens
    payload["max_tokens"] = self.max_tokens
    if page_num == 1:
        logger.warning("[VlmDirectAsyncConverter] No API params found, using legacy mode")
```

### 2. `marker/prompts/base.py`

**修改位置**: `_get_base_syntax()` 方法

**新增内容**:
```markdown
Subscript: <sub>text</sub>
Superscript: <sup>text</sup>
```

---

## 🧪 验证方法

### 方法 1: 运行测试脚本

```bash
cd d:\marker_cuda
python test_vlm_params.py
```

测试脚本会验证：
1. ✅ API 参数正确传导
2. ✅ 不同配置产生不同的参数
3. ✅ 空提示词正确使用模板系统
4. ✅ 旧模式向后兼容

### 方法 2: 查看日志

在 Streamlit UI 中转换文档时，查看日志输出：

```
[VlmDirectAsyncConverter] Using template: modern_publication
[VlmDirectAsyncConverter] Applied API preset: high_accuracy
[VlmDirectAsyncConverter] API Type: qwen
[VlmDirectAsyncConverter] API Params: {'temperature': 0.0, 'top_p': 0.1, 'max_tokens': 8192}
[VlmDirectAsyncConverter] Using API params: {'temperature': 0.0, 'top_p': 0.1, 'max_tokens': 8192}
```

如果看到这些日志，说明参数正确传导。

### 方法 3: 对比不同配置的输出

**测试步骤**:
1. 使用 `temperature=0.0` 转换同一个文档，记录输出
2. 使用 `temperature=0.5` 转换同一个文档，记录输出
3. 对比两次输出

**预期结果**:
- `temperature=0.0`: 每次输出完全相同（确定性）
- `temperature=0.5`: 每次输出可能略有不同（随机性）

---

## 📋 Marker 支持的完整语法标识

### 1. 文本格式
```markdown
**粗体**
*斜体*
`代码`
<sub>下标</sub>
<sup>上标</sup>
```

### 2. 标题
```markdown
# 一级标题
## 二级标题
### 三级标题
```

### 3. 列表
```markdown
- 无序列表
  - 嵌套项

1. 有序列表
2. 第二项
```

### 4. 表格
```markdown
| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 数据 | 数据 | 数据 |
```

### 5. 数学公式
```markdown
行内公式: $E = mc^2$

块级公式:
$$
\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
$$
```

### 6. 代码块
````markdown
```python
def hello():
    print("Hello")
```
````

### 7. 脚注
```markdown
正文中的引用[^1]

[^1]: 脚注内容，通常在页面底部
```

### 8. 引用/引文
```markdown
<span id="ref1">引用锚点</span>
```

### 9. 页码锚点
```markdown
{1}  <!-- 页码标记 -->
```

---

## 🎯 使用建议

### 1. 推荐配置（高准确性）

```python
config = {
    "vlm_direct_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "vlm_direct_model": "qwen-vl-max",
    "vlm_direct_api_key": "sk-xxx,sk-yyy,sk-zzz",  # 多个Key
    "vlm_direct_max_concurrent": 9,  # 3个Key × 3
    "vlm_direct_prompt_template": "modern_publication",
    "vlm_direct_api_preset": "high_accuracy",  # temperature=0.0
}
```

### 2. 验证参数生效

转换文档后，检查日志中是否有：
```
[VlmDirectAsyncConverter] Using API params: {'temperature': 0.0, ...}
```

如果没有这行日志，说明参数未生效，可能是：
- 填写了自定义提示词（进入旧模式）
- 配置参数名称错误

### 3. 测试不同 temperature

**测试 1**: temperature=0.0（完全确定）
```python
config["vlm_direct_api_preset"] = "high_accuracy"
```

**测试 2**: temperature=0.5（有随机性）
```python
config["vlm_direct_api_preset"] = "creative"
```

对同一页面多次转换，观察输出差异：
- temperature=0.0: 每次完全相同
- temperature=0.5: 每次略有不同

---

## 🔍 故障排查

### 问题: 参数不生效

**检查清单**:
1. ✅ 确认 Streamlit UI 中"自定义提示词"输入框为空
2. ✅ 查看日志中是否有 "Using API params" 信息
3. ✅ 确认选择了正确的模板和预设
4. ✅ 运行 `test_vlm_params.py` 验证

### 问题: 输出总是相同

**可能原因**:
1. temperature=0.0（这是正常的，确保可复现性）
2. API 参数未传递（查看日志）
3. VLM API 本身的缓存机制

**解决方案**:
- 如果想要随机性，使用 "创意" 预设或自定义 temperature=0.5
- 如果想要确定性，保持 temperature=0.0

### 问题: 脚注识别不准确

**优化方案**:
1. 使用 "现代出版物" 模板（包含详细的脚注识别指导）
2. 确保 temperature=0.0（提高准确性）
3. 检查文档质量（图像清晰度、DPI）

---

## 📊 修复前后对比

### 修复前
```
配置: temperature=0.0
实际传递: {} (空字典)
结果: 使用 API 默认参数，输出不可控
```

### 修复后
```
配置: temperature=0.0
实际传递: {'temperature': 0.0, 'top_p': 0.1, 'max_tokens': 8192}
结果: 严格按照配置执行，输出可控且可复现
```

---

## ✨ 总结

1. **✅ 修复了 API 参数传导问题** - 现在参数会正确传递给 VLM API
2. **✅ 完善了语法标识** - 添加了上标和下标的说明
3. **✅ 添加了调试日志** - 方便验证参数是否生效
4. **✅ 提供了测试脚本** - 可以快速验证修复效果

**现在可以通过调整 temperature, top_p 等参数来控制 VLM 的输出行为了！**
