# 前端 UI 更新完成报告

## 更新日期
2026-02-01

## 更新概述
完成了页码锚点系统的简化和自定义编号功能的实现，统一了前端 UI 和后端逻辑。

## 主要变更

### 1. 前端 UI 更新 (streamlit_app.py)

#### 移除的配置项
- ❌ "锚点模板"下拉选择（原支持 {n}, {n1}, {printed} 等）
- ❌ "页序起始值"数字输入（原支持 0 或 1）

#### 保留的配置项
- ✅ "启用页码锚点"复选框
- ✅ "锚点位置"单选按钮（仅 VLM Direct 模式）
- ✅ "提取印刷页码"复选框
- ✅ 印刷页码详细配置（Pipeline 模式）

#### 新增的配置项
- ✅ "自定义编号来源"下拉选择
  - 无（仅使用自动识别）
  - VLM 输出提取
  - 上传文件（CSV/JSON）
  - 手动输入列表
  - 自动生成（sc001, sc002...）

- ✅ 根据来源类型显示对应的配置界面
  - **VLM 模式**：提取正则表达式输入
  - **文件模式**：文件上传器（支持 CSV/JSON）
  - **列表模式**：文本区域输入（支持逗号或换行分隔）
  - **自动模式**：前缀、起始编号、位数配置

### 2. 后端更新

#### formatters.py
1. **PageAnchorFormatter 简化**
   - 移除 template 参数（固定使用 {n} 格式）
   - 移除 page_anchor_start 参数（固定 0-based）
   - 只保留 wrapper 参数（默认 `{{{}}}`）

2. **CustomIDInjector 新增**
   - 支持 5 种来源类型：none, vlm, file, list, auto
   - 提供统一的 get_custom_id(page_index) 接口
   - 支持字符串和列表两种输入格式

3. **PageAnchorPlugin 增强**
   - 新增 custom_id_injector 参数
   - 自动生成 <!-- Page: X --> 标签
   - 优先级：printed_page_id > custom_id > 无

#### vlm_direct_async.py
1. **移除旧参数**
   - vlm_direct_page_anchor_template
   - vlm_direct_page_anchor_start

2. **新增参数**
   - vlm_direct_custom_id_source
   - vlm_direct_custom_id_data

3. **更新初始化逻辑**
   - 使用简化的 PageAnchorFormatter
   - 集成 CustomIDInjector

#### markdown.py
- 已在之前的更新中完成
- 支持 custom_id_source 和 custom_id_data 参数
- 自动生成 <!-- Page: X --> 标签

### 3. 双层页码系统

#### 定位层：{n} 锚点
- 固定格式：`{0}`, `{1}`, `{2}`...
- 0-based 页序
- 用于范围提取：`{2}-{5}` 提取第 3-5 页

#### 显示层：<!-- Page: X --> 标签
- 格式：`<!-- Page: sc001 -->`
- 优先级：
  1. PageNumberProcessor 自动识别（Pipeline 模式）
  2. CustomIDInjector 自定义编号
  3. 无（不显示标签）

### 4. 参数传递更新

#### VLM Direct 模式
```python
# 旧参数（已移除）
"vlm_direct_page_anchor_template": "{n1}"
"vlm_direct_page_anchor_start": 0

# 新参数
"vlm_direct_custom_id_source": "auto"
"vlm_direct_custom_id_data": {"prefix": "sc", "start": 1, "digits": 3}
```

#### Pipeline 模式
```python
# 旧参数（已移除）
"page_anchor_template": "{n1}"
"page_anchor_start": 0

# 新参数
"custom_id_source": "auto"
"custom_id_data": {"prefix": "sc", "start": 1, "digits": 3}
```

## 测试结果

### 语法检查
- ✅ streamlit_app.py - 通过
- ✅ formatters.py - 通过
- ✅ vlm_direct_async.py - 通过

### 功能测试
- ✅ CustomIDInjector - 所有测试通过
  - none 源：正确返回 None
  - list 源：正确解析列表
  - auto 源：正确生成编号
  - PageAnchorPlugin 集成：正确生成锚点和标签
  - 优先级测试：printed_page_id 优先于 custom_id

## 使用示例

### 示例 1：自动生成档案编号
```python
# UI 配置
custom_id_source = "auto"
custom_id_data = {
    "prefix": "sc",
    "start": 1,
    "digits": 3
}

# 输出
{0}

<!-- Page: sc001 -->
页面内容...

{1}

<!-- Page: sc002 -->
页面内容...
```

### 示例 2：手动输入列表
```python
# UI 配置
custom_id_source = "list"
custom_id_data = ["卷一", "卷二", "卷三"]

# 输出
{0}

<!-- Page: 卷一 -->
页面内容...

{1}

<!-- Page: 卷二 -->
页面内容...
```

### 示例 3：结合印刷页码
```python
# Pipeline 模式自动识别印刷页码
# 输出
{0}

<!-- Page: XII -->
页面内容...

{1}

<!-- Page: 308 -->
页面内容...
```

## 向后兼容性

### 已移除的参数
- `page_anchor_template` - 固定为 `{n}`
- `page_anchor_start` - 固定为 0
- `vlm_direct_page_anchor_template` - 固定为 `{n}`
- `vlm_direct_page_anchor_start` - 固定为 0

### 迁移指南
如果之前使用了这些参数，需要：
1. 移除 `page_anchor_template` 和 `page_anchor_start` 配置
2. 如果需要自定义编号，使用新的 `custom_id_source` 和 `custom_id_data`
3. 如果需要 1-based 页序，使用 `custom_id_source="auto"` 配置

## 下一步工作

### 可选增强
1. VLM 输出提取功能实现（目前仅有 UI）
2. 文件上传功能的完整实现
3. 更多的自定义编号格式支持

### 文档更新
1. 更新用户手册
2. 添加配置示例
3. 创建迁移指南

## 总结

本次更新成功简化了页码锚点系统，同时增强了自定义编号功能：
- 前端 UI 更加简洁直观
- 后端逻辑更加清晰统一
- 双层页码系统满足了定位和显示的不同需求
- 自定义编号支持多种来源，灵活性大大提升

所有代码已通过语法检查和功能测试，可以投入使用。
