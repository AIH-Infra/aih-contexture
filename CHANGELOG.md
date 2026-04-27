# Changelog

本文件记录 經緯·Contexture 的重要版本变化。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

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
- 如果旧目录为 `D:/AIH-infra-run/AIH-Contexture`，可在 0.3 发布目录运行：

  ```powershell
  .\upgrade_from_0.1.ps1
  ```

- 如果旧目录不同，可指定目标目录：

  ```powershell
  .\upgrade_from_0.1.ps1 -TargetDir "D:\AIH-infra-run\你的旧目录"
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
