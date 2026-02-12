# 问题诊断和解决方案

## 问题 1：VLM Direct 脚注格式变化

### 根本原因
**这不是 bug，是正确的 Markdown 语法！**

VLM Direct 使用的 `modern_publication` 模板（`marker/prompts/templates.py:216-257`）中，脚注示例使用的是 **Markdown 标准语法**：

```markdown
正文内容[^1]继续正文。

----

[^1]: 这是脚注内容，位于页面底部，字号较小。
```

### 对比

| 模式 | 脚注格式 | 说明 |
|------|---------|------|
| VLM Direct | `[^1]` | Markdown 标准语法（正确） |
| Pipeline | `<sup>1)</sup>` | HTML 格式（旧格式） |

### 为什么会这样？

1. **VLM Direct**：使用 VLM 模型直接转换，提示词要求输出标准 Markdown
2. **Pipeline**：使用 FootnoteProcessor 处理，输出 HTML 格式

### 解决方案

#### 方案 1：统一使用 Markdown 格式（推荐）

修改 Pipeline 的 FootnoteProcessor，输出 Markdown 格式 `[^1]` 而不是 HTML 格式。

#### 方案 2：修改 VLM 提示词

如果您更喜欢 HTML 格式，可以修改 `marker/prompts/templates.py:243-247`：

```python
**脚注示例**:
正文内容<sup>1)</sup>继续正文。

----

<sup>1)</sup> 这是脚注内容，位于页面底部，字号较小。
```

#### 方案 3：保持现状

`[^1]` 是标准 Markdown 语法，大多数 Markdown 渲染器都支持。建议保持现状。

## 问题 2：Pipeline 没有印刷页码

### 根本原因

**配置传递失败！** 即使 UI 勾选了"提取印刷页码"，`use_printed_page_number` 还是 False。

### 可能的原因

1. **UI 状态不同步**：Streamlit 的状态管理问题
2. **配置作用域问题**：`extract_printed_pages` 变量在错误的作用域
3. **配置被覆盖**：后续代码覆盖了配置

### 诊断步骤

#### 步骤 1：确认调试信息

刷新 Streamlit 页面后，应该在 Pipeline 配置区域看到：
```
🔍 调试信息：extract_printed_pages = True, printed_page_enabled = True
```

**如果看不到这个信息，说明代码没有执行到这里。**

#### 步骤 2：检查配置传递

在 `marker/scripts/streamlit_app.py:2022` 添加日志：

```python
if printed_page_enabled:
    st.success(f"✅ 启用印刷页码提取：{printed_page_enabled}")
    config_params.update({
        "use_printed_page_number": True,
        ...
    })
else:
    st.error(f"❌ 未启用印刷页码提取：{printed_page_enabled}")
```

#### 步骤 3：检查 PageNumberProcessor 初始化

在 `marker/processors/page_number.py:113` 添加日志：

```python
def __init__(self, config: Optional[dict] = None):
    super().__init__(config)

    logger.info(f"[PageNumberProcessor.__init__] Received config: {config}")
    logger.info(f"[PageNumberProcessor.__init__] page_numbering_enabled: {self.page_numbering_enabled}")
    logger.info(f"[PageNumberProcessor.__init__] use_printed_page_number: {self.use_printed_page_number}")
```

### 快速修复方案

#### 方案 1：强制启用（临时）

在 `marker/processors/page_number.py:75` 修改默认值：

```python
use_printed_page_number: Annotated[
    bool,
    "使用印刷页码而非机器页码"
] = True  # 改为 True
```

#### 方案 2：检查配置传递路径

确认配置传递的完整路径：
1. UI 勾选 → `extract_printed_pages = True`
2. 映射 → `printed_page_enabled = extract_printed_pages`
3. 更新配置 → `config_params["use_printed_page_number"] = True`
4. 传递给转换器 → `PdfConverter(config=config_params)`
5. 传递给处理器 → `PageNumberProcessor(config)`

**检查每一步是否正确执行。**

### 最可能的问题

根据日志 `use_printed_page_number=False`，最可能的问题是：

1. **`printed_page_enabled` 是 False**
   - 检查 `extract_printed_pages` 的值
   - 检查是否进入了 `if printed_page_enabled:` 块

2. **配置没有传递给 PageNumberProcessor**
   - 检查 `config_params` 是否包含 `use_printed_page_number`
   - 检查 PageNumberProcessor 是否正确读取配置

3. **配置被后续代码覆盖**
   - 检查是否有其他地方设置了 `use_printed_page_number=False`

## 下一步行动

### 对于 VLM Direct 脚注问题：
✅ **无需修复**，`[^1]` 是正确的 Markdown 语法。

### 对于 Pipeline 印刷页码问题：

1. **立即检查**：刷新页面，查看调试信息输出
2. **添加日志**：在关键位置添加日志，追踪配置传递
3. **临时修复**：修改默认值为 True，验证其他逻辑是否正常

**请先查看调试信息输出，然后告诉我 `extract_printed_pages` 和 `printed_page_enabled` 的值！**
