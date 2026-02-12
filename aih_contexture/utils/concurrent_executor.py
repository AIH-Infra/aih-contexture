"""
Ordered Concurrent Executor - 有序并发执行器

特性:
- 支持异步(asyncio)和同步(ThreadPoolExecutor)两种模式
- 自动从KeyPool获取Key并分配给任务
- 保证返回结果的顺序与输入顺序一致
- 进度显示支持
- 错误处理和重试机制
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Any, Optional, Tuple
from tqdm import tqdm

from aih_contexture.logger import get_logger
from aih_contexture.utils.api_key_pool import APIKeyPool

logger = get_logger()


class OrderedConcurrentExecutor:
    """
    有序并发执行器

    核心功能:
    1. 从KeyPool获取Key并分配给任务
    2. 并发执行任务
    3. 保证返回结果的顺序

    Example (Async):
        >>> pool = APIKeyPool("sk-key1,sk-key2,sk-key3")
        >>> executor = OrderedConcurrentExecutor(pool, max_concurrent=6)
        >>>
        >>> async def task(api_key, page_num):
        >>>     # 使用api_key处理page_num
        >>>     return f"Page {page_num} processed with {api_key}"
        >>>
        >>> tasks = [lambda key: task(key, i) for i in range(10)]
        >>> results = await executor.execute_async(tasks)
        >>> # results保证按照0-9的顺序

    Example (Sync):
        >>> pool = APIKeyPool("sk-key1,sk-key2,sk-key3")
        >>> executor = OrderedConcurrentExecutor(pool, max_concurrent=6)
        >>>
        >>> def task(api_key, block_id):
        >>>     # 使用api_key处理block_id
        >>>     return f"Block {block_id} processed"
        >>>
        >>> tasks = [lambda key: task(key, i) for i in range(10)]
        >>> results = executor.execute_sync(tasks)
        >>> # results保证按照0-9的顺序
    """

    def __init__(
        self,
        key_pool: APIKeyPool,
        max_concurrent: int,
        retry_on_failure: bool = True,
        max_retries: int = 2
    ):
        """
        初始化执行器

        Args:
            key_pool: API Key池
            max_concurrent: 最大并发数
            retry_on_failure: 失败时是否重试
            max_retries: 最大重试次数
        """
        self.key_pool = key_pool
        self.max_concurrent = max_concurrent
        self.retry_on_failure = retry_on_failure
        self.max_retries = max_retries

    async def execute_async(
        self,
        tasks: List[Callable[[str], Any]],
        preserve_order: bool = True,
        desc: str = "Processing",
        disable_progress: bool = False
    ) -> List[Any]:
        """
        异步执行任务列表

        Args:
            tasks: 任务列表，每个任务是一个接受api_key参数的async函数
            preserve_order: 是否保证返回顺序
            desc: 进度条描述
            disable_progress: 是否禁用进度条

        Returns:
            结果列表，如果preserve_order=True则顺序与输入一致
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _execute_with_index(index: int, task: Callable) -> Tuple[int, Any]:
            """执行单个任务，带索引和重试"""
            async with semaphore:
                last_error = None

                for attempt in range(self.max_retries + 1):
                    # 从Key池获取Key
                    api_key = self.key_pool.acquire()

                    try:
                        # 执行任务
                        result = await task(api_key)

                        # 标记Key成功
                        self.key_pool.mark_success(api_key)

                        return (index, result)

                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"[OrderedConcurrentExecutor] Task {index} failed with key "
                            f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                        )

                        # 标记Key失败
                        self.key_pool.mark_failure(api_key)

                        # 如果还有重试机会，继续
                        if attempt < self.max_retries and self.retry_on_failure:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue
                        else:
                            # 重试耗尽，返回None或抛出异常
                            logger.error(
                                f"[OrderedConcurrentExecutor] Task {index} failed after "
                                f"{self.max_retries + 1} attempts: {last_error}"
                            )
                            return (index, None)

                return (index, None)

        # 创建所有任务
        coroutines = [_execute_with_index(i, task) for i, task in enumerate(tasks)]

        # 使用tqdm显示进度
        if not disable_progress:
            results = []
            for coro in tqdm(
                asyncio.as_completed(coroutines),
                total=len(tasks),
                desc=desc
            ):
                result = await coro
                results.append(result)
        else:
            results = await asyncio.gather(*coroutines)

        # 保证顺序
        if preserve_order:
            results.sort(key=lambda x: x[0])

        # 返回结果（去掉index）
        return [r[1] for r in results]

    def execute_sync(
        self,
        tasks: List[Callable[[str], Any]],
        preserve_order: bool = True,
        desc: str = "Processing",
        disable_progress: bool = False
    ) -> List[Any]:
        """
        同步执行任务列表（使用ThreadPoolExecutor）

        Args:
            tasks: 任务列表，每个任务是一个接受api_key参数的函数
            preserve_order: 是否保证返回顺序
            desc: 进度条描述
            disable_progress: 是否禁用进度条

        Returns:
            结果列表，如果preserve_order=True则顺序与输入一致
        """

        def _execute_with_index(index: int, task: Callable) -> Tuple[int, Any]:
            """执行单个任务，带索引和重试"""
            last_error = None

            for attempt in range(self.max_retries + 1):
                # 从Key池获取Key
                api_key = self.key_pool.acquire()

                try:
                    # 执行任务
                    result = task(api_key)

                    # 标记Key成功
                    self.key_pool.mark_success(api_key)

                    return (index, result)

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"[OrderedConcurrentExecutor] Task {index} failed with key "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                    )

                    # 标记Key失败
                    self.key_pool.mark_failure(api_key)

                    # 如果还有重试机会，继续
                    if attempt < self.max_retries and self.retry_on_failure:
                        import time
                        time.sleep(1 * (attempt + 1))
                        continue
                    else:
                        # 重试耗尽，返回None
                        logger.error(
                            f"[OrderedConcurrentExecutor] Task {index} failed after "
                            f"{self.max_retries + 1} attempts: {last_error}"
                        )
                        return (index, None)

            return (index, None)

        # 使用ThreadPoolExecutor执行
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            # 提交所有任务
            futures = [
                executor.submit(_execute_with_index, i, task)
                for i, task in enumerate(tasks)
            ]

            # 收集结果（带进度条）
            results = []
            if not disable_progress:
                for future in tqdm(
                    as_completed(futures),
                    total=len(tasks),
                    desc=desc
                ):
                    results.append(future.result())
            else:
                results = [f.result() for f in futures]

        # 保证顺序
        if preserve_order:
            results.sort(key=lambda x: x[0])

        # 返回结果（去掉index）
        return [r[1] for r in results]
