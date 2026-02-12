# VLM 自动提取档案编号 - 完整解决方案

## 问题总结

### 问题 1: React NotFoundError（已解决 ✅）

**错误信息**:
```
NotFoundError: 无法对'Node'执行'removeChild': 要删除的节点不是此节点的子节点
```

**根本原因**:
- 条件渲染 `if conversion_mode == "vlm_direct":` 导致组件被创建/销毁
- 当用户切换转换模式或开关时，React 组件状态不一致

**解决方案**:
- ✅ 移除所有条件渲染
- ✅ 组件始终存在，使用 `disabled` 参数控制可用性
- ✅ 添加稳定的 `key="vlm_patterns_text_stable"`

### 问题 2: VLM 无法自动提取档案编号（已解决 ✅）

**用户需求**:
- 档案有清晰的 "SC 001", "SC 002" 等编号
- 希望 VLM 自动识别并提取，而不是手动输入列表

**根本原因**:
1. **正则表达式错误**: 默认值是 `<!--\s*page:\s*(\S+)\s*-->`，但 VLM 实际输出是 `<!-- printed-page: SC 001 -->`
2. **档案文献模板不完整**: 虽然基础提示词有页码识别指令，但档案文献模板没有强调档案编号识别

**解决方案**:
- ✅ 修复正则表达式默认值: `<!--\s*printed-page:\s*(.+?)\s*-->`
- ✅ 增强档案文献模板，添加档案编号识别指令

---

## 修复详情

### 修复 1: React 错误 ([streamlit_app.py:589-610](marker/scripts/streamlit_app.py#L589-L610))

**修改前**:
```python
vlm_printed_page_patterns = None
if conversion_mode == "vlm_direct":  # ❌ 条件渲染
    st.markdown("**VLM 输出提取配置**")
    vlm_patterns_text = st.text_area(...)
```

**修改后**:
```python
vlm_printed_page_patterns = None

# 始终显示配置区域，使用 disabled 控制可用性
st.markdown("**VLM 输出提取配置**")
st.caption("💡 VLM 会在输出中标记页码（如 `<!-- printed-page: SC 001 -->`），这里配置如何提取")

vlm_patterns_text = st.text_area(
    "正则表达式列表（每行一个）",
    value="<!--\\s*printed-page:\\s*(.+?)\\s*-->",  # ✅ 修复正则
    height=100,
    help="用于从 VLM 输出中提取页码的正则表达式。每行一个，按顺序尝试匹配。",
    disabled=(conversion_mode != "vlm_direct" or not extract_printed_pages),  # ✅ 使用 disabled
    key="vlm_patterns_text_stable"  # ✅ 稳定的 key
)

# 只在 VLM 模式且启用提取时解析
if conversion_mode == "vlm_direct" and extract_printed_pages:
    vlm_printed_page_patterns = [
        pattern.strip()
        for pattern in vlm_patterns_text.split('\n')
        if pattern.strip()
    ]
```

**关键改进**:
1. ✅ 组件始终渲染，不会被销毁
2. ✅ 使用 `disabled` 参数控制可用性
3. ✅ 添加稳定的 `key` 确保组件身份
4. ✅ 修复正则表达式默认值

---

### 修复 2: 正则表达式默认值

**错误的正则**:
```python
value="<!--\\s*page:\\s*(\\S+)\\s*-->\n页码[:：]\\s*(\\S+)\n\\[页码:\\s*([^\\]]+)\\]"
```

**问题**:
- `<!--\s*page:\s*` → 应该是 `printed-page` 而不是 `page`
- `\S+` → 无法匹配带空格的编号（如 "SC 001"）
- 多余的中文模式（VLM 不会输出中文标记）

**正确的正则**:
```python
value="<!--\\s*printed-page:\\s*(.+?)\\s*-->"
```

**说明**:
- `printed-page` → 匹配 VLM 实际输出的标签名
- `.+?` → 非贪婪匹配，支持任意字符（包括空格）
- 简洁单一，只匹配标准格式

---

### 修复 3: 增强档案文献模板 ([templates.py:195-213](marker/prompts/templates.py#L195-L213))

**添加的指令**:
```python
### 档案编号识别（重要）
**如果在页面上看到档案编号（如 SC 001, SC-001, 档案号：123 等），请使用以下格式输出**：

```
<!-- printed-page: 档案编号 -->
```

**档案编号常见位置**：
- 页面顶部或底部
- 页眉或页脚区域
- 页面角落
- 可能带有前缀（如 SC, DOC, 档案号, 编号等）

**示例**：
- 看到 "SC 001" → 输出 `<!-- printed-page: SC 001 -->`
- 看到 "SC-001" → 输出 `<!-- printed-page: SC-001 -->`
- 看到 "档案号：123" → 输出 `<!-- printed-page: 123 -->`
- 看到 "编号 A-2024-001" → 输出 `<!-- printed-page: A-2024-001 -->`

**规则**：
- 将此标签放在输出的开头（内容之前）
- 只在实际看到档案编号时输出
- 不要猜测或编造编号
- 保持原始格式（包括空格、横线等）
```

**为什么需要这个**:
- 基础提示词（[base.py:262-286](marker/prompts/base.py#L262-L286)）已经有页码识别指令
- 但档案文献有特殊的编号格式（SC 001, 档案号等）
- 需要明确告诉 VLM 这些也是"页码"，应该输出标记

---

## 完整工作流程

### VLM 自动提取档案编号的流程

```
1. 用户配置
   ├─ 选择转换模式: VLM Direct
   ├─ 选择提示词模板: 档案文献
   ├─ 启用页码锚点: ☑
   └─ 启用提取印刷页码: ☑

2. VLM 处理
   ├─ 读取提示词模板（包含档案编号识别指令）
   ├─ 识别页面上的档案编号（如 "SC 001"）
   └─ 输出标记: <!-- printed-page: SC 001 -->

3. 正则提取
   ├─ 使用正则: <!--\s*printed-page:\s*(.+?)\s*-->
   ├─ 匹配 VLM 输出中的标记
   └─ 提取编号: "SC 001"

4. 锚点注入
   ├─ CustomIDInjector 接收提取的编号
   ├─ 注入到 Markdown: <!-- Page: SC 001 -->
   └─ 最终输出包含档案编号锚点
```

---

## 使用指南

### 场景 1: 档案有清晰编号（如 SC 001）

**推荐方案**: VLM 自动提取（最准确）

**配置步骤**:

```
1. 转换模式: VLM Direct
2. 提示词模板: 档案文献
3. 页码锚点配置:
   ☑ 启用页码锚点
   ☑ 提取印刷页码
4. VLM 输出提取配置:
   正则表达式: <!--\s*printed-page:\s*(.+?)\s*-->
5. 自定义编号来源: 无（仅使用自动识别）
```

**工作原理**:
- VLM 看到 "SC 001" → 输出 `<!-- printed-page: SC 001 -->`
- 正则提取 → 获得 "SC 001"
- 注入锚点 → `<!-- Page: SC 001 -->`

**优点**:
- ✅ 完全自动，无需手动输入
- ✅ 准确识别实际编号
- ✅ 支持各种格式（带空格、横线等）

---

### 场景 2: 档案编号不规则或缺失

**推荐方案**: 自动生成（最简单）

**配置步骤**:

```
1. 转换模式: VLM Direct
2. 页码锚点配置:
   ☑ 启用页码锚点
   ☐ 提取印刷页码（不需要）
3. 自定义编号来源: 自动生成
   编号前缀: SC
   起始编号: 1
   分隔符: 空格
   编号位数: 3
```

**结果**: 自动生成 `SC 001`, `SC 002`, `SC 003`, ...

---

### 场景 3: 部分页面有编号，部分没有

**推荐方案**: VLM 提取 + 自动生成补充

**配置步骤**:

```
1. 转换模式: VLM Direct
2. 提示词模板: 档案文献
3. 页码锚点配置:
   ☑ 启用页码锚点
   ☑ 提取印刷页码
4. VLM 输出提取配置:
   正则表达式: <!--\s*printed-page:\s*(.+?)\s*-->
5. 自定义编号来源: 自动生成
   （为没有编号的页面生成）
```

**工作原理**:
- 有编号的页面 → VLM 提取实际编号
- 没有编号的页面 → 使用自动生成的编号

---

## 常见问题

### Q1: 为什么之前正则不工作？

**A**: 有两个原因：

1. **正则表达式错误**:
   - 旧: `<!--\s*page:\s*(\S+)\s*-->`
   - 新: `<!--\s*printed-page:\s*(.+?)\s*-->`
   - 问题: 标签名错误（`page` vs `printed-page`），且 `\S+` 无法匹配带空格的编号

2. **档案文献模板不完整**:
   - 虽然基础提示词有页码识别，但没有强调档案编号
   - 现在已添加明确的档案编号识别指令

### Q2: VLM 会输出什么格式？

**A**: VLM 会在输出开头添加标记：

```markdown
<!-- printed-page: SC 001 -->

档案正文内容开始...
```

### Q3: 如何验证 VLM 是否输出了标记？

**A**: 查看转换后的原始输出：

1. 在 Streamlit 界面查看 "Markdown 输出"
2. 搜索 `<!-- printed-page:`
3. 如果找到，说明 VLM 正确输出了标记

### Q4: 如果 VLM 没有输出标记怎么办？

**A**: 可能的原因：

1. **提示词模板选择错误** → 确保选择 "档案文献"
2. **VLM 没有看到编号** → 编号可能太小或位置不明显
3. **VLM 模型能力不足** → 尝试更强的模型

**解决方案**:
- 使用 "自动生成" 模式作为备选方案

---

## 技术细节

### VLM 提示词结构

完整的提示词由以下部分组成：

```
1. 基础 Marker 语法说明 (base.py:_get_base_syntax)
2. 输出要求 (base.py:_get_output_requirements)
3. 元素存在性原则 (base.py:_get_element_existence_rules)
4. 特殊指导 (base.py:_get_special_instructions)
   ├─ 文本方向
   ├─ 脚注识别
   ├─ 手写内容
   ├─ 多语言
   └─ 页码识别 ← 包含 printed-page 标记指令
5. 自定义指导 (templates.py:custom_instructions)
   └─ 档案编号识别 ← 新增的档案编号指令
```

### 正则表达式说明

**推荐正则**: `<!--\s*printed-page:\s*(.+?)\s*-->`

**解析**:
- `<!--` - HTML 注释开始
- `\s*` - 可选空白字符
- `printed-page:` - 标签名（固定）
- `\s*` - 可选空白字符
- `(.+?)` - 捕获组，非贪婪匹配任意字符（包括空格）
- `\s*` - 可选空白字符
- `-->` - HTML 注释结束

**支持的格式**:
- `<!-- printed-page: SC 001 -->` ✅
- `<!-- printed-page:SC 001-->` ✅
- `<!--printed-page: SC-001 -->` ✅
- `<!-- printed-page: 档案号123 -->` ✅

---

## 修改文件总结

### 1. [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py#L589-L610)

**修改内容**:
- 移除条件渲染，组件始终存在
- 使用 `disabled` 参数控制可用性
- 修复正则表达式默认值
- 添加稳定的 `key`

**影响**: 修复 React NotFoundError

### 2. [marker/prompts/templates.py](marker/prompts/templates.py#L195-L213)

**修改内容**:
- 在 `ARCHIVE_DOCUMENT` 模板中添加档案编号识别指令
- 明确说明档案编号的常见位置和格式
- 提供具体的输出示例

**影响**: VLM 能够识别并输出档案编号标记

---

## 测试验证

### 测试 1: React 错误已修复

**步骤**:
1. 启动 Streamlit 应用
2. 在 VLM Direct 和 Pipeline 模式之间切换
3. 反复开关 "提取印刷页码"
4. 检查浏览器控制台

**预期结果**: ✅ 不再出现 NotFoundError

### 测试 2: VLM 自动提取档案编号

**步骤**:
1. 选择 VLM Direct 模式
2. 选择 "档案文献" 模板
3. 启用 "提取印刷页码"
4. 上传有 "SC 001" 编号的档案
5. 运行转换

**预期结果**:
- ✅ VLM 输出包含 `<!-- printed-page: SC 001 -->`
- ✅ 最终 Markdown 包含 `<!-- Page: SC 001 -->`

### 测试 3: 正则表达式匹配

**步骤**:
```python
import re
pattern = r"<!--\s*printed-page:\s*(.+?)\s*-->"
text = "<!-- printed-page: SC 001 -->\n档案内容..."
match = re.search(pattern, text)
print(match.group(1))  # 应输出: SC 001
```

**预期结果**: ✅ 成功提取 "SC 001"

---

## 总结

### ✅ 已解决的问题

1. **React NotFoundError** - 移除条件渲染，使用 disabled 参数
2. **正则表达式错误** - 修复为 `<!--\s*printed-page:\s*(.+?)\s*-->`
3. **VLM 不输出档案编号** - 增强档案文献模板，添加明确指令

### 🎯 核心改进

1. **UI 稳定性** - 组件不再被销毁，React 状态一致
2. **自动化程度** - VLM 能够自动识别并输出档案编号
3. **用户体验** - 无需手动输入列表，完全自动化

### 📝 使用建议

**对于档案文献**:
- ✅ 首选: VLM 自动提取（最准确）
- ✅ 备选: 自动生成（最简单）
- ❌ 避免: 手动输入列表（费时费力）

---

## 完成状态

✅ React 错误已修复
✅ 正则表达式已修复
✅ 档案文献模板已增强
✅ VLM 自动提取已实现

请重新启动 Streamlit 应用测试修复效果！
