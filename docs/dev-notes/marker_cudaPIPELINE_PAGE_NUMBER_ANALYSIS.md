# Pipeline 模式双层页码实现方案分析

## 现状分析

### ✅ Pipeline 模式已有页码识别功能

**发现**：Pipeline 模式已经有完整的页码识别系统！

**关键组件**：
1. `PageNumberProcessor` (marker/processors/page_number.py)
   - 从页眉/页脚提取页码
   - 支持多种格式：阿拉伯数字、罗马数字、中文数字
   - 支持自定义正则表达式

2. UI 配置 (marker/scripts/streamlit_app.py)
   - `use_printed_page_number`: 使用印刷页码
   - `page_numbering_enabled`: 启用页码提取
   - `printed_page_zones`: 页码搜索区域（header/footer）
   - `page_number_format`: 页码格式（arabic/roman/chinese）
   - `llm_printed_page_correction_enabled`: LLM 辅助修正

### ⚠️ 问题：识别到的页码未转换为 `<!-- Page: X -->` 格式

**当前流程**：
```
PDF → Surya Layout → OCR → PageNumberProcessor → Document
                                    ↓
                            识别印刷页码
                                    ↓
                            存储在 Document 中？
                                    ↓
                            MarkdownRenderer
                                    ↓
                            只生成 {n} 锚点
```

**缺失环节**：
- PageNumberProcessor 识别到的页码存储在哪里？
- MarkdownRenderer 如何访问这些页码？
- 如何将页码转换为 `<!-- Page: X -->` 格式？

---

## 解决方案对比

### 方案 1：使用现有的 PageNumberProcessor（推荐）

**原理**：
利用 Pipeline 模式已有的页码识别功能，在 MarkdownRenderer 中读取识别到的页码，并转换为 `<!-- Page: X -->` 格式。

**实现步骤**：

1. **检查 PageNumberProcessor 如何存储页码**
   ```python
   # 在 PageNumberProcessor 中
   def __call__(self, document: Document) -> Document:
       for page in document.pages:
           # 提取页码
           page_number = self._extract_page_number(page)
           # 存储到 page.metadata 或 page 属性中
           page.printed_page_number = page_number
   ```

2. **在 MarkdownRenderer 中读取页码**
   ```python
   def convert_div(self, el, text, parent_tags):
       if is_page:
           page_id = int(el["data-page-id"])
           
           # 读取印刷页码
           printed_page = el.get("data-printed-page", None)
           
           # 生成 {n} 锚点
           anchor = f"{{{page_id}}}"
           
           # 添加印刷页码标记
           page_tag = ""
           if printed_page:
               page_tag = f"<!-- Page: {printed_page} -->"
           
           return f"\n\n{anchor}\n{page_tag}{self.page_separator}\n\n{text}"
   ```

3. **确保 Document 渲染时传递页码信息**
   ```python
   # 在 Document.render() 或 Page.render() 中
   def render(self, config):
       html = f'<div class="page" data-page-id="{self.page_id}"'
       if hasattr(self, 'printed_page_number') and self.printed_page_number:
           html += f' data-printed-page="{self.printed_page_number}"'
       html += '>'
       # ... 渲染内容
       return html
   ```

**优点**：
- ✅ 利用现有功能，无需重复开发
- ✅ 支持多种页码格式（阿拉伯、罗马、中文）
- ✅ 可以使用 LLM 辅助修正
- ✅ 不需要额外的 API 调用

**缺点**：
- ⚠️ 需要检查 PageNumberProcessor 的实现细节
- ⚠️ 需要确保页码信息正确传递到 MarkdownRenderer

**工作量**：2-3 小时

---

### 方案 2：LLM 辅助后处理

**原理**：
在 Pipeline 模式完成后，使用 LLM 识别页面中的印刷页码或档案编号。

**实现步骤**：

1. **在 MarkdownRenderer 后添加 LLM 处理**
   ```python
   def post_process_with_llm(markdown: str, images: list) -> str:
       # 对每一页调用 LLM
       for page_index, image in enumerate(images):
           prompt = "识别这一页的页码或档案编号"
           page_number = llm_call(image, prompt)
           
           # 在对应的 {n} 锚点后注入 <!-- Page: X -->
           markdown = inject_page_tag(markdown, page_index, page_number)
       
       return markdown
   ```

**优点**：
- ✅ 可以识别复杂的页码格式
- ✅ 可以识别档案编号
- ✅ 灵活性高

**缺点**：
- ❌ 需要额外的 LLM 调用（成本和时间）
- ❌ 可能不准确
- ❌ 增加系统复杂度
- ❌ 与现有的 PageNumberProcessor 功能重复

**工作量**：4-5 小时

---

### 方案 3：微调 Surya 添加页码识别模块

**原理**：
在 Surya Layout Detection 或 OCR 阶段，训练模型识别页码区域。

**实现步骤**：

1. **收集页码数据集**
2. **训练页码识别模型**
3. **集成到 Surya**
4. **在 Pipeline 中使用**

**优点**：
- ✅ 不需要额外的 LLM 调用
- ✅ 性能更好

**缺点**：
- ❌ 需要大量训练数据
- ❌ 需要修改 Surya 代码
- ❌ 维护成本高
- ❌ 与现有的 PageNumberProcessor 功能重复

**工作量**：数周到数月

---

### 方案 4：在 MarkdownRenderer 中注入自定义编号

**原理**：
不依赖自动识别，使用用户提供的自定义编号（CSV/JSON/自动生成/手动输入）。

**实现步骤**：

1. **在 MarkdownRenderer 中集成 CustomIDInjector**
   ```python
   class MarkdownRenderer(BaseModel):
       custom_id_source: str = "none"
       custom_id_data: Any = None
       
       def __call__(self, document: Document) -> MarkdownOutput:
           markdown = self.md_cls.convert(full_html)
           
           # 注入自定义编号
           if self.custom_id_source != "none":
               injector = CustomIDInjector(self.custom_id_source, self.custom_id_data)
               markdown = self._inject_custom_ids(markdown, injector)
           
           return MarkdownOutput(markdown=markdown, ...)
   ```

**优点**：
- ✅ 不需要修改 Surya
- ✅ 不需要 LLM 后处理
- ✅ 用户可以完全控制页码
- ✅ 实现简单

**缺点**：
- ❌ 无法自动识别印刷页码
- ❌ 需要用户手动提供编号

**工作量**：2-3 小时

---

## 推荐方案

### 🎯 混合方案：方案 1 + 方案 4

**原理**：
1. 优先使用 PageNumberProcessor 自动识别印刷页码
2. 如果识别失败或用户需要自定义，使用 CustomIDInjector

**实现**：

```python
class MarkdownRenderer(BaseModel):
    # 自定义编号配置
    custom_id_source: str = "none"
    custom_id_data: Any = None
    
    def convert_div(self, el, text, parent_tags):
        if is_page:
            page_id = int(el["data-page-id"])
            
            # 1. 尝试从 PageNumberProcessor 获取印刷页码
            printed_page = el.get("data-printed-page", None)
            
            # 2. 如果没有，尝试从 CustomIDInjector 获取
            if not printed_page and self.custom_id_source != "none":
                printed_page = self.custom_ids.get(page_id, None)
            
            # 生成锚点
            anchor = f"{{{page_id}}}"
            
            # 添加页码标记
            page_tag = ""
            if printed_page:
                page_tag = f"<!-- Page: {printed_page} -->"
            
            return f"\n\n{anchor}\n{page_tag}{self.page_separator}\n\n{text}"
    
    def __call__(self, document: Document) -> MarkdownOutput:
        # 初始化 CustomIDInjector
        if self.custom_id_source != "none":
            injector = CustomIDInjector(self.custom_id_source, self.custom_id_data)
            self.custom_ids = injector.custom_ids
        else:
            self.custom_ids = {}
        
        # 渲染
        markdown = self.md_cls.convert(full_html)
        
        # 添加额外锚点
        if self.paginate_output:
            page_count = len(document.pages)
            markdown += f"\n\n{{{page_count}}}"
        
        return MarkdownOutput(markdown=markdown, ...)
```

**优点**：
- ✅ 自动识别 + 手动补充
- ✅ 灵活性最高
- ✅ 利用现有功能
- ✅ 支持所有场景

**缺点**：
- ⚠️ 实现稍复杂

**工作量**：3-4 小时

---

## 实施步骤

### 阶段 1：验证 PageNumberProcessor（1 小时）
1. 检查 PageNumberProcessor 如何存储页码
2. 检查 Document/Page 是否有 printed_page_number 属性
3. 检查 HTML 渲染时是否传递 data-printed-page

### 阶段 2：修改 MarkdownRenderer（2 小时）
1. 在 convert_div() 中读取 data-printed-page
2. 生成 `<!-- Page: X -->` 标记
3. 添加额外锚点支持

### 阶段 3：集成 CustomIDInjector（1 小时）
1. 添加 custom_id_source 和 custom_id_data 参数
2. 在 __call__() 中初始化 CustomIDInjector
3. 在 convert_div() 中使用自定义编号

### 阶段 4：更新 UI 配置（1 小时）
1. 为 Pipeline 模式添加自定义编号配置
2. 传递参数到 MarkdownRenderer

### 阶段 5：测试（1 小时）
1. 测试 PageNumberProcessor 自动识别
2. 测试 CustomIDInjector 手动补充
3. 测试混合模式

**总工作量**：6 小时

---

## 结论

**推荐方案**：混合方案（PageNumberProcessor + CustomIDInjector）

**理由**：
1. ✅ 利用现有的 PageNumberProcessor 功能
2. ✅ 支持自动识别和手动补充
3. ✅ 不需要额外的 LLM 调用
4. ✅ 不需要修改 Surya
5. ✅ 实现简单，工作量小

**下一步**：
1. 验证 PageNumberProcessor 的实现细节
2. 修改 MarkdownRenderer 支持双层页码
3. 集成 CustomIDInjector
4. 测试所有场景
