# Changelog

本文件记录 經緯·Contexture 的重要版本变化。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [0.5.0] - 2026-06-06

0.5.0 是在 0.3 系列稳定能力基础上完成的架构系统化版本。本版本保持本地单用户发布形态，同时将运行入口、中间表示、后端能力目录、外部模型适配、质量评估、UI 执行辅助模块和 Markdown 后处理整理为更清晰的工程边界。

本版本不包含多用户系统、公网认证、服务队列、管理员控制台或分布式 worker。这些能力被保留为后续服务版本的开发方向。

### 新增

#### Runtime 与任务执行

- 新增 `aih_contexture/runtime/` 运行层，提供任务、结果、产物、运行分发和 UI 配置边界。
- 新增 `ContextureJob` 与 `ContextureResult`，用于统一本地 UI、CLI、API bridge 可复用的任务契约。
- 明确 runtime 支持的主线模式：
  - `pipeline`
  - `vlm_generalized`
  - `vlm_specialized`
  - `markdown_postprocess`
- `office` 保留为规划型模式；runtime runner 当前会显式拒绝该模式，避免把未发布能力暴露为可执行能力。
- 新增或整理运行辅助模块：
  - `runtime/job.py`
  - `runtime/runner.py`
  - `runtime/artifacts.py`
  - `runtime/config_builder.py`
  - `runtime/ui_config.py`
  - `runtime/model_lifecycle.py`
  - `runtime/vlm_middle.py`
  - `runtime/vlm_repair.py`
  - `runtime/backend_field_sets.py`
  - `runtime/subprocess_stream.py`

#### Middle JSON 与 Scholarly Markdown

- 新增 `aih_contexture/middle/`，将 Middle JSON 作为统一机器中间表示。
- 新增 Middle schema、validation、debug Markdown、scholarly Markdown、heading levels、labels 等模块。
- 新增面向不同来源的 Middle adapters：
  - document adapter
  - MinerU official adapter
  - VLM JSON adapter
  - OCR direct adapter
  - layout adapter
  - external layout adapter
  - external OCR adapter
  - external document adapter
- Middle JSON 支持文本、标题、页眉、页脚、页码、脚注、边注、行内注、参考文献、图注、图像、表格、公式、复杂区域等块类型。
- Scholarly Markdown 被明确定位为 Middle JSON 之上的人工校阅交换层。
- Scholarly Markdown 当前规则包括：
  - 页锚点 `{0}`、`{1}` 等。
  - 印刷页码注释 `<!-- Page: X -->`。
  - `heading_level=1` 渲染为 `#`。
  - 脚注引用和脚注块使用 `<sup>n</sup>`。
  - 边注使用结构化 HTML comment。

#### Backend 能力目录与诊断

- 新增 `aih_contexture/backends/` 后端能力层，包含 catalog、capabilities、diagnostics、external config、pipeline selection 等模块。
- 新增 layout、OCR、VLM、document/structure 后端 registry/runtime 结构。
- 新增 `contexture_backends`，用于查看 backend catalog。
- 新增 `contexture_doctor`，用于统一检查 backend catalog、本地依赖、sidecar Python 与可选服务探测状态。
- 后端诊断默认保持轻量；显式开启 service probe 后可检查 Calamari、VLM/OpenAI-compatible、PaddleOCR-VL 等服务端点。

#### Layout 后端

- 新增或形式化以下 layout 后端：
  - `surya`
  - `vlm_layout`
  - `external_layout_sidecar`
  - `mineru_pp_doclayout_v2`
  - `mineru_pp_doclayout_v2_direct`
  - `paddle_pp_doclayout_plus_l`
  - `paddle_pp_doclayout_v3`
- 新增 External Layout Sidecar，用于接入 MinerU/Paddle/通用 layout JSON 或 Contexture Middle JSON。
- 新增 MinerU Pipeline Sidecar，用于调用 MinerU CLI pipeline 并接入 Contexture 外部 layout 路径。
- 新增 MinerU PP-DocLayoutV2 Direct 路径，用于直接调用 MinerU layout model sidecar。
- 新增 Paddle PP-DocLayout Plus-L / V3 可选 layout adapter。
- 移除遗留 YOLO layout 相关实现；选择 `layout_backend="yolo"` 时会得到迁移错误。

#### OCR 后端

- 新增或形式化以下 OCR 后端：
  - `surya`
  - `vlm_ocr`
  - `calamari`
  - `paddle_ocr_v5`
  - `paddleocr_vl_ocr`
  - `tesseract`
- 新增 Calamari service-backed OCR 路径。
- 新增 PaddleOCR PP-OCRv5 adapter，将识别文本写回 Pipeline line/span 结构。
- 新增 PaddleOCR-VL OCR 路径，基于已有 layout block crop 做 VLRecognition。
- 新增 Tesseract OCR 路径，通过系统 Tesseract 可执行文件识别行文本。

#### VLM 泛化与特化

- 新增或整理以下 VLM 后端目录项：
  - `vlm_generalized`
  - `chandra`
  - `churro`
  - `paddleocr_vl`
  - `mineru_vl`
- 新增 PaddleOCR-VL 特化路径，支持 PaddleOCR-VL 模型族 profile，并保留官方 prompt 协议。
- 新增 MinerU-VL 特化路径，支持 layout detection + block recognition prompt 的结构化接入方式。
- 泛化 VLM 支持 Middle JSON 生成、失败页诊断、修复/rerender 和页面级 checkpoint。
- 特化 VLM/OCR UI 路径支持批次级暂停/恢复和已完成输出保留。

#### Document/Structure 后端

- 新增 document/structure 后端入口：
  - `backends/document/paddle_structure_runtime.py`
  - `scripts/paddle_structure.py`
  - `contexture_paddle_structure`
- 该路径用于接入 Paddle Structure 一类文档结构化输出；0.5 中尚未提升为独立 runtime mode。

#### Import、评估与可视化 CLI

- 新增 Middle/import 相关 CLI：
  - `contexture_middle`
  - `contexture_import_document`
  - `contexture_import_vlm_json`
  - `contexture_import_ocr_direct`
  - `contexture_import_layout`
  - `contexture_import_ocr`
- 新增评估、诊断与可视化 CLI：
  - `contexture_eval_layout`
  - `contexture_eval_markdown`
  - `contexture_download_layout_smoke`
  - `contexture_visualize_layout`
  - `contexture_compare_layout`
- 新增外部后端辅助 CLI：
  - `contexture_paddle_ocr`
  - `contexture_paddle_sidecar`
  - `contexture_paddle_structure`

#### Markdown 后处理

- 将 Markdown 后处理提升为正式 runtime mode：`markdown_postprocess`。
- 支持 Markdown 文件/文本、Middle JSON、MinerU official JSON 作为后处理输入。
- 新增或整理后处理模块：
  - `postprocess/markdown_engine.py`
  - `postprocess/markdown_config.py`
  - `postprocess/printed_page_repair.py`
  - `postprocess/markdown_lm.py`
  - `postprocess/reporting.py`
  - `scripts/ui/markdown_postprocess_runner.py`
- 支持 Markdown cleanup、印刷页码审阅、页码修复 proposal、可选 LLM review/correction、Middle rerender、MinerU import + rerender、postprocess report 输出。

#### UI 执行辅助模块

- 新增 `aih_contexture/scripts/ui/` 下的可测试 UI helper，用于拆分 Streamlit 中的配置、批处理、任务状态、输出保存和后端参数逻辑。
- UI helper 覆盖 backend selector、file input、batch plan、pipeline runner、VLM runner、output saver、task state、Middle debug settings、Markdown postprocess runner 等能力。

#### Vendor 兼容层

- 新增 `aih_contexture/vendor/`，用于隔离外部模型协议差异：
  - `vendor/paddleocr_vl_compat.py`
  - `vendor/mineru_vl_compat/blocks.py`
  - `vendor/mineru_vl_compat/table.py`

#### Evaluation

- 新增 `aih_contexture/evaluation/`，用于 layout comparison、layout-to-Middle evaluation、layout overlay、scholarly Markdown evaluation 和 smoke manifest sources。
- Scholarly Markdown evaluator 可检查页锚点、旧式 page header/footer casing、旧式 superscript markers、旧式 margin syntax、结构化 comment block 和基础结构指标。

### 变更

- Backend catalog 明确为能力目录和诊断入口；builder 创建仍保留在 Pipeline 选择逻辑中。
- Pipeline builder 创建路径保留在 `backends/pipeline.py`，完整 factory registry 迁移留待后续版本。
- `MarginalAnnotationProcessor` 与 `InlineAnnotationProcessor` 接入 Pipeline 处理器链，默认关闭，显式配置后生效。
- `processor_debug_summary` 可暴露 processor 启用、禁用和执行顺序信息。
- VLM 泛化路径拆分为异步转换、Middle 提取、修复/rerender、UI batch runner、输出保存和进度跟踪等更清晰的边界。
- `/v1/convert` 明确为可信本地同步 runtime bridge，公网 server-mode 后续必须走 upload/storage-root job submission。
- API 异常处理改用项目 logger，避免直接 `traceback.print_exc()`。
- 安装脚本在安装依赖后会以 editable/no-deps 方式注册本地包，确保 `contexture_gui`、`contexture_server`、`contexture_doctor` 等命令入口可用。
- 升级脚本更新为 0.5 发布包覆盖清单，包含 `.streamlit`、`assets`、`data`、`examples`、`signatures`、`tools` 和新增根入口文件。

### 修复

- 修复 runtime API 错误路径直接打印 traceback 的问题。
- 修复 `office` 规划模式可能被误认为当前可执行模式的边界表达。
- 修复 `yolo` 遗留 layout 后端在 0.5 发布包中的陈旧暴露问题。
- 修复部分 UI 配置构造、后端字段映射和 batch runner 难以单独测试的问题。
- 修复发布包中 API profile 示例曾包含非空真实密钥形态的问题；发布版中相关 `api_key` 已清空。
- 修复发布文档和 UI placeholder 中出现本机绝对路径的问题。

### 验证

- 测试文件数量从 0.3.1 的 43 个扩展到 0.5.0 的 147 个。
- 已完成以下发布前定向验证记录：
  - API/backend closeout checks：31 passed。
  - 0.5 baseline focused regression：91 passed。
  - backend diagnostics/doctor focused checks：15 passed。
  - final release targeted regression：285 passed。
- 发布前执行敏感信息复扫，未发现明显真实 API key、token、私有用户目录或本机路径残留。
- 发布前清理 `.pytest_cache`、`__pycache__`、临时目录和开发收口文档。

### 打包

- 发布目录按 0.3.1 发布版形态清理，移除临时目录、缓存、内部收口计划和工程评估文档。
- `pyproject.toml` 版本号更新为 `0.5.0`。
- 发布包保留源码、测试、示例数据、安装/启动/升级脚本、README、CHANGELOG、许可证元数据、示例配置和 `VERSION_0.5_RELEASE_REPORT.md`。
- 发布包保留空 API profile 示例和 sidecar/VLM specialized backend 示例；不包含用户私密配置、临时输出、debug-heavy data 或本机运行缓存。

### 已知边界

- 0.5 不提供多用户 Web 应用、服务队列、Basic Auth 公网部署壳、管理员控制台或分布式 worker。
- 重模型实际推理、外部 MinerU/Paddle/PaddleOCR/Tesseract/Calamari 全量集成和公网部署验证不属于本次本地单用户发布验证范围。
- 泛化 VLM 已具备页面级 checkpoint；特化 VLM/OCR 当前主要提供批次级 UI 暂停/恢复，尚未统一为所有后端共享的服务级 durable job recovery。

## [0.3.0] - 2026-04-27

0.3.0 是面向实际批量文献转换的稳定性升级版本。相比 0.1.0，本版本重点改进页码溯源、VLM 泛化 OCR、Churro/Chandra 后端、Streamlit 使用体验和发布升级流程。

### 核心改进

- **页码溯源系统升级**：将页码处理从简单页眉/页脚提取升级为“机器页序 `{n}` + 印刷页码 `<!-- Page: X -->` + 页眉/页脚元数据”的双层溯源结构。
- **印刷页码识别更稳**：新增多候选打分机制，降低日期、年份、卷号、期号、报刊长页眉等内容被误识别为页码的概率。
- **Markdown 页码后处理**：新增 Markdown 后处理模块，可审阅印刷页码序列、识别异常段、生成修复建议，并在应用模式下修复缺失或异常页码。
- **LLM 辅助页码校正**：新增 LLM 印刷页码修正处理器，可在复杂页码序列中辅助判断和写回修正结果。
- **VLM 泛化模式更可诊断**：新增逐页 diagnostics 和 OpenAI-compatible response metadata，可区分非 JSON、坏 JSON、缺字段、字段类型错误、HTTP 错误、截断、重试耗尽和 Markdown 转换失败。
- **VLM teacher prompt 更稳**：JSON 严格输出保持开启；防幻觉默认开启；bbox 作为高级选项默认开启；图片描述改为非强制开关；thinking/reasoning 请求级默认关闭。
- **边注和脚注默认更干净**：边注识别默认关闭；关闭边注时不再提示模型输出 Marginal-Note 标签；脚注不再生成 `↩` 返回箭头。
- **Churro/Chandra 错误更早暴露**：增强 VLM 特化与 Churro 输出诊断，避免空 XML、空文档等问题延迟表现为模糊的 XML 解析错误。
- **Streamlit 批处理体验改进**：上传上限提升到 1024 MB；启动脚本会跳过已占用端口；VLM 泛化模式保留“多页 PDF 串行文件处理”和“单页多文件批次处理”两种并发语义。
- **0.1 到 0.3 软升级支持**：新增一键升级脚本，可复用 0.1 既有虚拟环境和 LM Studio 模型，只替换代码、文档、安装脚本和启动脚本。

### 新增

- 新增 `aih_contexture/postprocess/` Markdown 后处理框架：
  - `markdown_config.py`
  - `markdown_engine.py`
  - `markdown_lm.py`
  - `printed_page_repair.py`
  - `reporting.py`
- 新增 `aih_contexture/processors/llm/llm_printed_page_correction.py`，用于 LLM 辅助印刷页码修正。
- 新增 `aih_contexture/processors/page_footer.py`，增强页脚相关处理能力。
- 新增 `aih_contexture/processors/footnote_policy.py`，统一脚注策略处理。
- 新增 VLM prompt 管理与预设模块：
  - `aih_contexture/prompts/manager.py`
  - `aih_contexture/prompts/presets.py`
- 新增 Churro / Chandra / VLM 输出解析工具：
  - `aih_contexture/utils/churro_output.py`
  - `aih_contexture/utils/chandra_output.py`
  - `aih_contexture/utils/vlm_json_output.py`
- 新增 OCR 服务抽象与工厂：
  - `aih_contexture/services/ocr_base.py`
  - `aih_contexture/services/ocr_churro.py`
  - `aih_contexture/services/ocr_factory.py`
  - `aih_contexture/services/lmstudio_native.py`
- 新增 Kimi API profile 示例：`configs/api_profiles/kimi.json`。
- 新增 0.3 更新说明：`UPDATE_0.3.md`。
- 新增 0.1 到 0.3 一键升级脚本：
  - `upgrade_from_0.1.ps1`
  - `upgrade_from_0.1.bat`
  - `upgrade_from_0.1.sh`
- 新增页码处理、Markdown 后处理、VLM 异步转换相关测试。

### 变更

- 重写 `PageNumberProcessor` 的页码提取逻辑，从单候选提取改为区域候选收集、格式识别、候选打分、去重与跨页选择。
- 调整 Markdown 页锚点语义：`{n}` 固定表示 PDF/机器页序，印刷页码通过 `<!-- Page: X -->` 注释表达。
- Markdown 渲染器支持输出可选页眉/页脚注释和图片描述注释。
- VLM 泛化 JSON 处理链路改为保留失败来源，不再把所有问题混成单一 `parse_error`。
- OpenAI-compatible 本地/LM Studio 路线保持严格批次，一批全部完成后再进入下一批。
- VLM 泛化 UI 的提示词区域改为“识别策略与提示词”，并新增/调整防幻觉、bbox、confidence、表格公式增强、图片描述、边注识别等开关。
- Streamlit JSON 输出可附加 diagnostics 与 response metadata，便于复盘每页转换结果。
- 上传大小限制提升到 1024 MB。
- 启动脚本增加端口占用跳过逻辑。
- `pyproject.toml` 版本号更新为 `0.3.0`。

### 修复

- 修复 VLM 泛化 JSON 模式中 Markdown 结果可能被再次当作 JSON 处理的问题。
- 修复 `confidence: null` 导致 JSON 转 Markdown 报错的问题。
- 修复边注关闭后仍可能输出 `**[Marginal-Right]**` 的问题。
- 修复脚注 HTML 输出中出现 `↩` 返回箭头的问题。
- 修复 VLM prompt 中示例值可能诱导模型猜测页码、bbox、confidence 等字段的问题。
- 修复 Churro/VLM 特化链路中空 XML 或空输出报错不清晰的问题。
- 修复 Streamlit 保存配置时部分 VLM 泛化开关没有稳定写入的问题。

### 升级说明

- 推荐从 0.1 采用软升级：复用旧 `.venv` 和 LM Studio 模型，只替换代码与脚本。
- 如果旧目录为 `D:/path/to/AIH-Contexture`，可在 0.3 发布目录运行：

  ```powershell
  .\upgrade_from_0.1.ps1
  ```

- 如果旧目录不同，可指定目标目录：

  ```powershell
  .\upgrade_from_0.1.ps1 -TargetDir "D:\path\to\你的旧目录"
  ```

- 脚本会备份旧代码，保留 `.venv`、`.env`、`configs`、`output`、`uploads`、`conversion_results`、`debug_data` 等用户环境和数据。
- 如需先预演，可运行：

  ```powershell
  .\upgrade_from_0.1.ps1 -DryRun
  ```

---

## [0.1.0] - 2025-02-11

### 基于 Marker 的首个独立发布版本

Contexture 作为独立项目的首个版本，基于 Marker 进行了人文学科文献结构化能力开发。

### 新增

#### 架构能力

- OCR 后端可插拔架构：支持 Surya / Calamari / Chandra / VLM。
- Layout 后端可插拔架构：支持 Surya / YOLO / DocLayout-YOLO / VLM。
- 三模式处理架构：传统 Pipeline / VLM 泛化 / VLM 特化。
- 异步并发处理架构：支持批量文档处理。

#### 人文学科功能

- 双重页码系统：同时追踪 PDF 页码与印刷页码。
- 页码锚点系统：支持 RAG 精确溯源。
- 页码模式识别：支持阿拉伯数字、罗马数字、中文数字页码。
- 页码序列修正：基于模式识别修正异常页码。
- 边注处理器：识别并结构化页边注释。
- 行内小字注处理器：处理古籍夹注、割注。

#### 模板系统

- `modern_publications`：现代学术出版物。
- `chinese_ancient_books`：中国古籍。
- `german_gothic_print`：德语哥特体印刷品。
- `archive_documents`：档案文献。

#### 工具能力

- API Key 池：多 Key 并发、Round-robin 负载均衡、失败自动冷却。
- 批处理工具：GPU 内存自适应批处理参数计算。

### 致谢

本项目基于以下开源项目：

- [Marker](https://github.com/VikParuchuri/marker) (GPL-3.0) - Datalab
- [Surya](https://github.com/VikParuchuri/surya) (GPL-3.0) - Datalab
- [Chandra](https://github.com/VikParuchuri/chandra) (Apache-2.0) - Datalab
- [Calamari OCR](https://github.com/Calamari-OCR/calamari) (Apache-2.0)
