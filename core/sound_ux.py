"""Sound UX — CRUX 音效系统。启动音/成功叮/错误嗡/熔断警报/炼丹完成钟。
基于 edge-tts (微软免费语音引擎) 或系统 beep fallback。
所有音效异步播放，不阻塞主流程。
用法:
  from core.sound_ux import SoundUX
  SoundUX.startup()  #
  SoundUX.success()  #
  SoundUX.error()    #
  SoundUX.alert()    #
  SoundUX.alchemy()  #
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = ["SOUND_DIR", "SoundUX"]
ROOT = Path(__file__).resolve().parent.parent
SOUND_DIR = ROOT / "output" / "sounds"
SOUND_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("crux.sound_ux")


class SoundUX:
    """CRUX 音效系统 — 异步播放，永远不阻塞主流程。"""

    _enabled = True
    _lock = threading.Lock()

    @classmethod
    def _play(cls, text: str, duration: float = 1.5):
        """异步播放 TTS 短音频。失败静默降级。"""
        if not cls._enabled:
            return

        def _run():
            try:
                # 优先 edge-tts
                mp3_path = SOUND_DIR / f"sfx_{hash(text) % 10000}.mp3"
                if not mp3_path.exists():
                    r = run_subprocess(
                        ["edge-tts", "--text", text, "--voice", "zh-CN-XiaoxiaoNeural", "--write-media", str(mp3_path)],
                        timeout=8,
                        cwd=str(ROOT),
                    )
                    if r.returncode != 0:
                        cls._beep_fallback()
                        return
                # 播放
                if sys.platform == "win32":
                    run_subprocess(["start", "/min", "wmplayer", str(mp3_path)], shell=True, timeout=3)  # nosec B604
                else:
                    run_subprocess(["ffplay", "-nodisp", "-autoexit", "-t", str(duration), str(mp3_path)], timeout=5)
            except (OSError, RuntimeError, subprocess.SubprocessError) as e:
                logger.debug("TTS playback failed (%s), falling back to beep", e)
                cls._beep_fallback()

        threading.Thread(target=_run, daemon=True).start()

    @classmethod
    def _beep_fallback(cls):
        """系统蜂鸣降级。"""
        try:
            if sys.platform == "win32":
                import winsound

                winsound.Beep(800, 200)
            else:
                sys.stdout.write("\a")
                sys.stdout.flush()
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("Sound fallback: %s", e)

    # ── 音效 API ────────────────────────────────────────────
    @classmethod
    def startup(cls):
        """启动音 — 低沉有力的开机声。"""
        cls._play("CRUX Studio 启动", 1.0)

    @classmethod
    def success(cls):
        """成功叮 — 清脆的完成提示。"""
        try:
            if sys.platform == "win32":
                import winsound

                winsound.Beep(1200, 100)
                time.sleep(0.05)
                winsound.Beep(1600, 150)
            else:
                sys.stdout.write("\a")
                sys.stdout.flush()
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("SFX fallback: %s", e)

    @classmethod
    def error(cls):
        """错误嗡 — 低沉短促的错误提示。"""
        try:
            if sys.platform == "win32":
                import winsound

                winsound.Beep(400, 200)
                time.sleep(0.08)
                winsound.Beep(300, 300)
            else:
                sys.stdout.write("\a\a")
                sys.stdout.flush()
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("SFX fallback: %s", e)

    @classmethod
    def alert(cls):
        """熔断警报 — 三连急促警告音。"""
        try:
            if sys.platform == "win32":
                import winsound

                for _ in range(3):
                    winsound.Beep(600, 150)
                    time.sleep(0.06)
            else:
                for _ in range(3):
                    sys.stdout.write("\a")
                    sys.stdout.flush()
                    time.sleep(0.1)
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("SFX fallback: %s", e)

    @classmethod
    def alchemy(cls):
        """炼丹完成 — 悠长的完成钟声。"""
        try:
            if sys.platform == "win32":
                import winsound

                winsound.Beep(1000, 150)
                time.sleep(0.1)
                winsound.Beep(1400, 150)
                time.sleep(0.1)
                winsound.Beep(1800, 300)
            else:
                for _ in range(3):
                    sys.stdout.write("\a")
                    sys.stdout.flush()
                    time.sleep(0.15)
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("SFX fallback: %s", e)

    @classmethod
    def toggle(cls, enabled: bool | None = None) -> bool:
        """开关音效。返回当前状态。"""
        if enabled is not None:
            cls._enabled = enabled
        return cls._enabled
