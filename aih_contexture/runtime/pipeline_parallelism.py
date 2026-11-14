"""Pipeline performance plan: worker processes and pages per batch from free memory.

The UI (recommendation) and the pipeline worker (final check) both call
``resolve_pipeline_parallelism`` so they cannot disagree. Each worker process
loads its own model copy, so VRAM decides how many workers fit; pages per batch
only changes host RAM, because the GPU sees ``layout_batch_size`` pages at a time.

Profiles are measured whole-process footprints (CUDA context, every model the
Pipeline loads, allocator cache), not ``torch.cuda.max_memory_allocated``.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

AUTO = "auto"
MANUAL = "manual"
MAX_WORKERS = 8
# Measured optimum on RTX 5060 Ti: parallel workers interleave GPU and CPU
# phases best with small batches; a single worker gains ~7% from 100 pages.
PARALLEL_PAGES_PER_BATCH = 25
SINGLE_PAGES_PER_BATCH = 100
MIN_PAGES_PER_BATCH = 10
AUTO_MIN_PAGES_PER_WORKER = 50
RAM_RESERVE_GB = 4.0
VRAM_RESERVE_GB = 0.5
VRAM_RESERVE_FRACTION = 0.03


@dataclass(frozen=True, slots=True)
class WorkerProfile:
    """Per-process footprint of one Pipeline worker for a layout backend."""

    vram_base_gb: float
    vram_per_layout_item_gb: float
    default_layout_batch_size: int
    # Beyond this the shared GPU (Surya) or CPU stages stop scaling.
    useful_workers: int
    ram_base_gb: float = 3.0
    ram_per_page_gb: float = 0.02
    quality_extra_gb: tuple[tuple[str, float], ...] = ()

    def vram_gb(self, layout_batch_size: int | None, quality: str | None = None) -> float:
        items = int(layout_batch_size or self.default_layout_batch_size)
        extra = dict(self.quality_extra_gb).get(str(quality or "").strip().lower(), 0.0)
        return self.vram_base_gb + self.vram_per_layout_item_gb * max(1, items) + extra

    def ram_gb(self, pages_per_batch: int) -> float:
        return self.ram_base_gb + self.ram_per_page_gb * max(1, pages_per_batch)


# Measured on RTX 5060 Ti 16 GB (2026-10-23), nvidia-smi delta per worker over
# whole books. Text-layer OCR only (``ocr_backend == "none"``); OCR models
# change the footprint. Surya: 4.5/5.2/6.4 GB at layout batch 4/8/16 on short
# runs, 5.6 GB per worker with two in parallel over 304 pages; 192 DPI adds 1.2 GB.
WORKER_PROFILES: dict[str, WorkerProfile] = {
    "surya": WorkerProfile(
        vram_base_gb=4.4, vram_per_layout_item_gb=0.15, default_layout_batch_size=8, useful_workers=3,
        quality_extra_gb=(("standard", 0.6), ("high", 1.2)),
    ),
    # PP-DocLayoutV2 sidecar plus the Pipeline process: 2.7/3.4/4.6 GB at batch 1/4/8.
    "mineru_pp_doclayout_v2_direct": WorkerProfile(
        vram_base_gb=2.6, vram_per_layout_item_gb=0.25, default_layout_batch_size=4, useful_workers=4,
    ),
}
LIMIT_LABELS = {"vram": "显存", "ram": "内存", "cpu": "CPU", "batches": "批次数", "useful": "收益上限", "pages": "页数", "small_job": "页数过少"}


@dataclass(frozen=True, slots=True)
class MemoryProbe:
    device: str | None
    vram_free_gb: float | None
    vram_total_gb: float | None
    ram_available_gb: float | None
    cpu_count: int
    source: str = "none"


@dataclass(slots=True)
class ParallelPlan:
    mode: str
    workers: int
    pages_per_batch: int
    batch_threshold: int
    worker_vram_gb: float | None
    worker_ram_gb: float
    limits: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    probe: MemoryProbe | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_backend(name: Any) -> str:
    return str(name or "").strip().lower().replace("-", "_")


def worker_profile(layout_backend: Any, ocr_backend: Any = "none") -> WorkerProfile | None:
    if normalize_backend(ocr_backend) not in ("", "none", "pdftext"):
        return None
    return WORKER_PROFILES.get(normalize_backend(layout_backend))


def layout_batch_size_for(values: dict[str, Any]) -> int | None:
    backend = normalize_backend(values.get("layout_backend"))
    key = "mineru_layout_batch_size" if backend == "mineru_pp_doclayout_v2_direct" else "layout_batch_size"
    value = values.get(key)
    return int(value) if value not in (None, "", 0) else None


def resolve_pipeline_parallelism(
    *,
    layout_backend: Any,
    ocr_backend: Any = "none",
    layout_batch_size: int | None = None,
    layout_quality: str | None = None,
    mode: str = AUTO,
    workers: int | None = None,
    pages_per_batch: int | None = None,
    batch_threshold: int | None = None,
    total_pages: int | None = None,
    probe: MemoryProbe | None = None,
) -> ParallelPlan:
    """Return a safe worker count and batch size.

    Auto picks both; manual keeps the user's values but never exceeds what
    free VRAM and RAM can hold, because an over-committed Windows GPU spills
    into shared memory and stalls instead of failing.
    """
    mode = MANUAL if str(mode).strip().lower() == MANUAL else AUTO
    probe = probe if probe is not None else probe_memory()
    profile = worker_profile(layout_backend, ocr_backend)
    notes: list[str] = []
    limits: dict[str, int] = {}

    if mode == MANUAL:
        limits["requested"] = max(1, min(MAX_WORKERS, int(workers or 1)))
        pages = max(1, int(pages_per_batch or PARALLEL_PAGES_PER_BATCH))
    elif profile is None:
        limits["profile"] = 1
        notes.append("当前后端组合没有实测显存档案，自动配置保持单进程。")
        pages = SINGLE_PAGES_PER_BATCH
    else:
        limits["useful"] = profile.useful_workers
        pages = PARALLEL_PAGES_PER_BATCH

    worker_vram = profile.vram_gb(layout_batch_size, layout_quality) if profile else None
    if worker_vram is not None:
        if probe.vram_free_gb is None:
            limits["vram"] = 1
            notes.append("未检测到 GPU 可用显存，按单进程运行。")
        else:
            reserve = VRAM_RESERVE_GB + VRAM_RESERVE_FRACTION * float(probe.vram_total_gb or probe.vram_free_gb)
            limits["vram"] = max(1, int((probe.vram_free_gb - reserve) // worker_vram))
    elif mode == MANUAL and limits["requested"] > 1:
        notes.append("当前后端组合没有实测显存档案，按手动进程数运行，请留意显存。")
    limits["cpu"] = max(1, probe.cpu_count // 4)
    if total_pages and mode == AUTO:
        # Model loading per worker only pays off with enough pages each.
        limits["pages"] = max(1, int(total_pages) // AUTO_MIN_PAGES_PER_WORKER)

    def ram_per_worker(page_count: int) -> float:
        return profile.ram_gb(page_count) if profile else 3.0 + 0.02 * page_count

    if probe.ram_available_gb is not None:
        limits["ram"] = max(1, int((probe.ram_available_gb - RAM_RESERVE_GB) // ram_per_worker(pages)))
    chosen = min(limits.values())

    if mode == AUTO and chosen == 1:
        # One worker: larger batches cut per-batch overhead, if RAM allows.
        fits = probe.ram_available_gb is None or probe.ram_available_gb - RAM_RESERVE_GB >= ram_per_worker(SINGLE_PAGES_PER_BATCH)
        pages = SINGLE_PAGES_PER_BATCH if fits else PARALLEL_PAGES_PER_BATCH
    if total_pages:
        if mode == AUTO and chosen > 1:
            # At least two batches per worker keeps the shared queue balanced.
            pages = max(MIN_PAGES_PER_BATCH, min(pages, math.ceil(int(total_pages) / (chosen * 2))))
        limits["batches"] = max(1, math.ceil(int(total_pages) / pages))
        chosen = min(chosen, limits["batches"])

    if mode == MANUAL and chosen < limits["requested"]:
        binding = sorted(LIMIT_LABELS.get(key, key) for key, value in limits.items() if value == chosen and key != "requested")
        notes.append(f"手动设置 {limits['requested']} 个进程超出安全上限，已限制为 {chosen}（受限于：{'、'.join(binding)}）。")
    threshold = pages if mode == AUTO else int(batch_threshold or pages)
    return ParallelPlan(
        mode=mode, workers=chosen, pages_per_batch=pages, batch_threshold=threshold,
        worker_vram_gb=round(worker_vram, 2) if worker_vram is not None else None,
        worker_ram_gb=round(ram_per_worker(pages), 2), limits=limits, notes=notes, probe=probe,
    )


def plan_from_values(
    values: dict[str, Any], *, total_pages: int | None = None, probe: MemoryProbe | None = None,
) -> ParallelPlan:
    """Map Pipeline UI/config values onto the resolver; shared by UI and runner."""
    ocr_backend = values.get("ocr_backend")
    if str(values.get("ocr_preprocess_backend") or "none") not in ("", "none"):
        ocr_backend = "none"
    return resolve_pipeline_parallelism(
        layout_backend=values.get("layout_backend", "surya"),
        ocr_backend=ocr_backend,
        layout_batch_size=layout_batch_size_for(values),
        layout_quality=values.get("surya_layout_quality"),
        mode=values.get("pipeline_performance_mode") or AUTO,
        workers=values.get("pipeline_workers"),
        pages_per_batch=values.get("pages_per_batch"),
        batch_threshold=values.get("batch_threshold"),
        total_pages=total_pages,
        probe=probe,
    )


# Indra OCR (CPU) is planned in cores, not VRAM. Its own source says a single ONNX Runtime thread pool helps one page
# only a little, so with enough pages the best use is one single-thread process per core; with fewer than
# INDRA_MIN_POOL_PAGES one process uses the cores on each page. 1.5 GB per worker is Indra's own budget constant
# (indra_ocr.parallel.WORKER_MEMORY), not a measurement of ours; large scans can need more.
INDRA_WORKER_RAM_GB = 1.5
INDRA_MIN_POOL_PAGES = 4
INDRA_SINGLE_PROCESS_THREADS = 4
INDRA_RESERVED_CORES = 2
INDRA_MIN_PAGES_PER_WORKER = 2
# Measured on a 24-core machine with 135 scanned pages: 4 workers 4.8 pages/s, 8 -> 6.9, 12 -> 7.7, 16 -> 7.9, 22 -> 7.2.
# More workers stop paying off around 12; a manual setting may go past this, the automatic plan does not.
INDRA_USEFUL_WORKERS = 12


def _physical_cores(probe: MemoryProbe) -> int:
    try:
        import psutil

        return int(psutil.cpu_count(logical=False) or probe.cpu_count)
    except ImportError:
        return probe.cpu_count


def plan_indra_workers(
    config: dict[str, Any], *, total_pages: int | None = None, probe: MemoryProbe | None = None,
) -> ParallelPlan:
    """Cores for an Indra run: automatic from cores, free RAM and page count, or the user's ``indra_cores``.

    A manual value is honoured up to what free RAM and the machine can hold, never silently beyond it.
    """
    probe = probe if probe is not None else probe_memory()
    requested = config.get("indra_cores")
    if requested in (None, "", 0) and str(config.get("pipeline_performance_mode") or AUTO).strip().lower() == MANUAL:
        requested = config.get("pipeline_workers")
    manual = requested not in (None, "", 0)
    pages = max(1, int(total_pages or 1))
    physical = _physical_cores(probe)
    limits: dict[str, int] = {"cpu": max(1, physical - INDRA_RESERVED_CORES if physical > INDRA_RESERVED_CORES + 1 else physical)}
    notes: list[str] = []
    if probe.ram_available_gb is not None:
        limits["ram"] = max(1, int((probe.ram_available_gb - RAM_RESERVE_GB) // INDRA_WORKER_RAM_GB))
    if manual:
        limits["requested"] = max(1, int(requested))
    elif pages < INDRA_MIN_POOL_PAGES:
        limits["small_job"] = INDRA_SINGLE_PROCESS_THREADS
    else:
        limits["pages"] = max(1, pages // INDRA_MIN_PAGES_PER_WORKER)
        limits["useful"] = INDRA_USEFUL_WORKERS
    chosen = min(limits.values())
    if manual and chosen < limits["requested"]:
        binding = sorted(LIMIT_LABELS.get(key, key) for key, value in limits.items() if value == chosen and key != "requested")
        notes.append(f"手动设置 {limits['requested']} 个核心超出安全上限，已限制为 {chosen}（受限于：{'、'.join(binding)}）。")
    if not manual and pages < INDRA_MIN_POOL_PAGES:
        notes.append("页数少于 4：单进程，多核同时处理每一页。")
    return ParallelPlan(
        mode=MANUAL if manual else AUTO, workers=chosen, pages_per_batch=pages, batch_threshold=pages,
        worker_vram_gb=None, worker_ram_gb=INDRA_WORKER_RAM_GB, limits=limits, notes=notes, probe=probe,
    )


_PROBE_CACHE: tuple[float, MemoryProbe] | None = None
_PROBE_TTL_SECONDS = 20.0


def probe_memory(*, use_cache: bool = True, runner: Callable[..., Any] = subprocess.run) -> MemoryProbe:
    """Free VRAM without creating a CUDA context in this process."""
    global _PROBE_CACHE
    now = time.monotonic()
    if use_cache and _PROBE_CACHE and now - _PROBE_CACHE[0] < _PROBE_TTL_SECONDS:
        return _PROBE_CACHE[1]
    device = free = total = None
    source = "none"
    nvidia = _probe_nvidia_smi(runner)
    if nvidia is not None:
        device, free, total = nvidia
        source = "nvidia-smi"
    else:
        torch_probe = _probe_torch_subprocess(runner)
        if torch_probe is not None:
            device, free, total = torch_probe
            source = "torch"
    probe = MemoryProbe(
        device=device, vram_free_gb=free, vram_total_gb=total,
        ram_available_gb=_ram_available_gb(), cpu_count=os.cpu_count() or 1, source=source,
    )
    _PROBE_CACHE = (now, probe)
    return probe


def _probe_nvidia_smi(runner: Callable[..., Any]) -> tuple[str, float, float] | None:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        completed = runner(
            ["nvidia-smi", "--query-gpu=name,memory.free,memory.total", "--format=csv,noheader,nounits", "-i",
             os.environ.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0] or "0"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        name, free_mb, total_mb = [part.strip() for part in completed.stdout.strip().splitlines()[0].split(",")]
        return name, int(free_mb) / 1024, int(total_mb) / 1024
    except Exception:  # noqa: BLE001 - absent or failing tool means "unknown".
        return None


_TORCH_PROBE = (
    "import torch\n"
    "if torch.cuda.is_available():\n"
    "    f, t = torch.cuda.mem_get_info()\n"
    "    print(torch.cuda.get_device_name(0) + '|' + str(f) + '|' + str(t))\n"
)


def _probe_torch_subprocess(runner: Callable[..., Any]) -> tuple[str, float, float] | None:
    # ROCm and other devices: ask torch in a child so this process stays context-free.
    try:
        completed = runner([sys.executable, "-c", _TORCH_PROBE], capture_output=True, text=True, timeout=60, check=True)
        name, free, total = completed.stdout.strip().splitlines()[-1].rsplit("|", 2)
        return name, int(free) / 2**30, int(total) / 2**30
    except Exception:  # noqa: BLE001
        return None


def _ram_available_gb() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    return psutil.virtual_memory().available / 2**30


def describe_plan(plan: ParallelPlan) -> str:
    probe = plan.probe
    parts = []
    if probe and probe.vram_free_gb is not None:
        parts.append(f"{probe.device or 'GPU'} 可用显存 {probe.vram_free_gb:.1f}/{probe.vram_total_gb:.1f} GB")
    if probe and probe.ram_available_gb is not None:
        parts.append(f"可用内存 {probe.ram_available_gb:.1f} GB")
    head = f"{plan.workers} 个并行进程 × 每批 {plan.pages_per_batch} 页"
    if plan.worker_vram_gb is not None:
        head += f"（每进程约 {plan.worker_vram_gb:.1f} GB 显存）"
    return head + ("；" + "，".join(parts) if parts else "")
