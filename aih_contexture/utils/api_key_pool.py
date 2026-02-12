"""
API Key Pool - 管理多个API Key的并发使用

特性:
- 支持多个Key的并发分配
- Round-robin负载均衡
- 失败Key的临时禁用机制
- 线程安全
"""

import threading
import time
from typing import List, Dict


class APIKeyPool:
    """
    API Key池 - 用于并发场景下的Key管理

    与APIKeyRotator的区别:
    - APIKeyRotator: 失败时切换Key (串行容错)
    - APIKeyPool: 并发时分配Key (并行负载均衡)

    使用场景:
    - 多个任务需要同时使用不同的Key
    - 提高并发吞吐量，突破单Key限流

    Example:
        >>> pool = APIKeyPool("sk-key1,sk-key2,sk-key3")
        >>> key1 = pool.acquire()  # 获取Key1
        >>> key2 = pool.acquire()  # 获取Key2
        >>> pool.mark_failure(key1, cooldown=60)  # Key1失败，禁用60秒
        >>> key3 = pool.acquire()  # 跳过Key1，获取Key3
    """

    def __init__(self, keys: str | List[str], default_cooldown: int = 60):
        """
        初始化Key池

        Args:
            keys: API Key字符串(逗号或换行分隔)或Key列表
            default_cooldown: 失败Key的默认冷却时间(秒)
        """
        self.keys = self._parse_keys(keys)
        self.default_cooldown = default_cooldown

        # Round-robin索引
        self.current_index = 0

        # 禁用的Key及其恢复时间 {key: retry_after_timestamp}
        self.disabled_keys: Dict[str, float] = {}

        # 线程锁
        self._lock = threading.Lock()

        if not self.keys:
            raise ValueError("At least one API key is required")

    def _parse_keys(self, keys: str | List[str]) -> List[str]:
        """解析Key字符串或列表"""
        if isinstance(keys, list):
            return [k.strip() for k in keys if k and k.strip()]

        if not isinstance(keys, str):
            return []

        # 尝试按逗号分隔
        if ',' in keys:
            parsed = [k.strip() for k in keys.split(',') if k.strip()]
            if parsed:
                return parsed

        # 尝试按换行分隔
        if '\n' in keys:
            parsed = [k.strip() for k in keys.split('\n') if k.strip()]
            if parsed:
                return parsed

        # 单个Key
        key = keys.strip()
        return [key] if key else []

    def _cleanup_disabled(self):
        """清理已过期的禁用Key (需要在锁内调用)"""
        current_time = time.time()
        expired_keys = [
            key for key, retry_after in self.disabled_keys.items()
            if current_time >= retry_after
        ]
        for key in expired_keys:
            del self.disabled_keys[key]

    def acquire(self) -> str:
        """
        获取一个可用的Key

        使用round-robin策略，自动跳过被禁用的Key

        Returns:
            可用的API Key

        Raises:
            RuntimeError: 如果所有Key都被禁用
        """
        with self._lock:
            # 清理过期的禁用Key
            self._cleanup_disabled()

            # 如果所有Key都被禁用
            if len(self.disabled_keys) >= len(self.keys):
                # 找到最早恢复的Key
                earliest_key = min(
                    self.disabled_keys.items(),
                    key=lambda x: x[1]
                )[0]
                # 强制使用它（虽然还在冷却期）
                return earliest_key

            # Round-robin查找可用Key
            attempts = 0
            while attempts < len(self.keys):
                key = self.keys[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.keys)

                # 如果Key未被禁用，返回
                if key not in self.disabled_keys:
                    return key

                attempts += 1

            # 理论上不会到这里（上面已经处理了全部禁用的情况）
            return self.keys[0]

    def mark_failure(self, key: str, cooldown: int = None):
        """
        标记Key失败，临时禁用

        Args:
            key: 失败的API Key
            cooldown: 冷却时间(秒)，None则使用default_cooldown
        """
        if cooldown is None:
            cooldown = self.default_cooldown

        with self._lock:
            retry_after = time.time() + cooldown
            self.disabled_keys[key] = retry_after

    def mark_success(self, key: str):
        """
        标记Key成功，如果之前被禁用则恢复

        Args:
            key: 成功的API Key
        """
        with self._lock:
            if key in self.disabled_keys:
                del self.disabled_keys[key]

    def get_key_count(self) -> int:
        """获取总Key数量"""
        return len(self.keys)

    def get_available_count(self) -> int:
        """获取当前可用的Key数量"""
        with self._lock:
            self._cleanup_disabled()
            return len(self.keys) - len(self.disabled_keys)

    def get_status(self) -> Dict:
        """
        获取Key池状态

        Returns:
            状态字典，包含总数、可用数、禁用列表等
        """
        with self._lock:
            self._cleanup_disabled()
            return {
                "total": len(self.keys),
                "available": len(self.keys) - len(self.disabled_keys),
                "disabled": len(self.disabled_keys),
                "disabled_keys": list(self.disabled_keys.keys())
            }
