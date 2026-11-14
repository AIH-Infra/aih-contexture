"""Low-level interface to the screen-ai shared library.

Handles library discovery, model-file callbacks, SkBitmap struct layout,
and the raw ``PerformOCR`` call.  Everything here is an implementation
detail -- the public API lives in :mod:`locro.ocr`.

See ``CHROME_SCREEN_AI_DLL.md`` for how the struct layout was determined.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from pathlib import Path

from ._platform import LIB_NAME, chrome_component_bases

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chromium stub symbols (Linux only)
# ---------------------------------------------------------------------------
# libchromescreenai.so references a handful of Chromium-internal symbols
# (zlib stubs, threadlogger) that don't exist on the host system.  They are
# never called during normal OCR, but the dynamic linker needs them resolved.
# We compile a tiny .so that exports them and preload it with RTLD_GLOBAL.

_STUBS_SOURCE = """\
#include <stddef.h>
void *unsupported_gzopen(const char *path, const char *mode) { return NULL; }
int unsupported_gzread(void *file, void *buf, unsigned len) { return 0; }
int unsupported_gzclose(void *file) { return 0; }
void _ZN12threadlogger21EnableThreadedLoggingEi(int x) {}
"""

_STUBS_NAME = "_chromium_stubs.so"
_stubs_loaded = False


def _ensure_stubs(model_dir: Path) -> None:
    """Compile (once) and preload the Chromium stub symbols on Linux."""
    global _stubs_loaded
    if _stubs_loaded or sys.platform != "linux":
        return

    stubs_path = model_dir / _STUBS_NAME
    if not stubs_path.exists():
        log.info("Compiling Chromium stubs -> %s", stubs_path)
        subprocess.run(
            ["cc", "-shared", "-fPIC", "-o", str(stubs_path), "-x", "c", "-"],
            input=_STUBS_SOURCE.encode(),
            check=True,
        )

    log.debug("Preloading %s", stubs_path)
    ctypes.CDLL(str(stubs_path), mode=os.RTLD_LAZY | ctypes.RTLD_GLOBAL)
    _stubs_loaded = True


# ---------------------------------------------------------------------------
# Suppress native library chatter (C++ glog, TFLite, futex, etc.)
# ---------------------------------------------------------------------------

# The native library uses Google's C++ logging (glog/abseil), TensorFlow
# Lite logging, and Chromium's own LOG() macros -- all of which write
# directly to stderr (fd 2), including from background threads.
#
# Strategy for quiet mode (no --verbose):
#   - Set env vars that the native loggers check (GLOG, abseil, TFLite).
#   - Redirect fd 2 to /dev/null *permanently* and re-point Python's
#     logging to a saved copy of the original stderr.  This catches
#     anything the env vars miss (background threads, etc.).
#
# In --verbose mode none of this is applied.

_native_suppressed = False


def _suppress_native_stderr() -> None:
    """Permanently redirect fd 2 to /dev/null for native code.

    Python logging is re-pointed to the original stderr so our own
    INFO messages remain visible.  Call once, before loading the DLL.
    """
    global _native_suppressed
    if _native_suppressed:
        return
    _native_suppressed = True

    for var in ("GLOG_minloglevel", "TF_CPP_MIN_LOG_LEVEL", "ABSL_MIN_LOG_LEVEL"):
        os.environ.setdefault(var, "3")

    sys.stderr.flush()
    if sys.platform == "win32":
        ctypes.cdll.msvcrt.fflush(None)
    else:
        ctypes.CDLL(None).fflush(None)

    saved_err = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)

    # Give Python logging a file object that writes to the *original*
    # stderr fd so our own messages still appear.
    real_stderr = os.fdopen(saved_err, "w", closefd=False)
    for handler in logging.root.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr:
            handler.stream = real_stderr
    sys.stderr = real_stderr


# ---------------------------------------------------------------------------
# Library location
# ---------------------------------------------------------------------------


def find_screen_ai_dir() -> Path:
    """Find the screen-ai component directory.

    Checks Chrome's user-data directory first, then falls back to the
    package's own download directory (populated by ``locro download``).
    """
    # 1. Chrome / Chromium component directory
    for base in chrome_component_bases():
        if not base.exists():
            continue
        for v in sorted(base.iterdir(), reverse=True):
            if (v / LIB_NAME).exists():
                return v

    # 2. Package's own download directory
    from ._download import find_local_model_dir

    local = find_local_model_dir()
    if local is not None:
        return local

    raise FileNotFoundError(
        "screen-ai component not found.\n"
        "  Run:  locro download\n"
        "  Or install Chrome and visit chrome://components to trigger download."
    )


# ---------------------------------------------------------------------------
# File-content callbacks (the library reads model files through these)
# ---------------------------------------------------------------------------

_model_dir: Path | None = None
_file_cache: dict[str, bytes] = {}

_GetFileSizeFn = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_char_p)
_GetFileContentFn = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p
)


def _read_model_file(relative_path: str) -> bytes:
    if relative_path in _file_cache:
        return _file_cache[relative_path]
    assert _model_dir is not None
    full_path = _model_dir / relative_path
    if not full_path.exists():
        log.warning("Model file not found: %s", full_path)
        return b""
    data = full_path.read_bytes()
    _file_cache[relative_path] = data
    log.debug("Read model file: %s (%d bytes)", relative_path, len(data))
    return data


@_GetFileSizeFn
def _get_file_size_cb(path: ctypes.c_char_p) -> int:
    s = path.decode("utf-8") if isinstance(path, bytes) else path
    return len(_read_model_file(s))


@_GetFileContentFn
def _get_file_content_cb(
    path: ctypes.c_char_p, buf_size: int, buf: ctypes.c_void_p
) -> None:
    s = path.decode("utf-8") if isinstance(path, bytes) else path
    data = _read_model_file(s)
    n = min(len(data), buf_size)
    ctypes.memmove(buf, data[:n], n)


# ---------------------------------------------------------------------------
# SkBitmap struct layout (64-bit x86, Chrome component v140)
# ---------------------------------------------------------------------------

_kBGRA_8888 = 6  # SkColorType  (kN32 on little-endian)
_kPremul = 2  # SkAlphaType


class _SkImageInfo(ctypes.Structure):
    _fields_ = [
        ("fColorSpace", ctypes.c_void_p),
        ("fColorType", ctypes.c_int32),
        ("fAlphaType", ctypes.c_int32),
        ("fWidth", ctypes.c_int32),
        ("fHeight", ctypes.c_int32),
    ]


class _SkPixmap(ctypes.Structure):
    _fields_ = [
        ("fPixels", ctypes.c_void_p),
        ("fRowBytes", ctypes.c_size_t),
        ("fInfo", _SkImageInfo),
    ]


class _SkBitmap(ctypes.Structure):
    _fields_ = [
        ("fPixelRef", ctypes.c_void_p),
        ("fPixmap", _SkPixmap),
        ("fFlags", ctypes.c_uint8),
    ]


class _FakeSkPixelRef(ctypes.Structure):
    """Stub so SkBitmap::isNull() returns false."""

    _fields_ = [
        ("vtable_ptr", ctypes.c_void_p),
        ("refcount", ctypes.c_int32),
        ("_pad", ctypes.c_int32),
        ("fWidth", ctypes.c_int32),
        ("fHeight", ctypes.c_int32),
        ("fPixels", ctypes.c_void_p),
        ("fRowBytes", ctypes.c_size_t),
        ("_extra", ctypes.c_uint8 * 64),
    ]


_FAKE_VTABLE = (ctypes.c_void_p * 16)()


def _make_bitmap(pixels: bytes, width: int, height: int) -> _SkBitmap:
    """Create an SkBitmap struct from raw BGRA pixel data."""
    row_bytes = width * 4
    pixel_buf = ctypes.create_string_buffer(pixels, len(pixels))
    addr = ctypes.addressof(pixel_buf)

    info = _SkImageInfo(
        fColorSpace=0, fColorType=_kBGRA_8888, fAlphaType=_kPremul,
        fWidth=width, fHeight=height,
    )
    pixmap = _SkPixmap(fPixels=addr, fRowBytes=row_bytes, fInfo=info)
    pxref = _FakeSkPixelRef(
        vtable_ptr=ctypes.addressof(_FAKE_VTABLE), refcount=1,
        fWidth=width, fHeight=height, fPixels=addr, fRowBytes=row_bytes,
    )
    bm = _SkBitmap(fPixelRef=ctypes.addressof(pxref), fPixmap=pixmap, fFlags=0)
    bm._prevent_gc = (pixel_buf, pxref)  # prevent GC
    return bm


# ---------------------------------------------------------------------------
# Library wrapper
# ---------------------------------------------------------------------------


class ScreenAIDll:
    """Thin wrapper around screen-ai library exports."""

    def __init__(self, model_dir: Path):
        global _model_dir
        _model_dir = model_dir

        lib_path = model_dir / LIB_NAME
        if not lib_path.exists():
            raise FileNotFoundError(f"Library not found: {lib_path}")

        _ensure_stubs(model_dir)

        if log.getEffectiveLevel() > logging.DEBUG:
            _suppress_native_stderr()

        log.info("Loading %s", lib_path)
        self._dll = ctypes.CDLL(str(lib_path))
        self._bind()

    def _bind(self):
        d = self._dll
        d.GetLibraryVersion.argtypes = [ctypes.POINTER(ctypes.c_uint32)] * 2
        d.GetLibraryVersion.restype = None
        d.SetFileContentFunctions.argtypes = [_GetFileSizeFn, _GetFileContentFn]
        d.SetFileContentFunctions.restype = None
        d.EnableDebugMode.argtypes = []
        d.EnableDebugMode.restype = None
        d.InitOCRUsingCallback.argtypes = []
        d.InitOCRUsingCallback.restype = ctypes.c_bool
        d.SetOCRLightMode.argtypes = [ctypes.c_bool]
        d.SetOCRLightMode.restype = None
        d.GetMaxImageDimension.argtypes = []
        d.GetMaxImageDimension.restype = ctypes.c_uint32
        d.PerformOCR.argtypes = [
            ctypes.POINTER(_SkBitmap), ctypes.POINTER(ctypes.c_uint32),
        ]
        d.PerformOCR.restype = ctypes.c_void_p
        d.FreeLibraryAllocatedCharArray.argtypes = [ctypes.c_void_p]
        d.FreeLibraryAllocatedCharArray.restype = None

    def get_version(self) -> tuple[int, int]:
        major, minor = ctypes.c_uint32(), ctypes.c_uint32()
        self._dll.GetLibraryVersion(ctypes.byref(major), ctypes.byref(minor))
        return major.value, minor.value

    def init_ocr(self) -> bool:
        self._dll.SetFileContentFunctions(_get_file_size_cb, _get_file_content_cb)
        log.info("Initializing OCR pipeline...")
        return bool(self._dll.InitOCRUsingCallback())

    def get_max_image_dimension(self) -> int:
        return self._dll.GetMaxImageDimension()

    def set_light_mode(self, enabled: bool) -> None:
        self._dll.SetOCRLightMode(enabled)

    def perform_ocr(self, bgra_pixels: bytes, width: int, height: int) -> bytes | None:
        """Run OCR on raw BGRA pixel data.  Returns serialised protobuf or None."""
        bm = _make_bitmap(bgra_pixels, width, height)
        out_len = ctypes.c_uint32(0)
        log.info("PerformOCR %dx%d ...", width, height)
        ptr = self._dll.PerformOCR(ctypes.byref(bm), ctypes.byref(out_len))
        if not ptr:
            log.warning("PerformOCR returned null")
            return None
        data = ctypes.string_at(ptr, out_len.value)
        self._dll.FreeLibraryAllocatedCharArray(ptr)
        log.info("PerformOCR returned %d bytes", len(data))
        return data
