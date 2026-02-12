# 正则表达式不生效问题修复报告

## 🔴 问题描述

用户反馈两个问题：
1. **正则表达式不生效** - 档案编号 "SC013" 没有被提取
2. **侧边栏 React 错误** - NotFoundError: 无法对"Node"执行"removeChild"

---

## 🔍 问题诊断

### 问题 1: 正则配置逻辑错误

**错误代码** (streamlit_app.py:1094-1096):
```python
vlm_direct_printed_page_patterns = None
if custom_id_source == "vlm" and custom_id_data and "patterns" in custom_id_data:
    vlm_direct_printed_page_patterns = custom_id_data["patterns"]
```

**问题分析**:
- ❌ 只有当 `custom_id_source == "vlm"` 时才传递正则
- ❌ "自定义编号来源" 和 "提取印刷页码" 是两个独立功能
- ❌ 它们被错误地混在一起了

**结果**: 正则配置无法传递到 `PrintedPageExtractor`

### 问题 2: VLM 没有输出页码标记

**根本原因**:
- VLM 的提示词中没有要求输出页码标记
- VLM 输出的是原始文本，不包含 `<!-- page: SC013 -->` 格式
- 正则表达式无法匹配原始文本中的页码

---

## ✅ 修复方案

### 修复 1: 分离正则配置

**新增独立配置区域** (streamlit_app.py:589-607):

```python
# 🆕 VLM Direct 模式的正则配置
vlm_printed_page_patterns = None
if extract_printed_pages and conversion_mode == "vlm_direct":
    st.markdown("**VLM 输出提取配置**")
    vlm_patterns_text = st.text_area(
        "正则表达式列表（每行一个）",
        value="<!--\\s*page:\\s*(\\S+)\\s*-->\n页码[:：]\\s*(\\S+)\n\\[页码:\\s*([^\\]]+)\\]",
        height=100,
        help="用于从 VLM 输出中提取页码的正则表达式"
    )
    vlm_printed_page_patterns = [
        pattern.strip()
        for pattern in vlm_patterns_text.split('\n')
        if pattern.strip()
    ]
```

**修复配置传递** (streamlit_app.py:1094-1096):

```python
# 🆕 传递正则模式（独立于自定义编号）
vlm_direct_printed_page_patterns = vlm_printed_page_patterns if 'vlm_printed_page_patterns' in locals() else None
```

### 修复 2: React 错误

**原因**: Streamlit 组件状态不一致

**解决方法**:
1. 刷新页面
2. 清除浏览器缓存
3. 重启 Streamlit 应用

---

## 📖 使用指南

### 方案 A: 使用自动生成（推荐）

对于规则的档案编号 "SC013", "SC014"...：

```
自定义编号来源: 自动生成
编号前缀: SC
起始编号: 13
分隔符: 无
编号位数: 3
```

**结果**: SC013, SC014, SC015, ...

### 方案 B: 使用 VLM 输出提取

**步骤 1**: 修改提示词

在 VLM Direct 提示词中添加：
```
If you see a document ID (like "SC013"), output it at the beginning:
<!-- page: SC013 -->
```

**步骤 2**: 配置正则

在 "VLM 输出提取配置" 中输入：
```
<!--\s*page:\s*(\S+)\s*-->
```

**步骤 3**: 启用提取

勾选 "提取印刷页码"

---

## 🎯 关键改进

1. ✅ **分离配置** - "提取印刷页码" 和 "自定义编号" 现在是独立的
2. ✅ **独立正则配置** - VLM Direct 模式有自己的正则配置区域
3. ✅ **正确传递** - 正则模式正确传递到 `PrintedPageExtractor`

---

## 🧪 测试验证

### 测试 1: 验证正则传递

```python
# 配置
config = {
    "vlm_direct_extract_printed_pages": True,
    "vlm_direct_printed_page_patterns": [
        r"<!--\s*page:\s*(\S+)\s*-->",
    ]
}

# 验证
converter = VlmDirectAsyncConverter(config)
assert converter.printed_page_extractor.patterns == config["vlm_direct_printed_page_patterns"]
```

### 测试 2: 验证自动生成

```python
# 配置
config = {
    "prefix": "SC",
    "start": 13,
    "digits": 3,
    "separator": ""
}

# 验证
injector = CustomIDInjector(source_type="auto", source_data=config)
assert injector.get_custom_id(0) == "SC013"
assert injector.get_custom_id(1) == "SC014"
```

---

## 📝 总结

**修复的文件**:
- [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)

**修复的问题**:
1. ✅ 正则配置逻辑错误
2. ✅ 配置传递失败
3. ⚠️ React 错误（需要刷新页面）

**推荐方案**:
- 对于规则编号：使用**自动生成**
- 对于不规则编号：使用**VLM 输出提取**（需修改提示词）
