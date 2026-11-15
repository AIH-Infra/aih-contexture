# Changelog

本文件记录 經緯·Contexture 的重要版本变化。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

## [1.1.1] - 2026-11-15

### 修复

- ScreenAI 可检索 PDF 保留带旋转标记和裁剪框的扫描页方向，修复背景横转及内容裁切；继续复用原始扫描图。

## [1.1.0] - 2026-11-14

### 新增与改进

- Pipeline 分批配置统一为“每批页数”，不超过该页数的文件整份处理。短文件队列按资源预算并行处理，进程与模型在文件间复用，长文件批次并行与文件并行分开调度。进度按文件分别显示，任务结束关闭常驻进程。
- Pipeline 并行批次转发页级阶段进度，按文件显示完成页数及活动阶段；自动并发按可用资源预算，手动并发保留设置并提示估算用量。
- ScreenAI 在识别前可清理批注与链接，保留正文和表单可见值；可检索PDF复用扫描图并压缩保存，支持PDF/A输入。
- 可选局域网网关提供任务与节点管理、文献归档、容量准入、保留策略、备份及恢复工具。

### 安装与发布

- 固定本地 Surya 0.17.1、Transformers 4.57.6 及匹配的 PDF 文本依赖；安装脚本校验选定的 PyTorch 运行配置。
- 更新五种处理模式、批量文件和可选局域网部署文档；公开源码包不包含机器配置、凭据、模型、运行环境或开发验收材料。


## [1.0.5] - 2026-11-12

### 修复

- ROCm 实例通过自身 PyTorch 探测 AMD 显存，修复同时安装 NVIDIA 显卡时读取错误设备并将并行进程误限为一的问题。手动性能设置显示用于规划的显卡和可用显存。

## [1.0.4] - 2026-11-12

### 修复

- 上传完成时先处理队列控件事件，再刷新主界面，修复自动刷新与清理按钮同时触发时丢失点击的问题。

## [1.0.3] - 2026-11-12

### 性能

- 批量上传最多四文件并行，复用 HTTP 连接与跨域预检，批次开始和结束时写入暂存清单。队列片段每 0.5 秒刷新，上传期间避免整页重跑，整批上传登记完成后开放任务启动；上传中断后可清理该批缓存。

## [1.0.2] - 2026-11-12

### 修复

- Web UI 批量文件以 256 KiB 分块上传至磁盘，五种模式使用暂存路径。任务收尾删除成功输入，失败与暂停输入保留重试，提供移除和清理入口；兼容迁移已有上传控件中的文件。ZIP 与诊断下载改为流式读取，取消整文件下载缓存。

### 新增

- 局域网调试网关提供认证、持久化文件队列、节点心跳、任务归属和结果下载；原生工作节点组合 ScreenAI 与 Indra 严格版面路径，输出 Markdown、Middle JSON 和执行记录。提供 Docker 网关与 Linux/macOS 原生节点部署说明。

## [1.0.1] - 2026-11-12

### 依赖

- 将项目安装元数据中的 API SDK、Web 服务和解析库版本范围与现行 requirements 安装方式对齐，支持现有 CUDA、ROCm 环境中的依赖版本。

### 性能

- Pipeline 的 ScreenAI 预处理按任务选页执行，保留原文档页数与页码；Indra 跨批次复用源文件身份和模型进程，页面图像由实际消费者按原分辨率加载。
- VLM 泛化按文件复用 PDF 与 HTTP 会话，图像准备移到有界工作线程；断点记录按页追加并校验源文件与配置身份，批次休息作用于页面批次。
- VLM 特化的文件、页面与区块共享 API 请求并发上限；ScreenAI 隔离进程连续处理多个批次，恢复时保留成功结果；暂时性请求错误使用配置的重试次数。
- 任务进度单独刷新，下载与阅读预览按输出文件版本缓存；结构化源复用 Markdown 渲染并限制在途文件；Markdown 后处理共享页面解析并集中应用修改。

### 界面

- 侧栏统一收紧分组、控件、分隔线和提示卡间距，桌面增加设置宽度；宽侧栏的四类导航并排展示。性能推荐与资源明细分层显示，减少重复标题与分隔。
- 配置管理在侧栏分类导航上方独立展示，集中提供预设应用、保存、当前设置导出与导入应用。
- 五个模式在主栏直接选择；设置保留在侧栏，通过侧栏顶部分类标签切换，主栏继续显示文件上传、下载和任务状态，原参数与配置键继续沿用。
- Pipeline 与两种 VLM 模式的侧栏统一为模型设置、内容处理、页码与引证、高级设置四类。
- 统一使用“版面分析 Layout”和“文字识别 OCR”；品牌区采用横贯主内容区的居中横幅，保留 Logo、中英文 slogan 及仓库入口，启动器沿用项目主题配色。
- 品牌头部保留中英文 slogan，并以独立入口展示 GitHub 代码仓库，支持窄屏换行。
- 处理方式保留 Pipeline 模式、VLM 泛化模式、VLM 特化模式、结构化源导入、Markdown 后处理的原始称谓。
- 统一工作台的深靛蓝与暖白配色、标题层级、控件边框和间距，精简品牌头部与设置分组，主区显示当前处理方案。
- 移除后端介绍卡与主流程中的安装实现说明，统一版面分析和文字来源名称，Surya、Indra 排在版面引擎前两位；模型与环境覆盖项收进高级设置。

### 修复

- 输出目录规范化与保存改由控件回调更新，修复“保存默认值”触发的 Streamlit 状态异常；无效目录明确报错并阻止启动，保留修正入口。模板切换、恢复及删除同步编辑器；模板、配置与 API 预设写盘失败显示错误，兼容异常设置元数据，Markdown 后处理载入 API 预设时检查接口类型。
- ScreenAI 两处封装与 Pipeline 统一 Unicode 文字写回，修复希腊文、西里尔文、希伯来文、阿拉伯文和泰文等字符变问号、字体资源重复及混排数字倒序。旧隐藏层按 PDF 指令清理，保留可见正文与图片；可搜索 PDF 只保留新 OCR 文字，含可见正文的页面按原画面生成背景。
- 配置导出读取当前界面，导入成功后立即应用对应模式和参数；补齐模型、内容处理及超时参数的保存恢复，校验导入结构并处理 API Key 占位符。
- Pipeline 通过后台任务实时显示阶段页数与批次；运行中禁用重复启动及历史恢复，逐文件汇总结果并折叠错误详情。输入区区分无效目录与空目录，阅读预览默认显示，移除无效 FP16 开关及重复的必需文件选项。
- Indra 保留值为零的复核阈值，缩小超大页面渲染时使用实际 DPI 映射坐标，并在检测到文字区域但缺少原文字层时生成阅读复核提示。
- GUI 最终配置构建器保留 Indra 模式、模型目录、DPI 和核心数，修复界面设置在提交任务时丢失的问题。
- Indra 严格版面路径直接提取 PDF 已有字符，保留隐形 OCR 文字层作为版面特征，修复已有可提取文字却被判为无文字层的问题。
- Indra 设置根据 OCR 后端显示有效选项，严格禁用时隐藏文字来源与公式识别控件，并区分版面辅助文字和 OCR 输出文字。
- `indra_layout + ocr=none` 或禁用 OCR 时启用严格版面路径，仅加载检测和顺序模型，使用原文字层特征，无文字层时保留区域并标记。严格路径直接读取原 PDF 页码，跨批次复用内部模型进程，输出分阶段耗时。
- Indra 逐页上报内部并行进度，并在返回批次结果前等待内部进程退出、关闭 PDF 句柄，修复 Windows 临时 PDF 清理时的 WinError 32。
- Indra 模型目录留空时自动发现共享运行数据目录的 `models/OCR/Indra`，界面显示实际模型路径。
- Indra 版面与 OCR 共用模型目录、下载开关和 CPU 设置；启动处理前检查环境与模型。性能配置固定外层单进程，内部按物理核心、内存和批次页数规划，避免嵌套进程池及误用显存档案。

## [1.0.0] - 2026-11-04

自 0.9.0 之后的累积变化，作为 1.0.0 发布。依据为各提交与 `FULL_ACCEPTANCE_20261030.md`、`INDRA_MIXED_ACCEPTANCE_20261030.md`、`PLAN_INDRA_INTEGRATION_20261030.md`。

> 说明：2026-10-10 整理的 `aih-contexture-1.0` 目录曾以 0.10 工作目录为基线使用过 1.0.0 的版本号；本次 1.0.0 以 develop 的 0.9.0 之后提交为准，取代该快照。

### 新增

- **Indra OCR**：CPU（ONNX）版面标签 + 阅读顺序 + 文字。版面 `indra_layout` 与 OCR `indra_ocr` 可分别选择：版面可配 PDF 文字层（`--disable_ocr`）、Chrome ScreenAI 或其他 OCR；OCR 可配任意版面；两者同选且未禁用 OCR 时走原生直连（PDF → Middle → Markdown/JSON，不加载 Surya、不占 GPU）。核心数自动规划（物理核心、可用内存、页数、实测收益上限 12）或 `--indra_cores` 手动；运行在独立解释器的 sidecar 中，权重由使用者自备，默认不联网；逐页缓存、页级置信证据与可选复核诊断。可选安装项 `.[indra]`。
- **glm_ocr** 块级 OCR 后端（OpenAI 兼容服务，失败显式记录）。
- **内置 PP-DocLayoutV3**（CPU ONNX，`.[paddle-layout]`）与 **Paddle OCR Torch**（与主环境共用 PyTorch，`.[paddle-torch]`，可选 PP-OCRv5/v6）；原生多边形与阅读顺序保存在 Middle。
- **评估**：`contexture_eval_text`（文字/表格/阅读顺序基线）、基准评测集与运行器、30 页手标版面真值与评分器（`benchmarks/`、`evaluation/`）。
- 模式 `middle_geometry_profile=lean`（不保存逐词坐标）；Pipeline 并行进程数与每批页数按可用显存联动。

### 变更（可能影响现有用法）

- API 在存在失败页时返回 `success=false`，响应附失败页、诊断与警告；Source Package 请求必须提供 `config.output_dir`；多格式请求生成全部所请求格式并新增 `outputs` 映射（首格式 `format/output` 保持兼容）。
- 未指定独立解释器时，PP-DocLayoutV3 改走内置 ONNX 路径；显式指定 Paddle SDK、GPU 或解释器的配置保持原路径。
- 命令行 `--help` 不再误启动 Streamlit；帮助输出对不可编码字符做兼容转义。
- Middle 存储不再丢弃 `native_polygon` 与 `native_reading_order`；span formats 排序输出以保证可复现。

### 已知限制

- 真实浏览器文件上传验收未通过（扩展权限阻断），其余前端流程已验收。
- 所有验收仅在 Windows 本机完成；macOS、Linux 未验证。
- 30 项测试因缺固定模型或文献样本而跳过，对应的可选后端未被普遍实测。
- Indra 在旧式印刷体与脚注上较弱；低置信复核阈值（0.92 / 0.60）为起点，未校准；真实旋转扫描 PDF 未验证。
- OXR 仅为评测候选，未集成。

---

## [0.9.0] - 2026-07-26

0.9.0 consolidates Contexture as a clean, installable single-user source release for Windows, macOS, and Linux. It preserves optional external backends while making direct VLM and text-layer operation easier to automate on a personal workstation or server.

### 新增

- 新增 `contexture_vlm_generalized` 与 `contexture_vlm_specialized` 独立 CLI。
- 两个 VLM CLI 支持 `--config-json`、重复 `--set KEY=VALUE`、`--dry-run` 和环境变量 API Key，适合连接 LM Studio 等本地/局域网推理服务。
- VLM CLI 可保存 Markdown、JSON、HTML 与可选 Middle JSON 产物。

### 变更

- 修复 Layout 禁用时 OCR 下拉框被旧 ScreenAI 迁移状态覆盖的问题；用户明确选择“禁用 OCR”时保持 PDF 文本层快速路径。
- Chrome ScreenAI 默认 worker 调整为 4。
- 文本层快速路径默认文件子进程并发调整为 4，UI 限制为 1–16。
- 发布目录移除本机运行产物、私有 Profile、缓存、日志、开发计划与测试残留，仅保留可安装源码和公开示例配置。

### 边界

- 仍定位为本地单用户工具；不包含公网认证、队列、多用户工作区或分布式 worker。
- VLM 泛化提供页面级 checkpoint/reuse；特化模式保留批次级恢复与已完成产物，不宣称完整断点续跑。

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
