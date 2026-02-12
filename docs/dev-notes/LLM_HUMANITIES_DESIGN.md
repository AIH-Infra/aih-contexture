# 人文社科文献 LLM 辅助系统设计方案

## 🎯 设计目标

针对多语种、多形式、多字体的人文社科文献（古早出版物、古籍、档案、手写等），设计一套模块化、可配置的 LLM 辅助系统，在 OCR 和版面识别完成后进行智能优化。

## 📐 系统架构

### 整体流程

```
PDF 输入
  ↓
版面识别 (Layout Detection) - 可选后端: Surya/VLM/YOLO
  ↓
OCR 文本提取 - 可选后端: Surya/VLM/Calamari
  ↓
文档结构构建 (Document Building)
  ↓
【LLM 辅助处理层】← 本设计的核心
  ├─ 模块 1: 版面优化 (Layout Optimization)
  ├─ 模块 2: 页码识别 (Page Number Recognition)
  ├─ 模块 3: 噪音过滤 (Noise Filtering)
  ├─ 模块 4: 文本修正 (Text Correction)
  ├─ 模块 5: 结构增强 (Structure Enhancement)
  └─ 模块 6: 元数据提取 (Metadata Extraction)
  ↓
Markdown 渲染
  ↓
最终输出
```

## 🧩 功能模块设计

### 模块 1: 版面优化 (Layout Optimization)

**目标**: 修正版面识别错误，优化复杂布局

**处理对象**:
- 多栏布局（双栏、三栏、不规则分栏）
- 混合布局（文字+图片+表格）
- 古籍竖排布局
- 档案文件的不规则布局

**处理粒度**: 页级别（Page-level）

**工作方式**:
1. 提取整页图像
2. 提取当前版面识别结果（块的位置、类型、顺序）
3. LLM 分析图像和结构，判断：
   - 阅读顺序是否正确
   - 块的分类是否准确
   - 是否有遗漏的内容
4. 输出优化后的块顺序和类型

**提示词模板**:
```
你是文档版面分析专家。请分析这个页面的布局结构。

当前识别结果:
{current_layout_json}

请检查:
1. 阅读顺序是否符合文档类型（现代横排/古籍竖排/多栏等）
2. 块的分类是否准确（正文/标题/脚注/页码/噪音）
3. 是否有遗漏或错误分割的内容

输出优化后的布局结构（JSON格式）。
```

**配置参数**:
- `layout_optimization_enabled`: bool (默认 False)
- `layout_optimization_confidence_threshold`: float (0.7)
- `layout_optimization_document_type`: str ("modern" | "ancient_chinese" | "archive" | "auto")

