# 解决方案：Surya + 禁用 OCR 模式下提取印刷页码

## 问题根源

在 [marker/scripts/streamlit_app.py:512](marker/scripts/streamlit_app.py#L512)：

```python
extract_printed_pages = st.checkbox(
    "提取印刷页码",
    value=True if conversion_mode == "vlm_direct" else False,  # ← 这里！
    help="自动识别文档中的印刷页码（如古籍卷标、罗马数字等）"
)
```

**默认值规则：**
- VLM Direct 模式：默认 **True**（勾选）
- Pipeline 模式（包括 Surya）：默认 **False**（不勾选）

## 解决方案

### 方案 1：手动勾选（推荐）

在 Streamlit UI 中：
1. 选择 Pipeline 模式
2. 选择 Surya 布局检测
3. **手动勾选"提取印刷页码"** ← 关键步骤！
4. 运行转换

### 方案 2：修改默认值

如果您希望 Pipeline 模式也默认勾选，修改代码：

```python
# 修改前
value=True if conversion_mode == "vlm_direct" else False,

# 修改后
value=True,  # 所有模式都默认勾选
```

## 验证方法

运行转换后，查看日志：

### ✅ 正确配置（已勾选）
```
[PageNumberProcessor] ✅ Enabled, processing 10 pages
[PageNumberProcessor] Config: use_printed_page_number=True
[PageNumberProcessor] Page 0: Found printed page number '1'
```

### ❌ 错误配置（未勾选）
```
[PageNumberProcessor] ✅ Enabled, processing 10 pages
[PageNumberProcessor] Config: use_printed_page_number=False
```
→ 即使 PageNumberProcessor 运行了，`use_printed_page_number=False` 意味着不会提取印刷页码

## 为什么会这样设计？

Pipeline 模式默认不勾选的原因可能是：
1. 印刷页码提取需要额外的处理时间
2. 不是所有文档都有印刷页码
3. VLM Direct 模式更适合处理复杂文档（如古籍），所以默认启用

## 总结

**Surya + 禁用 OCR 模式下没有印刷页码的原因：**
1. ✅ PageNumberProcessor 已正确集成
2. ✅ 您的 PDF 有文本层，可以提取文本
3. ❌ **"提取印刷页码"选项默认未勾选**

**解决方法：手动勾选"提取印刷页码"选项即可。**
