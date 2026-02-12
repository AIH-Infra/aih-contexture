"""
API Key 轮换器

支持配置多个API Key,失败时自动切换到下一个Key。
"""

from typing import List, Optional
import threading


class APIKeyRotator:
    """
    API Key 轮换器

    特性:
    - 支持多个API Key
    - 失败时自动切换到下一个Key
    - 线程安全
    - 向后兼容(单Key时行为不变)
    """

    def __init__(self, api_keys: str | List[str]):
        """
        初始化Key轮换器

        Args:
            api_keys: API Key字符串(逗号分隔)或Key列表
        """
        # 解析API Keys
        if isinstance(api_keys, str):
            # 支持逗号分隔的多个Key
            self.keys = [k.strip() for k in api_keys.split(',') if k.strip()]
        else:
            self.keys = [k for k in api_keys if k]

        if not self.keys:
            self.keys = [""]  # 至少有一个空Key

        self.current_index = 0
        self.failure_counts = {key: 0 for key in self.keys}
        self._lock = threading.Lock()

    def get_current_key(self) -> str:
        """获取当前使用的Key"""
        with self._lock:
            return self.keys[self.current_index]

    def mark_failure_and_rotate(self) -> str:
        """
        标记当前Key失败,并切换到下一个Key

        Returns:
            下一个要使用的Key
        """
        with self._lock:
            # 记录失败
            current_key = self.keys[self.current_index]
            self.failure_counts[current_key] += 1

            # 切换到下一个Key
            self.current_index = (self.current_index + 1) % len(self.keys)
            next_key = self.keys[self.current_index]

            return next_key

    def mark_success(self):
        """标记当前Key成功(可选,用于统计)"""
        # 成功后不需要特殊处理,保持当前Key
        pass

    def get_key_count(self) -> int:
        """获取Key数量"""
        return len(self.keys)

    def get_failure_counts(self) -> dict:
        """获取各Key的失败次数"""
        with self._lock:
            return self.failure_counts.copy()

    @staticmethod
    def parse_keys(api_keys: str | List[str]) -> List[str]:
        """
        解析API Keys

        Args:
            api_keys: API Key字符串(逗号分隔)或Key列表

        Returns:
            Key列表
        """
        if isinstance(api_keys, str):
            return [k.strip() for k in api_keys.split(',') if k.strip()]
        else:
            return [k for k in api_keys if k]
