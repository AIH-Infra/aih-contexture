# 独立诊断与正式输出

同目录的多个阅读版本各用完整文件名配对，例如`book_middle_scholarly.diagnostics.json`和`book.page_repaired.review.diagnostics.json`，不会互相覆盖。结果区“查看或下载诊断文件”默认关闭，开启后可单独下载各诊断文件。

待核信息是可选诊断，默认关闭。开启“输出诊断信息”、CLI的`--reading-diagnostics`或配置`emit_reading_diagnostics=true`后，另存`*.diagnostics.json`。该选项不从文档配置继承，不改变正式内容。

Markdown、Middle JSON、HTML、XML等正式输出不插入待核说明、诊断标题和隐藏警告注释；不自动生成旧的table_review/classical_marginalia/review报告。原模型字段、坐标、来源身份及重渲染必需的语义状态仍保留。正式Middle去掉reading_review、classical_marginalia_review、reading_folio_review等派生汇总。书帖签名还原源属性所需的状态保存在semantic_furniture_source，诊断解释另存。

源书原有的“warning/待核/needs review”等文字不得误删。未知数字与不确定边注原文仍保留；仅有充分证据的通用行号按原选项舍去。Bekker和印刷页码继续使用各自规则。边注采用Left marginal note、Right marginal note或Margin；缺少可靠注号时使用中性Footnote，不生成无依据的引用链接。

独立诊断文件包含逐页复核状态、表格与边码证据、处理建议，绑定具体阅读文件名与SHA-256。预览的“查看诊断信息”默认关闭，主动开启后在独立区域展示；源码和下载文件不包含界面提示。修改阅读文件后，旧诊断不得自动匹配。默认不往常规处理摘要和控制台追加待核清单；真实失败仍按原有错误机制报告。

后处理仅清理普通正文的多余空行。代码、pre、公式和表格的原始字符与换行保持不变；代码示例中的页锚点和Page注释不参与页码分析。修复按确认的原偏移写回，不靠全文同名替换。重复页ID无法确定时不自动改写。CRLF与LF分别保留。

保存的来源Middle保留识别证据。基础重渲染和附加后处理分别按明确配置执行；相同来源及配置应可重现输出。旧Middle仍可读取，原始文件不被改写。当前古典分析器版本为0.16。

## 历史识别 JSON 的阅读规则

历史 Pipeline 的单一 marginal-annotation aside 容器解析为边注文本、方位和子类型；原 HTML 及坐标保留在 JSON。未知 HTML 容器不套用此协议。英文文字边注使用 Left marginal note、Right marginal note 或 Margin；连续的存疑纯数字边注可使用 Left margin、Right margin 或 Margin 合并展示，遇到文字或方位变化即结束合并。存疑数字不受已确认行号的舍弃开关影响。

没有词框的历史 JSON 只允许对独立边注整块进行行号识别：须有正文外的位置、长递增序列和稳定的行距证据。正文块中混入的数字不能据此按正则删除。通用行号默认 drop；page_comments 输出实际观察值，例如 `<!-- Lines: 5, 10, 15, 20 -->`。Bekker 使用自己的分析规则，不将康德通用行号套入 Bekker。缺失、OCR 错误或页边界外的行号不补造。

被识别为边注的页眉或页脚，只有位置、文字签名及至少三个独立页的重复同时成立时，才恢复为页眉或页脚。其源内容和分类证据保存在 JSON，重渲染子集仍可复现。印刷页码只从明确观察到的页眉边缘数字恢复，不插值。

无注号脚注保留原文和 Footnote 分类，不按块数自动编号。版权页的出版说明需有出版用语、版权上下文和底部位置共同支持，才保留为普通文本；同样防止将正文块内的小字出版说明再次提取成脚注。真实有编号脚注沿用原注号。

以上规则由主处理采用的 Middle 阅读渲染与 JSON 重渲染共用。原生转换器兼容模式可继续使用其原生 Markdown；显式 render_from_middle 或已启用且具备条件的古典阅读模式才采用 Middle 输出。附加 Markdown 后处理是后续独立步骤，不能把纯重渲染与模型推理视为同一步骤。

## Indra 置信证据与诊断

Indra 原生和混搭路线均在页面 `attrs.indra` 中按 `layout`、`ocr` 保存来源、模式、模型版本、行置信度统计与本次阈值。运行元数据的 `indra.pages` 覆盖所有实际处理页，分批合并不能只保留第一批。证据不复制全文，也不触发自动换后端。布局阶段的 `text_used=false` 表示该次辅助识别文字没有充当最终文字来源；其置信度不是布局类别概率或 PDF 原文字的准确率。

阈值命中的复核解释只进入显式启用的诊断文件及预览的独立诊断区，保存在 `indra_review` 和逐页阅读复核摘要中。默认不产生低置信提示，真实失败仍按错误机制报告。正式 Middle 与 `_meta.json` 不保存派生 `indra.review`；保留原始证据和阈值，以便保存、压缩、重读后按同一规则重新生成诊断。历史原生 Indra 文件中的 `indra_source` 与 `line_confidence` 仍可解析；旧复核对象内的阈值会在保存副本中移入来源元数据，原始历史文件不被改写。
