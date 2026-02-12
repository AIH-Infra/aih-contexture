# 简化页码锚点 - 实施总结

## 核心修改（8个文件）

### 1. marker/formatters.py
- 简化 PageAnchorFormatter: 只用 {n} 格式
- 修改 PageAnchorPlugin: 添加额外锚点参数
- 修改 PrintedPageExtractor: 改为 <!-- Page: X --> 且不移除
- 新增 CustomIDInjector: 注入自定义编号

### 2. marker/converters/vlm_direct_async.py
- 集成 CustomIDInjector
- 修改页码锚点处理流程
- 添加额外锚点支持

### 3. marker/renderers/markdown.py
- 简化 PageAnchorFormatter 初始化
- 添加额外锚点到文档末尾

### 4. marker/prompts/base.py
- 修改提示词: <!-- Page: X --> 格式
- 支持多个页码标记

### 5. marker/scripts/streamlit_app.py
- 简化页码锚点配置
- 添加自定义编号配置（5种来源）

## 全局生效保证

VLM Direct: PageAnchorPlugin + CustomIDInjector
Pipeline: MarkdownRenderer + Document metadata

## 工作量: 10-13小时

详见 PAGE_ANCHOR_IMPLEMENTATION.md
