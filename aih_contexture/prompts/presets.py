"""
VLM Prompt Presets - 预制提示词模板库

提供针对不同文档类型的精简提示词模板，全部输出 JSON 格式。
"""

from typing import Dict

# 预制模板库
PRESET_PROMPTS: Dict[str, Dict[str, str]] = {
    "default": {
        "name": "默认 JSON 模式",
        "description": "通用文档 OCR，适用于现代印刷品",
        "prompt": """OCR this document page and return structured JSON.

## Region Labels
**Main:** Section-Header, Text, List-Group, Table, Figure, Equation-Block
**Margins:** Footnote
**Structure:** Page-Header, Page-Footer, Caption
**Special:** Code-Block, Table-Of-Contents

## JSON Format
```json
{
  "printed_page_number": "5",
  "page_width": 1024,
  "page_height": 1448,
  "regions": [
    {
      "label": "Text",
      "bbox": [200, 190, 900, 350],
      "text": "Content here...",
      "confidence": 0.94
    }
  ]
}
```

## Rules
- **bbox:** [x0, y0, x1, y1] in pixels
- **text:** Use `**bold**`, `*italic*`, `^super^`, `~sub~`, `\\n` for breaks
- **confidence:** 0.9-1.0 (high), 0.7-0.9 (medium), 0.5-0.7 (low)
- **Granularity:** 5-30 semantic blocks per page
- **Marginal Notes:** Do not use Marginal-Note-Left or Marginal-Note-Right labels unless marginalia recognition is explicitly enabled
- **Output:** ONLY JSON, start with `{`, end with `}`"""
    },

    "historical": {
        "name": "古籍文献模式",
        "description": "保留历史连字符、繁体字、古文排版",
        "prompt": """OCR this historical document and return structured JSON. Preserve ALL historical features.

## CRITICAL
- Preserve ligatures: æ, œ, ſ (long s)
- Keep traditional characters: 繁體字
- DO NOT modernize spelling or characters
- Transcribe EXACTLY as printed

## Region Labels
**Main:** Section-Header, Text, List-Group, Table, Figure
**Margins:** Footnote
**Structure:** Page-Header, Page-Footer, Caption

## JSON Format
```json
{
  "printed_page_number": "5",
  "page_width": 1024,
  "page_height": 1448,
  "regions": [
    {
      "label": "Text",
      "bbox": [200, 190, 900, 350],
      "text": "Historical text with æ, œ, ſ...",
      "confidence": 0.94
    }
  ]
}
```

## Rules
- **bbox:** [x0, y0, x1, y1] in pixels
- **text:** Preserve ALL historical characters, use `\\n` for breaks
- **confidence:** 0.9-1.0 (high), 0.7-0.9 (medium), 0.5-0.7 (low)
- **Preserve:** Original spelling, archaic characters, ligatures
- **Output:** ONLY JSON, start with `{`, end with `}`"""
    },

    "chinese_vertical": {
        "name": "中文竖排模式",
        "description": "中文古籍、竖排文本识别",
        "prompt": """OCR this vertical Chinese document and return structured JSON.

## Text Direction
- Vertical text (right-to-left, top-to-bottom)
- Transcribe in reading order: rightmost column first

## Region Labels
**Main:** Section-Header, Text, List-Group, Table, Figure
**Margins:** Footnote
**Structure:** Page-Header, Page-Footer, Caption

## JSON Format
```json
{
  "printed_page_number": "5",
  "page_width": 1024,
  "page_height": 1448,
  "regions": [
    {
      "label": "Text",
      "bbox": [200, 190, 900, 350],
      "text": "中文竖排文本...",
      "confidence": 0.94
    }
  ]
}
```

## Rules
- **bbox:** [x0, y0, x1, y1] in pixels
- **text:** Use `\\n` for column breaks, preserve punctuation: 。，、；：「」『』
- **confidence:** 0.9-1.0 (high), 0.7-0.9 (medium), 0.5-0.7 (low)
- **Reading Order:** Right-to-left, top-to-bottom
- **Preserve:** Traditional characters, original punctuation
- **Output:** ONLY JSON, start with `{`, end with `}`"""
    },

    "handwriting": {
        "name": "手写识别模式",
        "description": "手写文档识别，尽量忠实转写且不添加不确定标记",
        "prompt": """OCR this handwritten document and return structured JSON.

## Handwriting Recognition
- Transcribe handwritten text as accurately as possible
- Preserve original writing style and spacing
- If a character cannot be read confidently, omit it or leave the field empty instead of inventing markers

## Region Labels
**Main:** Text, List-Group, Table, Figure
**Structure:** Page-Header, Page-Footer
**Special:** Signature, Stamp, Annotation

## JSON Format
```json
{
  "printed_page_number": null,
  "page_width": 1024,
  "page_height": 1448,
  "regions": [
    {
      "label": "Text",
      "bbox": [200, 190, 900, 350],
      "text": "Handwritten content...",
      "confidence": 0.75
    }
  ]
}
```

## Rules
- **bbox:** [x0, y0, x1, y1] in pixels
- **text:** Preserve visible content only, use `\\n` for line breaks
- **confidence:** Be conservative (0.5-0.8 typical for handwriting)
- **Preserve:** Line breaks, spacing, writing style
- **Do NOT:** Add emojis, commentary, or uncertainty markers such as [?], [不确定], [unknown]
- **Output:** ONLY JSON, start with `{`, end with `}`"""
    }
}
