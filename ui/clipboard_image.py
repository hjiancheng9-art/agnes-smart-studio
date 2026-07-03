"""Clipboard image helpers — WeChat screenshot paste + drag-drop file detection.

Windows: uses win32clipboard to detect images in clipboard (CF_DIB/CF_BITMAP).
macOS/Linux: uses subprocess to check for clipboard images (pngpaste/xclip).
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("crux.clipboard")

# Supported image extensions for drag-drop detection
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg", ".ico"}


def is_image_path(text: str) -> str:
    """Check if a text looks like a file path pointing to an image.

    Returns the clean path string if it's an image file, empty string otherwise.
    Handles Windows paths with quotes from drag-drop.
    """

    # Strip quotes (Windows drag-drop may wrap in quotes)
    clean = text.strip().strip('"').strip("'")
    # Also handle trailing spaces from multi-file drag
    clean = clean.rstrip(" ,;")

    try:
        fp = Path(clean)
    except (OSError, ValueError):
        return ""

    if fp.is_file() and fp.suffix.lower() in _IMAGE_EXTS:
        return clean
    return ""


def detect_drag_images(text: str) -> list[str]:
    """Detect multiple image file paths from drag-drop text.

    Windows console typically inserts space-separated quoted paths.
    """
    import shlex

    images: list[str] = []
    # Try shlex split for quoted paths
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()

    for part in parts:
        path = is_image_path(part)
        if path:
            images.append(path)
    return images


def get_clipboard_image() -> str | None:
    """Try to get an image from the system clipboard.

    Returns path to a saved temp file if an image was found, None otherwise.
    """
    if sys.platform == "win32":
        return _get_clipboard_image_win32()
    elif sys.platform == "darwin":
        return _get_clipboard_image_macos()
    else:
        return _get_clipboard_image_linux()


def _get_clipboard_image_win32() -> str | None:
    """Windows: check clipboard for bitmap/DIB image data."""
    try:
        import win32clipboard
    except ImportError:
        logger.debug("pywin32 not installed — clipboard image paste unavailable")
        return None

    try:
        win32clipboard.OpenClipboard()
    except Exception:
        return None

    try:
        # Check for DIB (Device Independent Bitmap) — WeChat screenshots use this
        for fmt in (win32clipboard.CF_DIB, win32clipboard.CF_BITMAP):
            try:
                if win32clipboard.IsClipboardFormatAvailable(fmt):
                    data = win32clipboard.GetClipboardData(fmt)
                    if data:
                        return _save_clipboard_dib(data)
            except Exception:
                continue
        return None
    finally:
        with contextlib.suppress(Exception):
            win32clipboard.CloseClipboard()


def _save_clipboard_dib(data: bytes) -> str | None:
    """Save Windows DIB clipboard data to a temp PNG file."""
    try:
        import io

        from PIL import Image

        # DIB = BITMAPINFOHEADER + pixel data
        # Use PIL to parse via BMP (DIB is essentially a BMP without the file header)
        # Prepend a simple BMP file header
        bmp_header = b"BM"
        # DIB data starts with BITMAPINFOHEADER (40 bytes)
        dib_size = len(data)
        file_size = 14 + dib_size
        bmp_header += file_size.to_bytes(4, "little")
        bmp_header += b"\x00\x00"  # reserved1
        bmp_header += b"\x00\x00"  # reserved2
        bmp_header += (14 + 40).to_bytes(4, "little")  # offset to pixel data

        bmp_data = bmp_header + data

        img = Image.open(io.BytesIO(bmp_data))
        # Save as compressed JPEG to temp
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, prefix="crux_clip_")
        tmp_path = tmp.name
        img.convert("RGB").save(tmp, format="JPEG", quality=85, optimize=True)
        tmp.close()
        # 注册 atexit 清理（临时文件非关键，失败不报错）
        import atexit
        @atexit.register
        def _clean():
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
        logger.debug("clipboard image saved: %s (%dKB)", tmp_path, os.path.getsize(tmp_path) // 1024)
        return tmp_path
    except ImportError:
        logger.debug("PIL not installed — can't process clipboard image")
        return None
    except Exception as e:
        logger.debug("failed to save clipboard image: %s", e)
        return None


def _get_clipboard_image_macos() -> str | None:
    """macOS: use pngpaste to get clipboard image."""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="crux_clip_")
        tmp.close()
        r = subprocess.run(
            ["pngpaste", tmp.name],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and os.path.getsize(tmp.name) > 100:
            return tmp.name
        os.unlink(tmp.name)
        return None
    except Exception:
        return None


def _get_clipboard_image_linux() -> str | None:
    """Linux: use xclip to check for image clipboard data."""
    try:
        # Check if clipboard has image mimetype
        r = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
            capture_output=True, timeout=5,
        )
        if r.returncode == 0 and len(r.stdout) > 100:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="crux_clip_")
            tmp.write(r.stdout)
            tmp.close()
            return tmp.name
        return None
    except Exception:
        return None
