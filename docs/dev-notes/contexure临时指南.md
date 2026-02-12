命名同步确认
项目名称：Contexture / 经纬

维度	中文	英文	技术对应
核心隐喻	经纬（织布）	Contexture	文档结构化
词源关联	经线+纬线	Context+Texture	Latin textus → text
技术映射	坐标定位	PageAnchor	版面识别
定位	经天纬地	Infrastructure	基础设施
Slogan: Weaving Data from History. (经纬万卷，结构古今)

这个命名的精妙之处：

词源闭环：Latin textus（编织）→ English text →经纬（织布）→ Contexture
技术隐喻：经纬线交织 = 文档结构化重组
学术气质：符合人文学科的定位
国际化：中英文都有深意，便于学术传播
当前工作目录已经是 d:\datalab\Contexture，项目重命名已完成。

请问接下来需要我做什么？例如：

继续探查Contexture 项目的具体实现
帮助完善项目文档
分析特定模块的代码
其他任务
从UI的代码 streamlit.py出发 探查Contexture 项目的具体实现 包括它的所有逻辑分支所有配置以及所有设置和的目的等等先形成一个基本的技术报告作为我们后续的依据
好的，我将从 UI 代码出发，系统性地探查 Contexture 项目的完整实现。让我先定位 streamlit.py 文件。

Globpattern: "**/streamlit*.py"
Found 1 file
Read d:\datalab\Contexture\marker\scripts\streamlit_app.py
文件很大（173.7KB），我将分段读取和分析。让我先读取前500行了解整体结构。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py
好的，我已经读取了前500行。让我先输出第一部分分析，然后继续读取。

📊 Contexture 技术报告 - 第一部分：UI 入口与配置架构
1.1 项目标识

页面标题:兰台·PageAnchor：面向人文学科与档案馆的文献级PDF结构化引擎
基于: Marker的 PDF 文档结构化提取
1.2 三大转换模式（核心分支）
从 build_config_dict() 函数可以看到三大模式：

模式	转换器类	特点
传统模式 (traditional)	PdfConverter	Pipeline流水线
OCR Direct模式	OcrDirectAsyncConverter	Chandra专用VLM
VLM Direct 模式	VlmDirectConverter	纯VLM端到端
1.3 后端解耦配置
版面识别后端 (layout_backend):

surya - 默认Surya
vlm - VLM版面识别
yolo - DocLayout-YOLO
none - 禁用
OCR后端 (ocr_backend):

surya - 默认Surya
vlm - VLM OCR
calamari - Calamari历史文献OCR
none - 禁用
让我继续读取更多内容，了解UI配置面板的完整结构。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py (lines 501-1000)
好的，我已经读取了500-1000行。让我输出第二部分分析。

📊 Contexture 技术报告 - 第二部分：UI 配置面板详解
2.1 三大转换模式的UI 配置
模式	UI 标识	默认选中	特点描述
traditional	🔧 传统模式	否	Marker Pipeline 完整流水线
vlm_direct	🚀 VLM Direct	否	纯 VLM 异步并发，提速 5-10 倍
ocr_direct	📚 OCR Direct	是	专业 OCR（Chandra），支持手写/表格/公式
2.2 OCR Direct 模式配置项
API 配置:

参数	默认值	说明
ocr_endpoint	http://localhost:1234/v1	OpenAI 兼容 API
ocr_model	chandra-ocr@f16	Chandra 模型
ocr_output_format	markdown,json,html	多格式输出
图像预处理:

参数	默认值	说明
ocr_resize_max	2048	最大图像尺寸
ocr_image_format	PNG	图像格式
ocr_image_quality	60	JPEG 质量
并发控制（创新设计）:

模式	说明	适用场景
serial_file	逐个文件，内部并行多页	多页 PDF
batch_single_page	多个单页文件同时处理	扫描图片
后处理配置:
-噪音过滤（支持正则）

脚注修复
页眉页脚过滤
2.3 页码锚点配置（PageAnchor）
这是 Contexture 的核心创新之一：


启用页码锚点 → 在每页开头添加`{n}` 锚点
提取印刷页码 → 生成 `<!-- Page: X -->` 标签
传统模式：通过版面识别检测页眉/页脚区域
VLM/OCR Direct 模式：通过正则表达式从 Markdown 提取

让我继续读取更多内容，了解传统模式的配置。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py (lines 1001-1500)
好的，我已经读取了1000-1500行。让我输出第三部分分析。

##📊 Contexture 技术报告 - 第三部分：高级配置详解

3.1 页码正则预设系统（创新设计）
预设	名称	适用场景
default	阿拉伯/罗马数字	通用印刷页码
sc_format	SC 档案编号	档案馆文献（SC001~SC999）
chinese	中文页码	古籍、线装书
custom	自定义正则	特殊格式
SC 档案编号的OCR 容错设计：


# S可能被识别为 5, $
# C 可能被识别为 0, O, (
r"\b([Ss5$][Cc0O(][Uu]?\s*[0Oo]?\d{3})(?!\d)"
3.2 自定义编号来源（4种模式）
模式	说明	用途
none	使用正则自动识别	默认
file	上传 CSV/JSON 映射	批量导入
list	手动输入列表	少量页面
auto	自动生成（SC001...）	连续编号
3.3 边码识别配置（人文学科专用）
MarginalAnnotation（边码/页边注）：

版心叶码、Stephanus/Bekker 编码
行号、书耳、眉批
位置阈值：左/右/上/下边栏
InlineAnnotation（行内小字注）：

双行小字、夹注、割注、括号注
字体比例阈值：0.75（相对主文本）
3.4 VLM Direct 模式配置
支持的 API 提供商：

提供商	类型	默认模型
openai_compatible	通用	qwen-vl-max
gemini	原生	gemini-2.5-flash
anthropic	原生	claude-sonnet-4
多Key 负载均衡：


检测到 N 个 API Key → 建议并发数: N × 3
让我继续读取更多内容，了解传统模式的配置。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py (lines 1501-2000)
好的，我已经读取了1500-2000行。让我输出第四部分分析。

##📊 Contexture 技术报告 - 第四部分：提示词模板系统

4.1 VLM Direct提示词模板（9种预设）
模板	名称	适用场景
universal	通用模板（推荐）	默认
modern_publication	现代出版物	书籍、期刊
ancient_chinese	中文古籍	竖排、右到左
archive_document	档案文献	手写/印章
gothic_german	哥特体德文	德文古籍
manuscript	手稿	手写文档
academic_paper	学术论文	公式/引用
mixed_content	混合内容	复杂文档
custom	自定义	手动配置
4.2 API 参数预设
预设	Temperature	说明
high_accuracy	0.0	减少幻觉，提高可复现性
balanced	0.3	平衡准确性和多样性
creative	0.7	更多创意输出
custom	自定义	手动配置
4.3 自定义模板参数
参数	选项	说明
text_direction	horizontal/vertical/mixed	文本方向
handwriting_mode	none/mixed/pure	手写识别模式
language_mode	monolingual/multilingual	语言模式
document_era	ancient/modern/contemporary	文档年代
primary_language	17种语言预设	主要语言
4.4 传统模式处理器配置
文本处理器：

Markdown 噪音清理（3级：basic/medium/aggressive）
行合并
引用块检测
代码块检测
结构处理器：

章节标题检测
列表检测
脚注检测
参考文献检测
表格处理器：

表格处理
让我继续读取更多内容，了解 OCR 后端配置和 LLM 增强配置。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py (lines 2001-2500)
好的，我已经读取了2000-2500行。让我输出第五部分分析。

##📊 Contexture 技术报告 - 第五部分：OCR 后端与 LLM 增强

5.1 OCR 后端配置（4种）
后端	名称	适用场景	特点
none	禁用 OCR	原生数字PDF	使用 PDF 内嵌文本
surya	Surya OCR	通用文档	内置深度学习，多语言
calamari	Calamari	历史文献	gt4histocr 模型
vlm	VLM OCR	复杂布局	视觉语言模型
5.2 Calamari OCR 高级配置（历史文献专用）
参数	默认值	说明
calamari_batch_size	100	每次发送的最大图片数
calamari_timeout	120	超时时间（秒）
calamari_footnote_y_frac	0.83	页底区域阈值（脚注后置）
calamari_sequential_mode	False	串行模式（最稳但慢）
calamari_require_ordering_info	True	要求可重排信息
calamari_fallback_to_sequential	True	批量失败自动降级串行
5.3 VLM OCR 三种模式
模式	名称	说明
tile	逐块（推荐）	按Marker 原逻辑
merge	区域合并	相邻块合并处理
full_page	整页	一次处理整页
最佳配置推荐：


Surya Layout + VLM 整页模式
- Surya 快速检测版面结构（~10秒）
- VLM 处理整页内容（利用大模型能力）
5.4 LLM 增强配置
支持的 LLM 提供商：

提供商	说明
ollama	OpenAI 兼容 API（推荐）
gemini	Google Gemini
azure	Azure OpenAI
claude	Anthropic Claude
LLM 处理模块（10个）：

模块	说明
表格优化	修正表格结构
公式识别	识别数学公式
图片描述	生成描述性文本
手写识别	识别手写内容
智能降噪	过滤无关符号
页面校正	修正阅读顺序
章节标题	优化标题层级
表单识别	识别表单结构
复杂区域	处理复杂布局
印刷页码校正	修正页码
让我继续读取更多内容，了解处理流程和主函数。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py (lines 2501-3000)
好的，我已经读取了2500-3000行。让我输出第六部分分析。

📊 Contexture 技术报告 - 第六部分：处理流程与并发架构
6.1 批处理模式（3种）
模式	说明	适用场景
自动	根据页数自动决定	默认
单批处理	一次性处理所有页面	小文档
分批处理	分批处理大文档	大文档/本地部署
分批参数：

参数	默认值	说明
batch_threshold	50	分批阈值（页）
pages_per_batch	25	每批页数
cooling_seconds	5	批次间冷却（秒）
6.2 VLM Direct 处理流程

1. 预读取文件内容到内存（避免 Streamlit 清理）
2. 创建全局信号量（并发控制）
3. 按批次处理：
   - 创建临时文件
   - asyncio.gather 并行处理
   - 立即清理临时文件- 保存结果
   - 批次间休息
4. 创建 ZIP 打包
6.3 OCR Direct 处理流程

1. 创建 OcrDirectAsyncConverter
2. 支持暂停-恢复机制
3. 按批次处理：
   - 检查文件可访问性
   - 异步并发处理
   - ModelCrashError 特殊处理
   - 保存结果
4. 创建 ZIP 打包
6.4 关键工程优化
预读取文件内容：避免 Streamlit 长时间运行后清理文件缓存
文件锁定检查：检测文件是否被 PDF 阅读器打开
安全清理临时文件：带重试机制的清理函数
暂停-恢复机制：支持中断后继续处理
让我继续读取剩余内容，了解传统模式的处理流程。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py (lines 3001-3500)
好的，我已经读取了3000-3500行。让我输出第七部分分析。

##📊 Contexture 技术报告 - 第七部分：传统模式处理流程

7.1 传统模式（Pipeline）处理流程

1. 加载模型 artifacts
2. 遍历每个文件：
   - 检测总页数
   - 根据批处理模式分割页码范围
   - 构建配置参数
   - 创建 PdfConverter
   - 构建文档 (build_document)
   - 渲染输出 (Markdown/JSON/HTML/Chunks)
   - 合并批次结果
   - 保存输出文件
3. 创建 ZIP 打包
7.2 配置参数传递链

UI配置 → config_params → build_config_dict() → config_dict → PdfConverter
7.3 渲染器映射
格式	渲染器类
markdown	MarkdownRenderer
json	JSONRenderer
html	HTMLRenderer
chunks	ChunkRenderer
7.4 诊断日志系统
传统模式包含详细的诊断日志：

文件哈希
OCR/Layout 后端
处理器配置状态
处理耗时统计
让我查看文件的剩余部分，了解输出保存逻辑。

Read d:\datalab\Contexture\marker\scripts\streamlit_app.py (lines 3501-3800)
好的，我已经完成了 streamlit_app.py 的完整阅读（3625行）。现在让我整理并分段输出完整的技术报告。

Update Todos

分析 UI 入口与配置架构

分析三大转换模式

分析后端解耦配置

分析提示词模板系统

分析处理流程与并发架构

输出完整技术报告
好的，让我分段输出完整的技术报告。

📊 Contexture 技术报告 - 第八部分：输出与保存系统
8.1 输出格式支持
格式	文件扩展名	说明
markdown	.md	Markdown 格式
json	.json	JSON 结构化数据
html	.html	HTML 网页格式
chunks	_chunks.json	分块 JSON
8.2 输出文件命名规则

{文件名}_{时间戳}.{扩展名}
例如:document_20260208_143022.md
带页码范围时：


{文件名}_p{起始}-{结束}_{时间戳}.{扩展名}
例如: document_p1-10_20260208_143022.md
8.3 元数据保存
每个输出文件附带 _meta.json 元数据文件，包含：

文档信息
处理参数
页面信息
8.4 ZIP 打包
所有输出文件自动打包为 ZIP：

VLM Direct: vlm_direct_results.zip
OCR Direct: ocr_direct_results.zip
传统模式: marker_output_{时间戳}.zip
现在让我输出完整的技术报告总结。

📋 Contexture 技术报告 - 总结
一、项目概览
项目	值
项目名称	Contexture / 经纬
UI 文件	marker/scripts/streamlit_app.py
代码行数	3625 行
页面标题	兰台·PageAnchor
二、三大转换模式
模式	转换器	特点	适用场景
传统模式	PdfConverter	Pipeline 流水线	通用文档
VLM Direct	VlmDirectAsyncConverter	纯 VLM 端到端	复杂文档
OCR Direct	OcrDirectAsyncConverter	Chandra 专用	手写/古籍
三、后端解耦架构
版面识别后端：

后端	说明
surya	内置深度学习（默认）
vlm	VLM 版面识别
yolo	DocLayout-YOLO
OCR 后端：

后端	说明
surya	内置 OCR（默认）
vlm	VLM OCR
calamari	历史文献专用
四、核心配置项统计
类别	配置项数量
转换模式	3
版面识别后端	3
OCR 后端	4
VLM 提示词模板	9
LLM 处理模块	10
页码正则预设	4
自定义编号来源	4
输出格式	4
五、创新功能清单
PageAnchor 页码锚点系统

支持阿拉伯/罗马/中文数字
SC 档案编号 OCR 容错
自定义正则表达式
边码识别系统

MarginalAnnotation（边码/页边注）
InlineAnnotation（行内小字注）
多Key 负载均衡

API Key Pool
API Key Rotator
建议并发数 = Key数量 × 3
批处理优化

暂停-恢复机制
批次间冷却（散热）
文件锁定检查
提示词模板系统

9 种文档类型模板
17 种语言预设
API 参数预设
<thinking> 让我继续输出技术报告的剩余部分。 </thinking>
六、处理流程图

┌─────────────────────────────────────────────────────────────┐
│                    Contexture 处理流程                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐                                            │
│  │  PDF 输入   │                                            │
│  └──────┬──────┘                                            │
│         │                                                │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              转换模式选择                            │   │
│  ├─────────────┬─────────────┬─────────────────────────┤   │
│  │  传统模式   │ VLM Direct  │     OCR Direct          │   │
│  │  Pipeline   │  纯 VLM     │     Chandra             │   │
│  └──────┬──────┴──────┬──────┴──────────┬──────────────┘   │
│         ││                │
│         ▼             ▼                  ▼                  │
│  ┌─────────────┐ ┌─────────────┐  ┌─────────────┐          │
│  │ 版面识别   │ │ VLM API│  │ Chandra API │          │
│  │ Surya/VLM/ │ │ 异步并发   │  │ 异步并发    │          │
│  │ YOLO       │ └──────┬──────┘  └──────┬──────┘          │
│  └──────┬──────┘       │                 │
│         │              │                 │                  │
│         ▼              │                 │                  │
│  ┌─────────────┐       │                 │                  │
│  │ OCR 识别   │       │                 │                  │
│  │ Surya/VLM/ │       │                 │                  │
│  │ Calamari   │       │                 │                  │
│  └──────┬──────┘       │                 │                  │
│         │              │                 │                  │
│         ▼              │                 │                  │
│  ┌─────────────┐       │                 │                  │
│  │ 处理器链   │       │                 │                  │
│  │ 20+ 处理器 │       │                 │                  │
│  └──────┬──────┘       │                 │                  │
│         │              │                 │                  │
│         ▼              ▼                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              渲染输出                                │   │
│  │Markdown / JSON / HTML / Chunks                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
七、配置参数完整清单
让我查看核心转换器的实现，补充技术报告。

Globpattern: "*.py"
Found 8 files
好的，让我继续分析核心转换器的实现。

Read d:\datalab\Contexture\marker\converters\vlm_direct_async.py
好的，让我继续分段输出技术报告。

📊Contexture 技术报告 - 第九部分：核心转换器分析
9.1 VlmDirectAsyncConverter 配置参数
参数	类型	默认值	说明
vlm_direct_base_url	str	Gemini 中转	API Base URL
vlm_direct_model	str	gemini-2.5-flash	模型名称
vlm_direct_api_key	str	-	API 密钥
vlm_direct_prompt	str	DEFAULT_PROMPT	转换提示词
vlm_direct_image_format	str	jpeg	图像格式
vlm_direct_max_image_dimension	int	2048	图像最大边长
vlm_direct_jpeg_quality	int	90	JPEG 质量
vlm_direct_timeout	int	600	超时时间（秒）
vlm_direct_max_tokens	int	0	最大输出 token
vlm_direct_max_retries	int	3	最大重试次数
vlm_direct_max_concurrent	int	5	最大并发数
9.2 页码锚点系统

# 核心组件
PageAnchorFormatter# 格式化器（{n} 格式）
PageAnchorPlugin     # 插件（位置控制）
PrintedPageExtractor # 印刷页码提取器
CustomIDInjector     # 自定义编号注入器
让我继续查看 OCR Direct 转换器。

Read d:\datalab\Contexture\marker\converters\ocr_direct_async.py
好的，让我继续分段输出技术报告。

📊 Contexture 技术报告 - 第十部分：OcrDirectAsyncConverter 分析
10.1 OcrDirectAsyncConverter 配置参数
参数	类型	默认值	说明
ocr_endpoint	str	localhost:1234/v1	OCR API 端点
ocr_model	str	chandra	模型名称
ocr_output_format	str	json	输出格式
ocr_max_tokens	int	4096	最大 token
ocr_temperature	float	0.0	温度（严格OCR）
ocr_timeout	int	120	超时时间
ocr_concurrency	int	5	最大并发数
ocr_batch_size	int	10	批次大小
ocr_batch_rest	float	2.0	批次间休息
ocr_resize_max	int	1024	图像最大尺寸
ocr_image_format	str	JPEG	图像格式
ocr_image_quality	int	60	JPEG 质量
10.2 后处理配置
参数	说明
ocr_noise_removal	噪音过滤
ocr_noise_patterns	自定义噪音正则
ocr_footnote_fix	脚注修复
ocr_filter_page_header	过滤页眉标记
ocr_filter_page_footer	过滤页脚标记
<thinking> 让我继续查看 formatters 模块，了解页码锚点系统的实现。 </thinking>
让我查看 formatters 模块，了解页码锚点系统的实现。

Read d:\datalab\Contexture\marker\formatters.py
好的，让我继续分段输出技术报告。

📊 Contexture 技术报告 - 第十一部分：页码锚点系统
11.1 核心组件
组件	功能
PageAnchorFormatter	格式化器，生成 {n} 格式锚点
PageAnchorPlugin	插件，控制锚点位置和页码标签
PrintedPageExtractor	从内容提取印刷页码
CustomIDInjector	自定义编号注入器
11.2 锚点格式

{0}        ← 页序锚点（0-based）

---

<!-- Page: SC001 -->  ← 印刷页码标签
页面内容...
11.3 位置选项
位置	说明
before	锚点在页面内容前
after	锚点在页面内容后
both	锚点在页面两端
现在让我更新TodoWrite 并输出最终的技术报告总结。

Update Todos

输出完整技术报告
好的，让我继续输出最终的技术报告总结。

📊 Contexture 技术报告 - 最终总结
一、项目架构总览

Contexture / 经纬
├── 三大转换模式
│   ├── 传统模式 (Pipeline)
│   ├── VLM Direct模式
│   └── OCR Direct 模式
├── 后端解耦架构
│   ├── 版面识别后端 (Surya/VLM/YOLO)
│   └── OCR 后端 (Surya/VLM/Calamari)
├── 页码锚点系统 (PageAnchor)
├── 提示词模板系统 (9种预设)
└── 并发处理架构 (API Key Pool)
二、核心统计数据
指标	数值
UI 代码行数	3625 行
转换模式	3 种
版面识别后端	3 种
OCR 后端	4 种
提示词模板	9 种
LLM 处理模块	10 个
页码正则预设	4 种
输出格式	4 种
三、配置参数完整清单
3.1 转换模式配置
模式	转换器类	主要参数
传统	PdfConverter	layout_backend, ocr_backend, use_llm
VLM Direct	VlmDirectAsyncConverter	vlm_direct_* (20+ 参数)
OCR Direct	OcrDirectAsyncConverter	ocr_* (15+ 参数)
<thinking> 让我继续输出技术报告的剩余部分。 </thinking>
3.2 版面识别后端配置
后端	配置参数
Surya	无需额外配置
VLM	vlm_layout_base_url, vlm_layout_model, vlm_layout_api_key, vlm_layout_prompt_template
YOLO	yolo_base_url, yolo_model, yolo_confidence_threshold
3.3 OCR 后端配置
后端	配置参数
Surya	ocr_batch_size, force_ocr
VLM	openai_base_url, openai_model, vlm_mode, vlm_prompt
Calamari	calamari_base_url, calamari_model, calamari_batch_size, calamari_sequential_mode
四、创新功能清单
功能	说明	适用场景
PageAnchor 系统	页码锚点 + 印刷页码提取	所有模式
正则预设系统	4种预设 + 自定义	VLM/OCR Direct
边码识别	MarginalAnnotation + InlineAnnotation	古籍/经典
多Key负载均衡	API Key Pool + Rotator	大规模处理
暂停-恢复机制	模型崩溃后继续	OCR Direct
批次间冷却	显卡散热	本地部署
五、处理流程对比
模式	流程	速度	准确度
传统	PDF → Layout → OCR → Processors → Render	中	高
VLM Direct	PDF → VLM API → Markdown	快	最高
OCR Direct	PDF → Chandra API → Markdown	中	最高
<thinking> 让我继续输出技术报告的剩余部分。 </thinking>
六、人文学科专用功能
功能	说明
Calamari OCR	gt4histocr 历史文献模型
中文古籍模板	竖排、右到左
哥特体德文模板	德文古籍
SC档案编号	OCR 容错（5C→SC）
边码识别	版心叶码、Stephanus 编码
行内小字注	双行小字、夹注、割注
七、技术报告结论
Contexture / 经纬 是一个面向人文学科的大规模文献结构化提取平台，具备以下特点：

架构创新：三大转换模式 + 后端解耦
工程质量：并发架构 + 容错机制
领域适配：人文学科专用功能
可扩展性：插件化设计
适用场景：

历史文献数字化
古籍整理
档案馆文献处理
学术论文提取
这份技术报告可以作为后续开发和维护的参考依据。如需深入分析某个具体模块，请告诉我。