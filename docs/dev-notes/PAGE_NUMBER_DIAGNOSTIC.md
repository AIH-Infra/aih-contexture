# Surya + 禁用 OCR 无印刷页码 - 诊断指南

## 问题

**配置**: Surya + 禁用 OCR
**现象**: 没有 `<!-- Page: X -->` 标签

## 诊断步骤

### 步骤 1: 检查是否勾选"提取印刷页码"

**位置**: UI 中的"页码锚点配置"部分

**问题**: Pipeline 模式下，"提取印刷页码"默认是**未勾选**的！

**代码**: `marker/scripts/streamlit_app.py:512`
```python
extract_printed_pages = st.checkbox(
    "提取印刷页码",
    value=True if conversion_mode == "vlm_direct" else False,  # ← Pipeline 默认 False!
    help="自动识别文档中的印刷页码（如古籍卷标、罗马数字等）"
)
```

**解决方案**: ✅ **手动勾选"提取印刷页码"复选框**

### 步骤 2: 检查是否有文本源

**Surya + 禁用 OCR 需要 PDF 文本层！**

#### 检查 PDF 是否有文本层

**方法 1**: 在 PDF 阅读器中尝试选择文本
- ✅ 可以选择 → 有文本层
- ❌ 不能选择 → 扫描件，无文本层

**方法 2**: 使用命令检查
```bash
# 使用 pdftotext 检查
pdftotext your.pdf - | head -n 20
```

#### 如果没有文本层

**选项 1**: 启用 OCR
```
OCR 后端: Surya OCR（或其他）
```

**选项 2**: 使用自定义编号
```
自定义编号来源: 自动生成
```

### 步骤 3: 检查配置传递

**验证配置是否正确传递到 PageNumberProcessor**

#### 添加调试日志

在 `marker/processors/page_number.py:141` 添加日志：

```python
def __call__(self, document: Document):
    """处理文档，提取页码信息。"""
    # 添加调试日志
    logger.info(f"[PageNumberProcessor] page_numbering_enabled={self.page_numbering_enabled}")
    logger.info(f"[PageNumberProcessor] use_printed_page_number={self.use_printed_page_number}")

    if not self.page_numbering_enabled:
        logger.info("[PageNumberProcessor] Skipped: page_numbering_enabled=False")
        return
```

#### 运行并检查日志

查看控制台输出，应该看到：
```
[PageNumberProcessor] page_numbering_enabled=True
[PageNumberProcessor] use_printed_page_number=True
[PageNumberProcessor] Processing 10 pages
```

如果看到 `False`，说明配置没有传递。

### 步骤 4: 检查是否找到页码

**PageNumberProcessor 可能运行了，但没找到页码**

#### 原因

1. **页码不在搜索区域**
   - 默认搜索：页脚（底部 17%）和页眉（顶部 15%）
   - 如果页码在其他位置，需要调整

2. **页码格式不匹配**
   - 默认格式：`auto`（自动检测）
   - 支持：阿拉伯数字、罗马数字、中文数字

3. **页码被识别为其他块类型**
   - Surya 可能将页码识别为普通文本
   - PageNumberProcessor 优先搜索 PageHeader/PageFooter 块

#### 调整搜索区域

在 UI 中展开"印刷页码详细配置"：

```
页码搜索区域: [页脚, 页眉]  ← 可以调整顺序
页眉起始位置: 0.0
页眉结束位置: 0.15  ← 可以增大（如 0.2）
页脚起始位置: 0.83  ← 可以减小（如 0.75）
```

#### 调整页码格式

```
页码格式: 自动检测（推荐）
```

或指定具体格式：
- 阿拉伯数字 (1, 2, 3...)
- 罗马数字 (I, II, III...)
- 中文数字 (一, 二, 三...)

## 完整检查清单

### UI 配置检查

- [ ] 转换模式：Pipeline
- [ ] 布局后端：Surya
- [ ] OCR 后端：禁用
- [ ] **✅ 勾选"启用页码锚点"**
- [ ] **✅ 勾选"提取印刷页码"** ← 关键！
- [ ] 自定义编号来源：无（或其他）

### PDF 文件检查

- [ ] PDF 有文本层（可以选择文本）
- [ ] 页码位于页眉或页脚
- [ ] 页码格式为常见格式（阿拉伯/罗马/中文数字）

### 代码检查

- [ ] PageNumberProcessor 已导入到 pdf.py
- [ ] PageNumberProcessor 在 default_processors 列表中
- [ ] 配置正确传递（检查日志）

## 测试用例

### 测试 1: 简单 PDF

**文件**: 任何有页码的学术论文 PDF

**配置**:
```
- Pipeline 模式
- Surya 布局
- 禁用 OCR
- ✅ 勾选"提取印刷页码"
```

**预期输出**:
```markdown
{0}

<!-- Page: 1 -->
内容...
```

### 测试 2: 扫描件 PDF

**文件**: 扫描的 PDF（无文本层）

**配置**:
```
- Pipeline 模式
- Surya 布局
- Surya OCR  ← 必须启用
- ✅ 勾选"提取印刷页码"
```

**预期输出**:
```markdown
{0}

<!-- Page: 1 -->
内容...
```

### 测试 3: 无页码 PDF

**文件**: 没有页码的 PDF

**配置**:
```
- Pipeline 模式
- Surya 布局
- 禁用 OCR
- ✅ 勾选"提取印刷页码"
- 自定义编号来源: 自动生成
```

**预期输出**:
```markdown
{0}

<!-- Page: page001 -->
内容...
```

## 常见问题

### Q1: 勾选了"提取印刷页码"，但还是没有

**检查**:
1. PDF 是否有文本层？
2. 页码是否在搜索区域内？
3. 查看日志，PageNumberProcessor 是否运行？

### Q2: 日志显示 "page_numbering_enabled=False"

**原因**: 配置没有传递

**解决**:
1. 确保勾选"提取印刷页码"
2. 重启 Streamlit 应用
3. 检查 streamlit_app.py 的配置传递代码

### Q3: 日志显示 "Processing X pages" 但没有找到页码

**原因**: 页码不在搜索区域或格式不匹配

**解决**:
1. 调整搜索区域（扩大页眉/页脚范围）
2. 尝试不同的页码格式
3. 检查 PDF 的页码位置

### Q4: 扫描件 PDF 无法提取页码

**原因**: 禁用 OCR 后没有文本

**解决**:
1. 启用 OCR（Surya OCR 或其他）
2. 或使用自定义编号

## 快速修复

### 最常见的问题

**忘记勾选"提取印刷页码"！**

**解决方案**:
1. 打开 Streamlit UI
2. 找到"页码锚点配置"部分
3. ✅ 勾选"提取印刷页码"
4. 重新转换

### 第二常见的问题

**PDF 是扫描件，没有文本层**

**解决方案**:
1. 启用 OCR（不要禁用）
2. 或使用自定义编号

## 验证修复

### 验证 PageNumberProcessor 已添加

```bash
cd d:\marker_cuda
python -c "from marker.converters.pdf import PdfConverter; print('PageNumberProcessor' in str(PdfConverter.default_processors))"
```

**预期输出**: `True`

### 验证配置传递

在转换时查看控制台日志，应该看到：
```
[PageNumberProcessor] page_numbering_enabled=True
[PageNumberProcessor] use_printed_page_number=True
[PageNumberProcessor] Processing X pages
```

## 总结

### 最可能的原因

1. **未勾选"提取印刷页码"** ← 最常见！
2. **PDF 无文本层 + 禁用 OCR** ← 第二常见！
3. **页码不在搜索区域**
4. **配置未传递**

### 解决方案

1. ✅ **勾选"提取印刷页码"复选框**
2. ✅ **确保有文本源（PDF 文本层或 OCR）**
3. ✅ **调整搜索区域（如果需要）**
4. ✅ **检查日志验证配置**

**按照这个诊断指南，应该可以解决问题！**
