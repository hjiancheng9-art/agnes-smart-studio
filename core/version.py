"""
Version module — 单一版本真源 (single source of truth).

所有需要展示应用版本号的地方都应从这里导入 __version__，
不要再在各处硬编码版本字符串（曾出现 pyproject=3.0 / manifest=5.0 /
Logo=v2.0 / web_api=4.0 四处打架的历史问题）。

注意: agnes-video-v2.0 / agnes-image-2.1 等是「模型 ID」，
属于 API 端点标识，与本应用版本号无关，不要在这里改动。
"""

__version__ = "5.1.0"
VERSION = __version__  # 向后兼容旧调用


def get_version_string() -> str:
    """Return the current version string."""
    return __version__


def print_version() -> None:
    """Print the current version string to stdout."""
    print(f"Version: {__version__}")


def get_version_tuple() -> tuple[int, int, int]:
    """Return the version as a (major, minor, patch) tuple of ints."""
    parts = __version__.split(".")
    return tuple(int(p) for p in parts[:3])  # type: ignore[return-value]


__all__ = [
    "VERSION",
    "__version__",
    "get_version_string",
    "get_version_tuple",
    "print_version",
]
