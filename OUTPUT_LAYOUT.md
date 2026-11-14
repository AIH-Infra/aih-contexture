# 输出目录与命名约定

## 当前确认的设计

每个输入文档对应一次独立运行目录。目录名保留来源文件名、运行时间和处理号；目录内部的正式工件使用完整书名作为前缀，不重复运行时间。

```text
output/
└── 资本论_第一卷_20260908_225501_0007/
    ├── 资本论_第一卷.md
    ├── 资本论_第一卷.html
    ├── 资本论_第一卷.json
    ├── 资本论_第一卷_meta.json
    ├── 资本论_第一卷_middle.json       # 仅在启用 Middle 输出时生成
    ├── 资本论_第一卷_middle_report.json # 仅在显式启用校验报告时生成
    ├── run_summary.json                 # 唯一的运行摘要
    ├── page_0001_picture_0001.jpeg
    └── ...
```

## 运行摘要

只保留一种摘要格式：`run_summary.json`。不生成 `run_summary.md`。

同一套 JSON 结构通过 `scope` 区分：

- 文档目录中的 `run_summary.json`：记录单个输入文档；
- 下载 ZIP 根部的 `run_summary.json`：记录整个批次，并在 `files` 中列出每个文档。

摘要记录输入身份、处理号、文件序号、模式、策略、模型或模型组合、关键配置、开始/结束时间、耗时、页数、输出工件、图片数量、状态、警告和错误。敏感配置、API key、完整本机路径不写入摘要。

## `middle_report.json` 的含义

`*_middle_report.json` 不是运行摘要，也不是普通正文输出。它是可选的 Middle JSON 结构校验报告，只在 `emit_middle_report` 开启时生成，记录：

- `ok`；
- 校验统计；
- 结构错误；
- 警告。

因此它不应被放进每次运行的固定输出集合。若用户没有要求 Middle 校验报告，就不生成。

## ZIP

ZIP 文件名由统一规则生成：

- Pipeline：`{ocr模型}_{layout模型}_{YYYYMMDD}_{处理号}.zip`；
- VLM 泛化/特化：`{vlm模型}_{YYYYMMDD}_{处理号}.zip`；
- 结构化源：`structured_source_{YYYYMMDD}_{处理号}.zip`；
- Markdown 后处理：`markdown_postprocess_{YYYYMMDD}_{处理号}.zip`。

ZIP 内部保持平铺，不包含图片，也不保留每个文档的本地目录层级：

```text
surya_mineru_20260908_0007.zip
├── 资本论_第一卷.md
├── 资本论_第一卷.json
├── 资本论_第一卷_meta.json
├── 国富论.md
├── 国富论.json
├── 国富论_meta.json
└── run_summary.json
```

本地目录中的 `run_summary.json` 不必重复放入 ZIP；ZIP 根部的一份批次摘要统一记录每一个文件的运行时间、处理号、模型和结果。打包时使用来源书名重命名本地工件，避免多个目录中的同名文件发生覆盖。

## 实际工件分类

Contexture 目前确实支持多种**业务输出工件**，但它们不是多种运行摘要：

- 正式阅读输出：Markdown、HTML、JSON；
- 可选辅助输出：chunks JSON；
- Middle 调试/审计输出：Middle JSON（必选）、完整 Middle JSON、Middle 校验报告、Middle debug Markdown、学术 Markdown、学术报告；
- 可选版面审计：layout/span overlay PDF；
- 图片：抽取后的 JPEG 等资源；
- 结构化源包：JSONL、索引、原始文件和 source manifest。

这些工件是否生成由分支和选项决定，不应被误称为“运行摘要格式”。
