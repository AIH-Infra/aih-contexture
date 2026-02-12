
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
    
    def _parse_list(self, input_str: str) -> dict:
        """解析逗号分隔的列表"""
        if not input_str:
            return {}
        
        ids = [x.strip() for x in input_str.split(',')]
        return {idx: id for idx, id in enumerate(ids) if id}
    
    def _generate_ids(self, config: dict) -> dict:
        """自动生成编号"""
        if not config:
            return {}
        
        prefix = config.get('prefix', 'page')
        start = config.get('start', 1)
        padding = config.get('padding', 3)
        count = config.get('count', 1000)  # 默认生成1000个
        
        return {
            idx: f"{prefix}{str(start + idx).zfill(padding)}"
            for idx in range(count)
        }
    
    def get_custom_id(self, page_index: int) -> Optional[str]:
        """获取指定页面的自定义编号"""
        return self.custom_ids.get(page_index, None)
