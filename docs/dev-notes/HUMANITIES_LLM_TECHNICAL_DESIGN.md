# LLM辅助系统技术设计方案 - 人文社科文献处理

## 一、当前架构深度分析

### 1.1 现有LLM处理架构

Marker当前的LLM辅助系统采用**基于块(Block)的处理模式**:

**核心组件:**
- `BaseLLMProcessor`: 基础处理器,提供图像提取、块标准化等通用功能
- `BaseLLMComplexBlockProcessor`: 复杂块处理器,用于处理需要复杂逻辑的块
- `BaseLLMSimpleBlockProcessor`: 简单块处理器,用于单个块的快速处理

**处理粒度分析:**

1. **单块处理模式** (Block-level):
   - 示例: `LLMTableProcessor`, `LLMEquationProcessor`
   - LLM一次只看到一个块(如一个表格、一个公式)
   - 优点: 精细控制,错误隔离
   - 缺点: 缺乏上下文,无法处理跨块关系

2. **页面级处理模式** (Page-level):
   - 示例: `LLMPageCorrectionProcessor`
   - LLM一次看到整个页面的所有块
   - 优点: 有完整上下文,可以调整块顺序和类型
   - 缺点: Token消耗大,处理速度慢

**多线程实现机制:**
```python
# 当前使用ThreadPoolExecutor实现并发
with ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
    for future in as_completed([
        executor.submit(self.process_rewriting, document, page, block)
        for page in document.pages
        for block in page.contained_blocks(document, self.block_types)
    ]):
        future.result()
```

**关键特性:**
- 并发度可配置(`max_concurrency`,默认3)
- 支持进度条显示(`tqdm`)
- 块级别的独立处理,互不干扰
- 支持OpenAI协议(通过`BaseService`抽象层)
- 异常处理机制,单个块失败不影响整体

### 1.2 数据流架构

```
PDF文档 → Provider → Document(pages) → Processors → Renderers → Markdown
                         ↓
                    PageGroup(blocks)
                         ↓
                    Block(spans/lines/chars)
```

**Document结构:**
- `Document`: 包含多个`PageGroup`
- `PageGroup`: 包含多个`Block`,维护`structure`列表(块的顺序)
- `Block`: 基础内容单元,包含`polygon`(位置)、`text_lines`(文本)等

**处理器执行顺序:**
处理器按照配置的顺序依次执行,每个处理器可以修改Document的内容。

## 二、人文社科文献处理需求分析

### 2.1 核心挑战

1. **多语种混排**: 古汉语、繁体字、少数民族文字、外文引用
2. **复杂版式**: 竖排、双栏、批注、夹注、眉批
3. **特殊内容**: 古籍刻本、手写档案、印章、图注
4. **页码系统**: PDF页码(锚点) vs 印刷页码(启发式识别)
5. **噪音过滤**: 水印、污渍、装订线、页边装饰
6. **排版优化**: 段落合并、标点修正、格式统一

### 2.2 技术要求

1. **灵活的后端组合**: Layout(YOLO/VLM) + OCR(Calamari/VLM)可自由替换
2. **模块化设计**: 每个功能独立开关
3. **高效并行**: 页面级并行处理,最终按页码锚点组装
4. **协议兼容**: 支持OpenAI协议,兼容深度学习和VLM方案

## 三、LLM辅助模块设计

### 3.1 模块架构

```
LLM辅助系统
├── 预处理模块 (Pre-processing)
│   ├── 页码识别模块 (LLMPageNumberDetector)
│   ├── 噪音检测模块 (LLMNoiseDetector)
│   └── 版式分析模块 (LLMLayoutAnalyzer)
├── 内容优化模块 (Content Optimization)
│   ├── 文本校正模块 (LLMTextCorrector)
│   ├── 排版优化模块 (LLMLayoutOptimizer)
│   └── 多语种处理模块 (LLMMultilingualProcessor)
├── 结构识别模块 (Structure Recognition)
│   ├── 章节识别模块 (LLMSectionDetector)
│   ├── 批注识别模块 (LLMAnnotationDetector)
│   └── 引用识别模块 (LLMCitationDetector)
└── 后处理模块 (Post-processing)
    ├── 段落合并模块 (LLMParagraphMerger)
    ├── 页面拼接模块 (LLMPageAssembler)
    └── 质量检查模块 (LLMQualityChecker)
```


### 3.2 详细模块设计

#### 3.2.1 页码识别模块 (LLMPageNumberDetector)

**功能**: 启发式识别印刷页码,建立PDF页码与印刷页码的映射关系

**处理粒度**: 页面级 (Page-level)

**继承**: `BaseLLMComplexBlockProcessor`

**实现策略**:
```python
class LLMPageNumberDetector(BaseLLMComplexBlockProcessor):
    block_types = (BlockTypes.PageHeader, BlockTypes.PageFooter, BlockTypes.Text)
    use_llm = False  # 默认关闭
    
    page_number_prompt = """你是页码识别专家。请分析这个页面,识别印刷页码。

页面图像: [图像]
当前识别的块: {blocks_json}

请识别:
1. 印刷页码的位置和内容(可能在页眉、页脚或边缘)
2. 页码格式(阿拉伯数字、罗马数字、中文数字等)
3. 页码类型(正文页码、前言页码、附录页码等)

输出JSON格式:
{
  "has_page_number": true/false,
  "page_number": "识别的页码",
  "page_number_type": "arabic/roman/chinese",
  "page_number_location": "header/footer/margin",
  "confidence": 0.0-1.0
}
"""
    
    def process_rewriting(self, document: Document, page: PageGroup, block: Block):
        # 提取页面图像
        image = page.get_image(document, highres=False)
        
        # 获取可能包含页码的块
        candidate_blocks = self.get_page_number_candidates(document, page)
        blocks_json = [self.normalize_block_json(b, document, page) for b in candidate_blocks]
        
        # 调用LLM识别
        prompt = self.page_number_prompt.replace("{blocks_json}", json.dumps(blocks_json))
        response = self.llm_service(prompt, image, page, PageNumberSchema)
        
        # 保存页码信息到page metadata
        if response and response.get("has_page_number"):
            page.update_metadata(
                printed_page_number=response["page_number"],
                page_number_type=response["page_number_type"],
                page_number_confidence=response["confidence"]
            )
```

**配置参数**:
- `use_llm`: bool (默认False)
- `page_number_detection_enabled`: bool (默认False)
- `page_number_confidence_threshold`: float (默认0.7)

---

#### 3.2.2 噪音检测模块 (LLMNoiseDetector)

**功能**: 识别并标记水印、污渍、装订线、页边装饰等噪音内容

**处理粒度**: 块级 (Block-level)

**继承**: `BaseLLMComplexBlockProcessor`

**实现策略**:
```python
class LLMNoiseDetector(BaseLLMComplexBlockProcessor):
    block_types = (BlockTypes.Text, BlockTypes.Picture, BlockTypes.Figure)
    use_llm = False
    
    noise_detection_prompt = """你是文档噪音识别专家。请判断这个内容块是否为噪音。

块图像: [图像]
块内容: {block_html}
块类型: {block_type}

噪音类型包括:
- 水印(watermark)
- 污渍(stain)
- 装订线(binding)
- 页边装饰(decoration)
- 扫描伪影(artifact)

输出JSON:
{
  "is_noise": true/false,
  "noise_type": "watermark/stain/binding/decoration/artifact/none",
  "confidence": 0.0-1.0,
  "reason": "判断理由"
}
"""
    
    def process_rewriting(self, document: Document, page: PageGroup, block: Block):
        # 提取块图像
        image = self.extract_image(document, block)
        
        # 调用LLM判断
        prompt = self.noise_detection_prompt.replace("{block_html}", block.render(document))
        prompt = prompt.replace("{block_type}", str(block.id.block_type))
        response = self.llm_service(prompt, image, block, NoiseSchema)
        
        # 标记噪音块
        if response and response.get("is_noise") and response.get("confidence") > 0.7:
            block.update_metadata(
                is_noise=True,
                noise_type=response["noise_type"]
            )
            # 可选: 直接从structure中移除
            if self.remove_noise_blocks:
                page.structure.remove(block.id)
```

**配置参数**:
- `use_llm`: bool (默认False)
- `noise_detection_enabled`: bool (默认False)
- `noise_confidence_threshold`: float (默认0.7)
- `remove_noise_blocks`: bool (默认False,仅标记不删除)

---

#### 3.2.3 版式分析模块 (LLMLayoutAnalyzer)

**功能**: 分析复杂版式(竖排、双栏、批注等),优化阅读顺序

**处理粒度**: 页面级 (Page-level)

**继承**: `BaseLLMComplexBlockProcessor`

**实现策略**:
```python
class LLMLayoutAnalyzer(BaseLLMComplexBlockProcessor):
    block_types = tuple()  # 处理所有块
    use_llm = False
    
    layout_analysis_prompt = """你是古籍和历史文献版式分析专家。请分析这个页面的版式结构。

页面图像: [图像]
当前块顺序: {blocks_json}

文档类型: {document_type}
可能的版式:
- 现代横排(modern_horizontal)
- 古籍竖排(ancient_vertical)
- 双栏(two_column)
- 三栏(three_column)
- 批注版式(annotation_layout): 正文+眉批/夹注
- 档案版式(archive_layout): 不规则布局

请分析:
1. 版式类型
2. 阅读顺序是否正确
3. 是否有批注、夹注等特殊内容
4. 块的分类是否准确

输出JSON:
{
  "layout_type": "版式类型",
  "reading_order_correct": true/false,
  "corrected_block_order": ["block_id1", "block_id2", ...],  # 如果需要调整
  "special_regions": [
    {"type": "annotation", "block_ids": [...], "relation": "批注正文块ID"}
  ],
  "confidence": 0.0-1.0
}
"""
    
    def process_rewriting(self, document: Document, page: PageGroup, block: Block):
        # 页面级处理,block参数在这里不使用
        pass
    
    def rewrite_blocks(self, document: Document):
        # 重写为页面级处理
        for page in document.pages:
            self.process_page_layout(document, page)
    
    def process_page_layout(self, document: Document, page: PageGroup):
        image = page.get_image(document, highres=False)
        blocks = page.structure_blocks(document)
        blocks_json = [self.normalize_block_json(b, document, page) for b in blocks]
        
        prompt = self.layout_analysis_prompt.replace("{blocks_json}", json.dumps(blocks_json))
        prompt = prompt.replace("{document_type}", self.document_type)
        response = self.llm_service(prompt, image, page, LayoutSchema)
        
        # 应用版式调整
        if response and not response.get("reading_order_correct"):
            self.apply_layout_corrections(document, page, response)
```

**配置参数**:
- `use_llm`: bool (默认False)
- `layout_analysis_enabled`: bool (默认False)
- `document_type`: str (默认"auto", 可选: "modern_horizontal", "ancient_vertical", "archive")
- `layout_confidence_threshold`: float (默认0.7)


---

#### 3.2.4 文本校正模块 (LLMTextCorrector)

**功能**: 修正OCR错误,优化标点,处理多语种文本

**处理粒度**: 块级或页面级(可配置)

**继承**: BaseLLMComplexBlockProcessor

**配置参数**:
- use_llm: bool (默认False)
- text_correction_enabled: bool (默认False)
- processing_level: str (默认block, 可选page)
- correction_threshold: float (默认0.7)

---

#### 3.2.5 段落合并模块 (LLMParagraphMerger)

**功能**: 智能合并跨页段落,处理断行问题

**处理粒度**: 跨页面级 (Cross-page)

**配置参数**:
- use_llm: bool (默认False)
- paragraph_merge_enabled: bool (默认False)
- merge_confidence_threshold: float (默认0.7)

---

## 四、多线程并行策略设计

### 4.1 当前多线程机制分析

**现状:**
- 使用ThreadPoolExecutor实现并发
- 默认并发度为3(max_concurrency=3)
- 每个块/页面独立处理,互不干扰
- 使用as_completed获取结果,不保证顺序

**问题:**
- 并发度较低,对于大文档处理速度慢
- 没有按页码锚点分组的机制
- 结果组装是顺序的,没有利用并行优势

### 4.2 新的并行策略

#### 4.2.1 三级并行架构

Level 1: 文档级并行 (Document-level Parallelism)
  - 将文档按页码锚点分组(如每10页一组)
  - 每组独立处理,互不干扰
  - 最后按页码顺序组装
  
Level 2: 页面级并行 (Page-level Parallelism)
  - 在每组内,页面并行处理
  - 使用ThreadPoolExecutor或ProcessPoolExecutor
  - 并发度可配置(默认10-20)
  
Level 3: 块级并行 (Block-level Parallelism)
  - 在每个页面内,块并行处理
  - 仅对独立的块(如表格、图片)并行
  - 文本块保持顺序处理

