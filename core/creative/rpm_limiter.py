"""
RPM Limiter — 速率限制队列

为 Agnes API 提供 RPM (Requests Per Minute) 友好的排队机制。
默认限制：
  - 视频: 1 RPM
  - 图片: 10 RPM（根据 price tier 自动调整）
  - 文本: 20 RPM

Usage:
    limiter = RPMLimiter()

    with limiter.limit("video"):
        result = agnes.create_video_task(...)

    # 或异步等待
    await limiter.wait("video")
    result = agnes.create_video_task(...)
"""

import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RateBucket:
    """速率桶 — 记录每个类别的请求时间戳"""

    max_rpm: int = 1
    timestamps: list[float] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self, block: bool = True, timeout: float = 60.0) -> bool:
        """
        尝试获取一个请求 slot。

        Args:
            block: 是否阻塞等待
            timeout: 最大等待秒数

        Returns:
            是否获取成功
        """
        start = time.time()

        while True:
            with self.lock:
                now = time.time()
                # 清理超过 60s 的时间戳
                self.timestamps = [t for t in self.timestamps if now - t < 60.0]

                if len(self.timestamps) < self.max_rpm:
                    self.timestamps.append(now)
                    return True

            if not block:
                return False

            # 等待重试
            elapsed = time.time() - start
            if elapsed >= timeout:
                return False

            # 计算需要等待的时间
            with self.lock:
                if self.timestamps:
                    oldest = min(self.timestamps)
                    wait = max(0.1, oldest + 60.0 - time.time())
                else:
                    wait = 0.1

            time.sleep(min(wait, 1.0))


class RPMLimiter:
    """
    全局 RPM 限流器。
    支持 with 语句和装饰器两种用法。
    """

    # 默认 RPM 配置（单位: 请求/分钟）
    DEFAULT_LIMITS = {
        "video": 1,
        "image": 10,
        "text": 20,
        "agent": 20,
    }

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._buckets: dict[str, RateBucket] = {}
        self._stats: dict[str, dict] = defaultdict(lambda: {"called": 0, "waited": 0, "total_wait_s": 0.0})

        for category, rpm in self.DEFAULT_LIMITS.items():
            self._buckets[category] = RateBucket(max_rpm=rpm)

        logger.debug("RPMLimiter 初始化: %s", dict(self.DEFAULT_LIMITS))

    def set_limit(self, category: str, rpm: int):
        """动态调整某个类别的 RPM 限制"""
        if category not in self._buckets:
            self._buckets[category] = RateBucket(max_rpm=rpm)
        else:
            self._buckets[category].max_rpm = rpm
        logger.info("RPMLimiter: %s RPM 调整为 %d", category, rpm)

    def get_config(self) -> dict:
        """获取当前配置"""
        return {cat: bucket.max_rpm for cat, bucket in self._buckets.items()}

    def get_stats(self) -> dict:
        """获取统计信息"""
        return dict(self._stats)

    def wait(self, category: str, timeout: float = 60.0) -> bool:
        """
        等待直到可以执行请求。

        Args:
            category: 类别 (video/image/text/agent)
            timeout: 超时秒数

        Returns:
            是否在超时前获取到 slot
        """
        bucket = self._buckets.get(category, self._buckets.get("text", RateBucket()))

        self._stats[category]["called"] += 1
        start = time.time()

        acquired = bucket.acquire(block=True, timeout=timeout)

        elapsed = time.time() - start
        if elapsed > 0.1:
            self._stats[category]["waited"] += 1
            self._stats[category]["total_wait_s"] += elapsed
            logger.debug("RPM wait %s: %.1fs", category, elapsed)

        return acquired

    @contextmanager
    def limit(self, category: str = "video", timeout: float = 60.0):
        """
        with RPMLimiter().limit("video"):
            ...
        """
        self.wait(category, timeout=timeout)
        try:
            yield
        finally:
            pass


# 全局单例
limiter = RPMLimiter()


def rate_limit(category: str = "video"):
    """装饰器: 自动限流"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            limiter.wait(category)
            return func(*args, **kwargs)

        return wrapper

    return decorator
