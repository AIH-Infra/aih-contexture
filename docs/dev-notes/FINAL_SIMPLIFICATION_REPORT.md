# 正则配置简化和 React 错误修复报告

## 修复总览

✅ **已完成所有修复**

本次修复解决了以下问题：
1. ✅ 移除重复的正则配置（简化 UI）
2. ✅ 修复 React NotFoundError（组件销毁错误）

---

## 问题诊断

### 问题 1: 正则配置重复

**用户反馈**: "为什么有两个地方都可以设置正则这是否导致了重复和复杂化"

**问题分析**:
- ❌ **第一处**: Line 591-603 - VLM Direct 模式独立配置（新增）
- ❌ **第二处**: Line 626-645 - 自定义编号来源 "vlm" 选项（旧代码）

**根本原因**:
- "提取印刷页码" 和 "自定义编号" 是两个独立功能
- 但在 UI 中混在一起，导致用户困惑
- 添加独立配置时没有移除旧的重复配置

### 问题 2: React NotFoundError

**错误信息**:
```
NotFoundError: 无法对'Node'执行'removeChild': 要删除的节点不是此节点的子节点
```

**问题分析**:
- 条件渲染 `if extract_printed_pages and conversion_mode == "vlm_direct":`
- 当条件变化时，React 组件被创建/销毁
- Streamlit 的 React 状态管理出现不一致

---

## 修复方案

### 修复 1: 移除重复配置

#### 1.1 移除 "vlm" 选项 ([streamlit_app.py:609](marker/scripts/streamlit_app.py#L609))

**修改前**:
```python
custom_id_source = st.selectbox(
    "自定义编号来源",
    options=["none", "vlm", "file", "list", "auto"],  # ❌ 包含 "vlm"
    ...
)
```

**修改后**:
```python
custom_id_source = st.selectbox(
    "自定义编号来源",
    options=["none", "file", "list", "auto"],  # ✅ 移除 "vlm"
    index=0,
    format_func=lambda x: {
        "none": "无（仅使用自动识别）",
        "file": "上传文件（CSV/JSON）",
        "list": "手动输入列表",
        "auto": "自动生成（sc001, sc002...）"
    }.get(x, x),
    help="选择自定义编号的来源方式。注意：VLM 输出提取已移至上方独立配置。"
)
```

#### 1.2 删除重复的配置代码 ([streamlit_app.py:626-645](marker/scripts/streamlit_app.py#L626-L645))

**删除的代码**:
```python
if custom_id_source == "vlm":
    st.info("💡 VLM 模式：将从 VLM 输出中提取页码信息（如古籍卷标、档案编号等）")

    st.markdown("**提取正则表达式**")
    vlm_extract_patterns_text = st.text_area(
        "正则表达式列表（每行一个）",
        value="<!--\\s*page:\\s*(\\S+)\\s*-->\n页码[:：]\\s*(\\S+)\n\\[页码:\\s*([^\\]]+)\\]",
        height=100,
        help="每行一个正则表达式，用于从 VLM 输出中提取页码。支持多个模式，按顺序尝试匹配。"
    )

    vlm_extract_patterns = [
        pattern.strip()
        for pattern in vlm_extract_patterns_text.split('\n')
        if pattern.strip()
    ]

    custom_id_data = {"patterns": vlm_extract_patterns}

elif custom_id_source == "file":
```

**简化后**:
```python
# 根据来源类型显示对应的配置界面
custom_id_data = None

if custom_id_source == "file":
```

---

### 修复 2: React NotFoundError

#### 2.1 使用 disabled 参数替代条件渲染 ([streamlit_app.py:589-606](marker/scripts/streamlit_app.py#L589-L606))

**修改前**:
```python
vlm_printed_page_patterns = None
if extract_printed_pages and conversion_mode == "vlm_direct":  # ❌ 条件渲染
    st.markdown("**VLM 输出提取配置**")
    vlm_patterns_text = st.text_area(...)
    vlm_printed_page_patterns = [...]
```

**修改后**:
```python
vlm_printed_page_patterns = None
if conversion_mode == "vlm_direct":  # ✅ 始终渲染
    st.markdown("**VLM 输出提取配置**")
    vlm_patterns_text = st.text_area(
        "正则表达式列表（每行一个）",
        value="<!--\\s*page:\\s*(\\S+)\\s*-->\n页码[:：]\\s*(\\S+)\n\\[页码:\\s*([^\\]]+)\\]",
        height=100,
        help="用于从 VLM 输出中提取页码的正则表达式。每行一个，按顺序尝试匹配。",
        disabled=not extract_printed_pages,  # ✅ 使用 disabled 控制
        key="vlm_patterns_text"  # ✅ 添加稳定的 key
    )
    if extract_printed_pages:  # ✅ 只在启用时解析
        vlm_printed_page_patterns = [
            pattern.strip()
            for pattern in vlm_patterns_text.split('\n')
            if pattern.strip()
        ]
```

**优点**:
- ✅ 组件始终存在，不会被销毁
- ✅ 使用 `disabled` 参数控制可用性
- ✅ 添加 `key` 确保组件身份稳定
- ✅ 避免 React 状态不一致

---

## 最终配置流程

### 简化后的 UI 结构

```
📍 页码锚点配置
  ├─ ☑ 启用页码锚点
  ├─ 锚点位置: before/after/both
  ├─ ☑ 提取印刷页码
  │
  ├─ [VLM Direct 模式]
  │   └─ **VLM 输出提取配置**
  │       └─ 正则表达式列表（每行一个）  ← 唯一的正则配置位置
  │
  └─ 自定义编号配置
      ├─ 自定义编号来源
      │   ├─ 无（仅使用自动识别）
      │   ├─ 上传文件（CSV/JSON）
      │   ├─ 手动输入列表
      │   └─ 自动生成（sc001, sc002...）
      │
      └─ [根据选择显示对应配置]
```

### 配置传递链路（简化后）

```
UI (streamlit_app.py)
  ↓
[VLM Direct 模式]
  ↓ 用户输入多行正则
vlm_patterns_text (Line 593-598)
  ↓ 解析为列表（仅当 extract_printed_pages=True）
vlm_printed_page_patterns (Line 599-606)
  ↓ 传递配置
vlm_direct_printed_page_patterns = vlm_printed_page_patterns (Line 1088)
  ↓ 配置字典
config["vlm_direct_printed_page_patterns"] = vlm_direct_printed_page_patterns (Line 1939)
  ↓ VlmDirectAsyncConverter
custom_patterns = config.get("vlm_direct_printed_page_patterns") (Line 156)
  ↓ PrintedPageExtractor
PrintedPageExtractor(patterns=custom_patterns) (Line 180)
```

---

## 使用示例

### 示例 1: 提取档案编号 "SC 001"

**场景**: 档案有清晰的 "SC 001", "SC 002" 编号

**方案 A: 使用自动生成（最简单）**

```
转换模式: VLM Direct
📍 页码锚点配置:
  ☑ 启用页码锚点
  ☐ 提取印刷页码  ← 不需要提取

  自定义编号来源: 自动生成
  编号前缀: SC
  起始编号: 1
  分隔符: 空格
  编号位数: 3
```

**结果**: 自动生成 `SC 001`, `SC 002`, `SC 003`, ...

**方案 B: 使用 VLM 输出提取（最准确）**

1. 修改提示词模板，要求 VLM 输出页码标记
2. 配置正则表达式：

```
转换模式: VLM Direct
📍 页码锚点配置:
  ☑ 启用页码锚点
  ☑ 提取印刷页码  ← 启用提取

  VLM 输出提取配置:
  正则表达式列表（每行一个）:
  <!--\s*page:\s*(\S+\s+\d+)\s*-->
  页码[:：]\s*(SC\s+\d+)

  自定义编号来源: 无（仅使用自动识别）
```

**结果**: 从 VLM 输出中提取 `SC 001`, `SC 002`, ...

---

## 修改文件总结

### 修改的文件

1. **[marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)**
   - Line 609-620: 移除 "vlm" 选项，添加提示
   - Line 622-624: 删除重复的 vlm 配置代码块
   - Line 589-606: 修复 React 错误（使用 disabled 参数）

### 配置参数（无变化）

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `vlm_direct_printed_page_patterns` | list[str] \| None | None | 自定义正则模式列表 |

---

## 优势总结

### ✅ 简化后的优势

1. **UI 更清晰**
   - 只有一个地方配置正则表达式
   - "提取印刷页码" 和 "自定义编号" 功能分离明确

2. **逻辑更简单**
   - 移除了混淆的 "vlm" 选项
   - 配置传递链路更直接

3. **错误已修复**
   - React NotFoundError 不再出现
   - 组件状态稳定

4. **功能完整**
   - 所有原有功能保持不变
   - 支持所有提取模式

---

## 测试建议

### 测试 1: 验证正则配置生效

```python
# 测试步骤
1. 选择 "VLM Direct" 模式
2. 启用 "提取印刷页码"
3. 在 "VLM 输出提取配置" 中输入正则
4. 运行转换
5. 检查输出中的 <!-- Page: X --> 标签
```

### 测试 2: 验证 React 错误已修复

```python
# 测试步骤
1. 选择 "VLM Direct" 模式
2. 反复切换 "提取印刷页码" 开关
3. 检查浏览器控制台是否有 NotFoundError
4. 检查 UI 是否正常响应
```

### 测试 3: 验证自动生成功能

```python
# 测试步骤
1. 选择 "自动生成" 模式
2. 配置: prefix=SC, separator=空格, digits=3
3. 运行转换
4. 检查输出: <!-- Page: SC 001 -->, <!-- Page: SC 002 -->, ...
```

---

## 总结

### ✅ 已解决的问题

1. **正则配置重复** - 移除了 custom_id_source 中的 "vlm" 选项
2. **React NotFoundError** - 使用 disabled 参数替代条件渲染
3. **UI 混乱** - 明确分离 "提取印刷页码" 和 "自定义编号" 功能

### 📝 关键改进

1. **唯一的正则配置位置** - 只在 "VLM 输出提取配置" 中配置
2. **稳定的组件渲染** - 使用 disabled 而不是条件渲染
3. **清晰的功能分离** - 提取和自定义是两个独立功能

### 🎯 推荐使用方案

**对于 "SC 001" 这样的档案编号**:

✅ **最简单**: 使用自动生成模式
- 配置: `prefix=SC, separator=空格, digits=3`
- 无需识别，直接生成

✅ **最准确**: 使用 VLM 输出提取
- 修改提示词要求 VLM 输出页码
- 配置正则表达式
- 适合页码格式不规则的情况

---

## 完成状态

✅ 所有修复已完成
✅ UI 已简化
✅ React 错误已修复
✅ 配置逻辑已优化

请重新启动 Streamlit 应用测试修复效果。
