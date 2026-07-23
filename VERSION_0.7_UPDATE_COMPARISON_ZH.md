# AIH-Contexture 0.7.0 相对原版 0.5.0 的完整更新对比

报告日期：2026-07-13

对比基线：AIH-Contexture 0.5.0 原版发布目录。

对比对象：AIH-Contexture 0.7.0 独立可运行发行目录。

## 1. 核验方法与结论

本报告不是根据文件名或提交记录推断，而是对两棵完整目录树的每一个文件计算 SHA-256 并比较相对路径与内容。

最终对比结果如下：

| 项目 | 数量 | 含义 |
| --- | ---: | --- |
| 原版 0.5 文件 | 585 | 完整原版目录中的全部文件。 |
| 0.7 文件 | 377 | 包含本中文版报告后的最终发行目录。 |
| 字节完全相同 | 252 | 原版文件原样保留。 |
| 内容已修改 | 94 | 原有文件仍在，但内容有功能、配置或发布边界变化。 |
| 0.7 新增 | 31 | 新的运行时能力或发行说明。 |
| 原版未纳入 0.7 | 239 | 全部是有意排除的测试、样例、开发材料、本机配置或旧发布材料。 |

两个关键结论：

1. 没有遗漏任何原版 aih_contexture 运行时代码文件。原版运行时代码为 320 个文件，0.7 为 348 个；原版运行时代码移除数为 0。
2. 0.7 文件数较小是发行包精简，不是运行能力删减。149 个测试文件、64 个样例和数据文件，以及开发和本机状态被有意排除。

## 2. 代码规范与架构延续

0.7 延续原版 0.5 的有效工程规范，而不是另起一套风格：

- Runtime、Middle、Backends、Converters、Processors、Services、Renderers 和 UI helper 仍保持分层；
- Middle JSON 仍是后端输出与渲染之间的机器中间契约；
- Scholarly Markdown 仍是面向人文学术校阅的交换格式；
- 可选后端仍通过 catalog、registry、diagnostics 和显式配置接入；
- CLI 继续使用 Click，桌面启动继续使用 Windows、macOS、Linux 三套脚本；
- 有稳定数据契约的地方继续使用类型注解和 Pydantic。

0.7 的发布边界比原版更严格：主环境只负责可直接安装的能力；MinerU、Paddle 等重型环境作为 sidecar 保持外置；云端或本地 VLM 服务不携带地址、账户或凭据。

## 3. 功能更新摘要

### 3.1 页码、脚注与 Markdown

- 印刷页码改为序列验证，可识别多个独立序列；
- 不再为未验证的前言页自动补负数页码；
- 孤立、噪声式页码候选不再输出为可引用页码；
- 学术编号段落统一输出为 201\.、8\. 等 Markdown 转义形式，避免被渲染成带缩进的列表；
- 脚注引用与定义统一保留为 <sup>n</sup> 语义；
- Churro XML 的视觉上标、Emphasis、Above、Superscript 与纯数字 Addition 可转为行内上标引用；
- 通用 VLM、特化 VLM 与 Markdown 后处理路径统一经过最终 Markdown 格式化。

### 3.2 后端与运行时

- 新增 MinerU OCR sidecar 与可复用 sidecar 进程池；
- 新增 MinerU-VL layout 兼容层；
- 新增 Surya 2 VLM layout/OCR 接入点；
- 新增 Chrome ScreenAI 本地 OCR、searchable PDF 预处理及回流 Pipeline；
- Paddle 与 MinerU 的 diagnostics 从简单路径存在性检查扩展为外部解释器和依赖导入检查；
- Pipeline 子进程会优先使用项目自身 .venv。

### 3.3 UI、批处理与资源管理

- 上传 PDF 立即写入任务临时目录，批量处理状态仅保存路径，不再将多本书常驻内存；
- 成功、取消和失败都会清理上传暂存目录；
- Pipeline、VLM 泛化、VLM 特化与 Markdown 后处理的最终渲染行为进一步统一；
- UI 增加 MinerU-VL、Surya 2、Chrome ScreenAI 与更多 sidecar 配置入口。

## 4. 外挂虚拟环境发现与新电脑可用性

复制 0.7 目录到新电脑后，先运行对应平台的安装脚本。安装脚本创建项目 .venv，随后 Pipeline 子进程会自动选择该解释器，因此 Surya 主流程不需要第二个虚拟环境。

外部环境采用受控发现，不会扫描整块硬盘或信任未知网络服务：

| 能力 | 发现顺序 | 边界 |
| --- | --- | --- |
| MinerU | CONTEXTURE_MINERU_PYTHON、CONTEXTURE_MINERU_COMMAND、CONTEXTURE_MINERU_SOURCE_ROOT；PATH；约定同级目录 | 不自动安装 MinerU。 |
| Paddle | CONTEXTURE_PADDLE_PYTHON；约定同级目录 | 不自动安装 Paddle/PaddleOCR。 |
| Tesseract | PATH 与标准 Windows 安装路径 | 不携带系统 OCR 可执行文件。 |
| VLM 服务 | 用户显式设置端点、模型与凭据 | 不自动发现或连接未知服务。 |
| Chrome ScreenAI | Chrome 已下载的 Screen AI 组件或本地 locro 组件目录 | 缺失时不自动下载组件。 |

doctor 会将缺失依赖或待配置后端明确标记。需要注意：某个 sidecar 被发现，只表示解释器路径可用；该环境中的模型权重或 Python 依赖若不完整，实际运行仍会失败并返回诊断错误。

## 5. 新增文件：逐文件清单

以下 31 个文件在原版 0.5 中不存在。前 28 个是运行时代码，后 3 个是发行文档。

- aih_contexture/backends/ocr/mineru_runtime.py
- aih_contexture/backends/sidecar_pool.py
- aih_contexture/builders/mineru_ocr.py
- aih_contexture/builders/mineru_vl_layout.py
- aih_contexture/builders/surya2_layout.py
- aih_contexture/builders/surya2_ocr.py
- aih_contexture/config/marginal_output.py
- aih_contexture/middle/semantics/__init__.py
- aih_contexture/middle/semantics/footnotes.py
- aih_contexture/processors/marginal_line_numbers.py
- aih_contexture/runtime/chrome_screenai_runtime.py
- aih_contexture/runtime/pipeline_preprocess.py
- aih_contexture/scripts/chrome_screenai_chunk_worker.py
- aih_contexture/scripts/mineru_ocr_sidecar.py
- aih_contexture/scripts/ui/mineru_vl_layout_settings.py
- aih_contexture/scripts/ui/surya2_vlm_settings.py
- aih_contexture/services/layout_mineru_vl.py
- aih_contexture/services/layout_surya2.py
- aih_contexture/vendor/locro/__init__.py
- aih_contexture/vendor/locro/_dll.py
- aih_contexture/vendor/locro/_download.py
- aih_contexture/vendor/locro/_platform.py
- aih_contexture/vendor/locro/_protobuf.py
- aih_contexture/vendor/locro/LICENSE
- aih_contexture/vendor/locro/models.py
- aih_contexture/vendor/locro/ocr.py
- aih_contexture/vendor/mineru_vl_compat/layout.py
- aih_contexture/vendor/surya2_compat.py
- RELEASE_MANIFEST.md
- VERSION_0.7_UPDATE_COMPARISON.md
- VERSION_0.7_UPDATE_COMPARISON_ZH.md

## 6. 修改文件：逐文件清单

以下 94 个原版文件在 0.7 中仍保留，但内容发生了改变。

### 6.1 发布、启动与配置

- .gitignore
- .streamlit/config.toml
- pyproject.toml
- README.md
- start.bat

### 6.2 后端、构建器与转换器

- aih_contexture/backends/diagnostics.py
- aih_contexture/backends/external_config.py
- aih_contexture/backends/layout/mineru_direct_runtime.py
- aih_contexture/backends/layout/mineru_runtime.py
- aih_contexture/backends/layout/registry.py
- aih_contexture/backends/ocr/registry.py
- aih_contexture/backends/pipeline.py
- aih_contexture/backends/vlm/registry.py
- aih_contexture/builders/external_layout_sidecar.py
- aih_contexture/builders/layout.py
- aih_contexture/builders/line.py
- aih_contexture/builders/mineru_direct_layout.py
- aih_contexture/builders/ocr.py
- aih_contexture/builders/vlm_layout.py
- aih_contexture/config/dpi_presets.py
- aih_contexture/config/parser.py
- aih_contexture/config/vlm_model_presets.py
- aih_contexture/converters/ocr_direct_async.py
- aih_contexture/converters/pdf.py
- aih_contexture/converters/vlm_direct_async.py

### 6.3 Middle、处理器、渲染与 schema

- aih_contexture/middle/adapters/document.py
- aih_contexture/middle/adapters/external_layout.py
- aih_contexture/middle/adapters/layout.py
- aih_contexture/middle/adapters/ocr_direct.py
- aih_contexture/middle/scholarly_markdown.py
- aih_contexture/processors/equation.py
- aih_contexture/processors/marginal_annotation.py
- aih_contexture/processors/printed_page_correction.py
- aih_contexture/processors/sectionheader.py
- aih_contexture/processors/table.py
- aih_contexture/renderers/__init__.py
- aih_contexture/renderers/markdown.py
- aih_contexture/schema/blocks/marginalannotation.py
- aih_contexture/schema/blocks/toc.py
- aih_contexture/schema/groups/page.py
- aih_contexture/schema/text/span.py

### 6.4 Runtime、服务与辅助工具

- aih_contexture/runtime/artifacts.py
- aih_contexture/runtime/backend_field_sets.py
- aih_contexture/runtime/runner.py
- aih_contexture/runtime/subprocess_stream.py
- aih_contexture/runtime/ui_config.py
- aih_contexture/runtime/vlm_middle.py
- aih_contexture/services/layout_base.py
- aih_contexture/services/layout_service.py
- aih_contexture/services/layout_vlm.py
- aih_contexture/services/ocr_factory.py
- aih_contexture/services/ocr_tesseract.py
- aih_contexture/services/ocr_vlm_specialized.py
- aih_contexture/services/vlm_layout.py
- aih_contexture/settings.py
- aih_contexture/utils/churro_output.py
- aih_contexture/utils/gpu.py
- aih_contexture/utils/markdown_filters.py
- aih_contexture/utils/vlm_json_output.py
- aih_contexture/vendor/mineru_vl_compat/__init__.py

### 6.5 CLI、API 与 Streamlit UI

- aih_contexture/scripts/backends.py
- aih_contexture/scripts/convert.py
- aih_contexture/scripts/convert_single.py
- aih_contexture/scripts/doctor.py
- aih_contexture/scripts/import_external_document.py
- aih_contexture/scripts/import_external_layout.py
- aih_contexture/scripts/import_external_ocr.py
- aih_contexture/scripts/import_ocr_direct.py
- aih_contexture/scripts/import_vlm_json.py
- aih_contexture/scripts/mineru_layout_direct_sidecar.py
- aih_contexture/scripts/paddle_ocr.py
- aih_contexture/scripts/paddle_structure.py
- aih_contexture/scripts/run_streamlit_app.py
- aih_contexture/scripts/server.py
- aih_contexture/scripts/streamlit_app.py
- aih_contexture/scripts/ui/backend_selectors.py
- aih_contexture/scripts/ui/batch_inputs.py
- aih_contexture/scripts/ui/external_layout_sidecar_settings.py
- aih_contexture/scripts/ui/markdown_postprocess_runner.py
- aih_contexture/scripts/ui/middle_debug_settings.py
- aih_contexture/scripts/ui/mineru_layout_settings.py
- aih_contexture/scripts/ui/page_margin_settings.py
- aih_contexture/scripts/ui/pipeline_config_sections.py
- aih_contexture/scripts/ui/pipeline_file_runner.py
- aih_contexture/scripts/ui/pipeline_processor_settings.py
- aih_contexture/scripts/ui/pipeline_subprocess.py
- aih_contexture/scripts/ui/task_state.py
- aih_contexture/scripts/ui/vlm_config.py
- aih_contexture/scripts/ui/vlm_generalized_runner.py
- aih_contexture/scripts/ui/vlm_output_saver.py
- aih_contexture/scripts/ui/vlm_progress.py
- aih_contexture/scripts/ui/vlm_specialized_runner.py

### 6.6 评估资源

- aih_contexture/evaluation/layout_overlay.py
- aih_contexture/evaluation/smoke_layout_manifest.example.json

## 7. 原版未纳入 0.7：完整类别核验

239 个原版文件未纳入 0.7，类别和数量如下。所有类别均为此前明确指定的非运行时发行内容。

| 原版目录或类别 | 数量 | 处理理由 |
| --- | ---: | --- |
| tests 整棵目录 | 149 | 用户要求的测试、fixture 与开发验证文件。 |
| data 整棵目录 | 64 | 样例转换结果、图片、示例 JSON/Markdown 与开发数据。 |
| .github | 8 | CI、Issue 模板、发布 workflow。 |
| configs | 3 | 本机应用设置和 API Profile，可能包含用户状态或凭据。 |
| examples | 2 | 开发示例，不是运行主路径。 |
| tools | 2 | 开发会话和状态维护脚本。 |
| signatures | 1 | 非运行时签名样例。 |
| 根目录文件 | 10 | 见下方逐项清单。 |

未纳入的 10 个根目录文件如下：

- .pre-commit-config.yaml
- ARCHITECTURE_AND_TECHNICAL_GUIDE.md
- ARCHITECTURE_REVIEW.md
- CHANGELOG.md
- CLA.md
- pytest.ini
- upgrade_from_0.1.bat
- upgrade_from_0.1.ps1
- upgrade_from_0.1.sh
- VERSION_0.5_RELEASE_REPORT.md

除上述类别外，没有任何原版文件被静默排除。尤其是 aih_contexture 下的运行时代码排除数为 0。

## 8. 发布验证与安全复核

已经完成：

- Python 源码编译与主应用入口导入；
- POSIX 安装/启动脚本 bash -n 检查；
- Python 3.12 wheel 构建，wheel 中无测试、字节码、API Profile；
- 最终敏感信息、私有路径、缓存与运行时残留扫描；
- 全量 SHA-256 文件树核对。

发行包不含 API Key、Token、密码、私有 API Profile、本机输出、模型缓存或虚拟环境。保留的外部 URL 是公开依赖、模型或文档链接，不是凭据。

## 9. 仍需诚实说明的风险

0.7 可作为本地单用户发行包使用，但以下架构债务仍与原版 0.5 的审计结论一致：

- runtime runner 仍以 if 分支派发模式，尚未演进为 mode registry；
- processor chain 仍依赖手工顺序，尚无依赖声明与拓扑验证；
- runtime error hierarchy 仍较浅，尚未完整区分超时、认证、资源和页级失败；
- 大量模式配置仍是字典式传递，尚未做到每种模式都有完整 Pydantic schema；
- Chrome ScreenAI 可自动寻找本地组件，但 doctor 还没有专门的可用性诊断。

这些是后续服务化和长期维护风险，不是 0.7 本地发行、安装和核心 Pipeline 使用的阻塞项。
