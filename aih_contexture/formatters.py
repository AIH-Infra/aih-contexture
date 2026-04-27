"""
格式化工具

提供页码锚点等格式化功能，独立模块以避免循环导入。
"""

from typing import Optional, Callable


class PageAnchorFormatter:
    """
    页锚点格式化器（简化版）。

    固定使用 {n} 格式（0-based 页序），简化实现。
    印刷页码和自定义编号通过 <!-- Page: X --> 标记单独处理。
    """

    def __init__(self, wrapper: str = "{{{}}}"):
        """
        Args:
            wrapper: 锚点包装格式，默认 "{{{}}}}" 生成 {0}, {1}, {2} 格式
                     可自定义如 "[]", "<>" 等
        """
        self.wrapper = wrapper

    def format(self, page_index: int, printed_page_id: Optional[str] = None) -> str:
        """
        格式化页锚点（简化版）。

        Args:
            page_index: 0-based 页序（从 0 开始）
            printed_page_id: 保留参数以兼容旧代码，但不使用（页码通过 <!-- Page: X --> 标记处理）

        Returns:
            格式化后的锚点字符串

        Examples:
            >>> formatter = PageAnchorFormatter()
            >>> formatter.format(0)
            '{0}'
            >>> formatter.format(5)
            '{5}'
        """
        result = str(page_index)

        # 应用包装格式
        if self.wrapper:
            result = self.wrapper.format(result)

        return result


class PageAnchorPlugin:
    """
    页码锚点插件 - 可插拔的页码锚点处理器

    用于在不同的转换器中统一处理页码锚点的插入和格式化。
    """

    def __init__(self,
                 formatter: Optional[PageAnchorFormatter] = None,
                 enabled: bool = True,
                 position: str = "before",  # "before", "after", "both"
                 separator: str = "\n\n",
                 page_separator: str = "---",  # 页面分隔符（用于在锚点后插入）
                 custom_id_injector: Optional['CustomIDInjector'] = None):
        """
        Args:
            formatter: 页锚点格式化器，如果为 None 则使用默认
            enabled: 是否启用页码锚点
            position: 锚点位置 - "before"(页面前), "after"(页面后), "both"(两端)
            separator: 锚点与内容之间的分隔符
            page_separator: 页面分隔符（插入在锚点之后）
            custom_id_injector: 自定义编号注入器（可选）
        """
        self.formatter = formatter or PageAnchorFormatter()
        self.enabled = enabled
        self.position = position
        self.separator = separator
        self.page_separator = page_separator
        self.custom_id_injector = custom_id_injector

    def wrap_page_content(self, page_index: int, content: str,
                         printed_page_id: Optional[str] = None) -> str:
        """
        为页面内容添加锚点和页码标签。

        Args:
            page_index: 0-based 页序
            content: 页面内容
            printed_page_id: 印刷页码（可选）

        Returns:
            添加了锚点和页码标签的页面内容
        """
        if not self.enabled:
            return content

        # 生成双重页码锚点
        anchors = []

        # PDF物理页码（始终添加）
        pdf_anchor = self.formatter.format(page_index)
        anchors.append(pdf_anchor)

        # 印刷页码不再作为锚点输出，仅通过 <!-- Page: X --> 注释显示
        anchor_str = " ".join(anchors)

        # 生成 <!-- Page: X --> 标签（用于显示，保留兼容性）
        display_id = printed_page_id
        if not display_id and self.custom_id_injector:
            display_id = self.custom_id_injector.get_custom_id(page_index)

        page_tag = f"<!-- Page: {display_id} -->\n" if display_id else ""

        # 根据位置插入锚点和标签
        if self.position == "before":
            return f"{anchor_str}{self.separator}{page_tag}{content}"
        elif self.position == "after":
            return f"{content}{self.separator}{page_tag}{anchor_str}"
        elif self.position == "both":
            return f"{anchor_str}{self.separator}{page_tag}{content}{self.separator}{page_tag}{anchor_str}"
        else:
            return content

    def process_pages(self, pages: list,
                     printed_pages: Optional[list] = None) -> list:
        """
        批量处理多个页面，添加锚点。

        Args:
            pages: 页面内容列表
            printed_pages: 印刷页码列表（可选，长度应与 pages 相同）

        Returns:
            添加了锚点的页面列表
        """
        if not self.enabled:
            return pages

        printed_pages = printed_pages or [None] * len(pages)

        return [
            self.wrap_page_content(idx, content, printed_id)
            for idx, (content, printed_id) in enumerate(zip(pages, printed_pages))
        ]


class PrintedPageExtractor:
    """
    印刷页码提取器 - 从页面内容提取印刷页码

    策略：
    1. 优先从注释标记中提取（page-header/footer）
    2. 使用传入的正则模式（来自正则预设系统）
    3. 每页只提取一个
    """

    def __init__(self,
                 patterns: Optional[list] = None,
                 remove_from_content: bool = True,
                 search_lines: int = 5):
        """
        Args:
            patterns: 正则表达式模式列表（来自正则预设系统）
            remove_from_content: 是否从内容中移除识别到的页码
            search_lines: 搜索前/后几行（默认5行）
        """
        import re
        self.re = re
        self.remove_from_content = remove_from_content
        self.search_lines = search_lines
        self.patterns = patterns or []
        # 调试日志
        print(f"[PrintedPageExtractor] Initialized with {len(self.patterns)} patterns:")
        for i, p in enumerate(self.patterns):
            print(f"  [{i}] {p}")

    def extract(self, content: str) -> tuple[str, Optional[str]]:
        """
        从页面内容提取印刷页码

        完全使用传入的 patterns 参数，按顺序匹配。
        用户通过正则预设控制优先级。

        Args:
            content: 页面内容（Markdown）

        Returns:
            (处理后的内容, 印刷页码)
        """
        if not content:
            return content, None

        full_text = content

        # 按顺序尝试每个正则模式
        for pattern in self.patterns:
            try:
                match = self.re.search(pattern, full_text, self.re.IGNORECASE)
                if match:
                    page_num = match.group(1)
                    # SC 编号统一转大写
                    if page_num.upper().startswith('SC'):
                        page_num = page_num.upper()
                    # 验证页码有效性
                    if not self._is_valid_page_number(page_num):
                        continue
                    if self.remove_from_content:
                        content = self.re.sub(
                            pattern, '', content, count=1, flags=self.re.IGNORECASE
                        ).strip()
                    return content, page_num
            except self.re.error:
                continue

        return content, None

    def _is_valid_page_number(self, text: str) -> bool:
        """验证页码是否合理，过滤明显错误"""
        text = text.strip()
        if not text:
            return False

        # 阿拉伯数字: 1-999（过滤年份）
        if text.isdigit():
            num = int(text)
            # 过滤前导零（00, 01, 03）和年份（>999）
            if text.startswith('0') or num == 0 or num > 999:
                return False
            return True

        # 罗马数字: 1-6位，只允许 IVXLCDM
        # 单字母只允许 I, V, X（过滤 M, L, C, D 等 OCR 错误）
        if self.re.match(r'^[IVXLCDM]{1,6}$', text, self.re.IGNORECASE):
            if len(text) == 1 and text.upper() not in ['I', 'V', 'X']:
                return False
            return True

        # 中文页码（允许）
        if self.re.search(r'[一二三四五六七八九十百千零〇頁葉页叶]', text):
            return True

        # SC 编号等特殊格式（包含字母+数字）
        if self.re.match(r'^[A-Z]{1,3}[-\s]?\d{1,4}$', text, self.re.IGNORECASE):
            return True

        return False

    def extract_batch(self, contents: list) -> tuple[list, list]:
        """
        批量提取印刷页码。

        Args:
            contents: 页面内容列表

        Returns:
            (处理后的内容列表, 印刷页码列表)
        """
        processed_contents = []
        printed_pages = []

        for content in contents:
            processed_content, printed_page = self.extract(content)
            processed_contents.append(processed_content)
            printed_pages.append(printed_page)

        return processed_contents, printed_pages


class CustomIDInjector:
    """
    自定义编号注入器 - 提供自定义页面编号
    
    支持多种来源：
    - VLM 输出提取（不处理，由 VLM 直接输出）
    - 文件上传（CSV/JSON）
    - 手动输入列表
    - 自动生成
    - 无
    """
    
    def __init__(self, source_type: str = "none", source_data=None):
        """
        Args:
            source_type: "none" | "vlm" | "file" | "list" | "auto"
            source_data: 根据 source_type 提供相应数据
        """
        self.source_type = source_type
        self.custom_ids = self._load_custom_ids(source_data)
    
    def _load_custom_ids(self, source_data) -> dict:
        """从不同来源加载自定义编号"""
        if self.source_type == "none" or self.source_type == "vlm":
            return {}
        elif self.source_type == "file":
            return self._parse_file(source_data)
        elif self.source_type == "list":
            return self._parse_list(source_data)
        elif self.source_type == "auto":
            return self._generate_ids(source_data)
        return {}
    
    def _parse_file(self, file_content: str) -> dict:
        """解析 CSV 或 JSON 文件"""
        import json
        import csv
        import io
        
        if not file_content:
            return {}
        
        try:
            # 尝试 JSON
            data = json.loads(file_content)
            # 确保键是整数
            return {int(k): str(v) for k, v in data.items()}
        except:
            pass
        
        try:
            # 尝试 CSV
            reader = csv.DictReader(io.StringIO(file_content))
            return {int(row['page_index']): row['custom_id'] for row in reader}
        except:
            return {}
    
    def _parse_list(self, input_data) -> dict:
        """解析列表（支持字符串或列表）"""
        if not input_data:
            return {}

        # 如果已经是列表，直接使用
        if isinstance(input_data, list):
            ids = [str(x).strip() for x in input_data if x]
        # 如果是字符串，按逗号分隔
        elif isinstance(input_data, str):
            ids = [x.strip() for x in input_data.split(',') if x.strip()]
        else:
            return {}

        return {idx: id for idx, id in enumerate(ids) if id}
    
    def _generate_ids(self, config: dict) -> dict:
        """自动生成编号"""
        if not config:
            return {}

        prefix = config.get('prefix', 'page')
        start = config.get('start', 1)
        digits = config.get('digits', 3)  # 使用 digits 而不是 padding
        count = config.get('count', 1000)  # 默认生成1000个
        separator = config.get('separator', '')  # 🆕 分隔符（如空格）

        return {
            idx: f"{prefix}{separator}{str(start + idx).zfill(digits)}"
            for idx in range(count)
        }
    
    def get_custom_id(self, page_index: int):
        """获取指定页面的自定义编号"""
        return self.custom_ids.get(page_index, None)
