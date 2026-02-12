# 🔴 紧急修复：VLM 不输出页码标记

## 问题现状

✅ 配置已正确传递：`vlm_direct_prompt_template: archive_document`
✅ 档案文献模板包含页码识别指令
✅ 正则表达式正确
❌ **VLM 输出中没有 `<!-- printed-page:` 标记**

## 可能的原因

### 原因 1: Streamlit 缓存问题

Streamlit 可能缓存了旧的配置或转换器实例。

**解决方案**：
1. 完全关闭 Streamlit 应用（Ctrl+C）
2. 清除浏览器缓存（Ctrl+Shift+Delete）
3. 重新启动应用

### 原因 2: 自定义提示词覆盖

即使输入框为空，Streamlit 可能仍然传递了空字符串。

**已修复**：Line 1979-1981 已添加 `.strip()` 检查

### 原因 3: VLM 模型忽略指令

某些 VLM 模型可能不遵循提示词中的格式指令。

**测试方法**：
查看终端日志，搜索：
```
[VlmDirectAsyncConverter] Using template: archive_document
```

如果看到这行，说明模板已加载。

---

## 立即行动方案

### 方案 A: 强制重启（推荐）

```bash
# 1. 停止 Streamlit
Ctrl+C

# 2. 清除 Python 缓存
cd d:\marker_cuda
del /s /q __pycache__
del /s /q *.pyc

# 3. 重新启动
python -m marker.scripts.streamlit_app
```

### 方案 B: 添加调试日志

在转换前添加日志输出，确认配置。
