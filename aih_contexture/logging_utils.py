"""统一的日志工具和模板"""
from pathlib import Path
from aih_contexture.logger import get_logger

logger = get_logger()


class LogTemplate:
    """标准日志模板 - 只输出INFO级别的关键信息"""

    @staticmethod
    def job_start(job_id: str, filepath: str, mode: str, **kwargs):
        """作业启动摘要"""
        logger.info(f"[Job.{job_id}] START file={Path(filepath).name} mode={mode}")
        for key, value in kwargs.items():
            logger.info(f"[Job.{job_id}]   {key}={value}")

    @staticmethod
    def job_complete(job_id: str, elapsed: float, pages: int, output_size: int):
        """作业完成摘要"""
        speed = pages / elapsed if elapsed > 0 else 0
        logger.info(
            f"[Job.{job_id}] DONE elapsed={elapsed:.1f}s pages={pages} "
            f"speed={speed:.2f}p/s size={output_size}"
        )

    @staticmethod
    def progress(job_id: str, phase: str, current: int, total: int, unit: str = "pages"):
        """进度报告（粗粒度：每10页或每批次）"""
        pct = (current / total * 100) if total > 0 else 0
        logger.info(f"[Job.{job_id}] {phase}: {current}/{total} {unit} ({pct:.0f}%)")

    @staticmethod
    def batch_progress(job_id: str, batch_num: int, total_batches: int, batch_size: int):
        """批次进度"""
        logger.info(
            f"[Job.{job_id}] Batch {batch_num}/{total_batches} ({batch_size} pages)"
        )
