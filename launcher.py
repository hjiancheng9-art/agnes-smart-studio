#!/usr/bin/env python3
"""CRUX One-Click Launcher --- start and interconnect all AI tools.

Usage:
    python launcher.py              # health check + TRM catalog + dashboard
    python launcher.py --start      # start persistent services
    python launcher.py --stop       # stop all running services
    python launcher.py --status     # quick connectivity check
    python launcher.py --tools      # TRM tool catalog only

Architecture:
    CRUX (heart) -- MCP mesh -- 7 beasts (organs)
    Each beast exposes tools via MCP stdio bridges.
    Launcher discovers, health-checks, and optionally keeps services alive.
    TRM (Tool Registry Mesh) indexes all tools across all beasts.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# UTF-8 encoding setup (critical on Windows/GDK)
import core.encoding as _enc

_enc.setup()

from core.mcp_servers._mcp_utils import run_subprocess

ROOT = Path(__file__).parent
PID_FILE = ROOT / ".beasts_pids.json"

# ── Rich import (optional, falls back to plain text) ──────────
try:
    from rich.align import Align
    from rich.box import ROUNDED
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── CRUX theme (fallback after UI removal) ────────────────────
try:
    from core.theme import BEAST_ORDER, BEAST_PALETTE, COLORS
    HAS_THEME = True
except ImportError:
    HAS_THEME = False
    BEAST_ORDER = []
    BEAST_PALETTE = {}
    COLORS = {
        "success": "green", "error": "red", "warning": "yellow",
        "primary": "blue", "muted": "dim white", "info": "cyan",
    }
    BEAST_ORDER = ["BAIHU", "QINGLONG", "ZHUQUE", "XUANWU", "QILIN", "TENGSHE", "YINGLONG"]


# ═══════════════════════════════════════════════════════════════
# Beast Configurations
# ═══════════════════════════════════════════════════════════════

@dataclass
class BeastConfig:
    name: str
    role: str
    icon: str
    binary: str
    bridge_script: str = ""
    startup_args: list[str] = field(default_factory=list)
    mcp_initialize: bool = True  # whether to test via MCP initialize handshake
    persistent: bool = False     # keep running in background
    timeout: int = 15
    env: dict[str, str] = field(default_factory=dict)


# Path to Python interpreter
PYTHON = os.path.expanduser(r"C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe")

# Binary locations discovered during research
CODEX_BIN = os.path.expanduser(r"C:\Users\huangjiancheng\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe")
KIMI_BIN = os.path.expanduser(r"~\.kimi-code\bin\kimi.exe")

CODEBUDDY_BIN = os.path.expanduser(r"~\AppData\Roaming\npm\codebuddy.cmd")
ZCODE_BIN = os.path.expanduser(r"~\.zcode\cli\zcode.cjs")
ZCODE_NODE = shutil.which("node") or "node"


BEASTS: dict[str, BeastConfig] = {
    "crux": BeastConfig(
        name="CRUX",
        role="心脏 · 编排中枢 · 媒体工厂",
        icon="❤",
        binary=PYTHON,
        startup_args=["crux_studio.py", "mcp-serve"],
        bridge_script="",
        persistent=True,
        timeout=30,
    ),
    "claude": BeastConfig(
        name="Claude Code",
        role="深度架构推理 · 多文件重构",
        icon="\U0001f9e0",
        binary="claude",
        startup_args=["mcp", "serve"],
        persistent=True,
        timeout=30,
    ),
    # "codex": BeastConfig( ... )  # DISABLED — bridge removed, see bridge-essence-extracted.md
    # "qoder-bridge": BeastConfig( ... )  # DISABLED — bridge removed, see bridge-essence-extracted.md
    # "codebuddy": BeastConfig( ... )  # DISABLED — bridge removed, see bridge-essence-extracted.md
    # "zcode": BeastConfig( ... )  # DISABLED — bridge removed, see bridge-essence-extracted.md
}


# ═══════════════════════════════════════════════════════════════
# Health Check Engine
# ═══════════════════════════════════════════════════════════════

@dataclass
class HealthResult:
    name: str
    icon: str
    role: str = ""      # one-line role description
    status: str = ""    # "online", "degraded", "offline"
    version: str = ""
    latency_ms: float = 0.0
    error: str = ""


def _spawn_and_initialize(cfg: BeastConfig) -> HealthResult:
    """Spawn the beast's MCP bridge/server, send initialize, measure response."""
    t0 = time.monotonic()

    # Build command
    if cfg.bridge_script:
        script = ROOT / cfg.bridge_script
        if not script.exists():
            return HealthResult(
                name=cfg.name, icon=cfg.icon, role=cfg.role, status="offline",
                version="", latency_ms=0,
                error=f"Bridge script not found: {cfg.bridge_script}"
            )
        cmd = [cfg.binary, str(script)]
    elif cfg.startup_args:
        cmd = [cfg.binary] + cfg.startup_args
    else:
        cmd = [cfg.binary]

    # For non-MCP CLIs, just verify binary exists and returns 0
    if not cfg.mcp_initialize:
        try:
            r = run_subprocess(cmd, timeout=cfg.timeout, cwd=str(ROOT), env_add={**cfg.env})
            latency = (time.monotonic() - t0) * 1000
            if r.returncode == 0:
                version_line = (r.stdout or "").split("\n")[0].strip()
                return HealthResult(
                    name=cfg.name, icon=cfg.icon, status="online",
                    version=version_line[:80], latency_ms=latency, error=""
                )
            else:
                return HealthResult(
                    name=cfg.name, icon=cfg.icon, status="degraded",
                    version="", latency_ms=latency,
                    error=(r.stderr or r.stdout or "")[:120]
                )
        except FileNotFoundError:
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="offline",
                version="", latency_ms=0,
                error=f"Binary not found: {cfg.binary}"
            )
        except subprocess.TimeoutExpired:
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="degraded",
                version="", latency_ms=cfg.timeout * 1000,
                error=f"Timed out after {cfg.timeout}s"
            )
        except Exception as exc:
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="offline",
                version="", latency_ms=(time.monotonic() - t0) * 1000,
                error=str(exc)[:120]
            )

    # MCP initialize handshake
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            env={**os.environ, **cfg.env},
        )

        # Send JSON-RPC initialize
        init_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "beast-launcher", "version": "1.0.0"}
            }
        }) + "\n"

        try:
            proc.stdin.write(init_msg)
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            proc.kill()
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="offline",
                version="", latency_ms=(time.monotonic() - t0) * 1000,
                error="Process died before initialize"
            )

        # Read response with timeout
        import threading
        response_line = None
        read_error = None

        def _read():
            nonlocal response_line, read_error
            try:
                response_line = proc.stdout.readline()
            except Exception as exc:
                read_error = str(exc)

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        reader.join(timeout=cfg.timeout)

        latency = (time.monotonic() - t0) * 1000

        if reader.is_alive():
            proc.kill()
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="degraded",
                version="", latency_ms=latency,
                error=f"No response within {cfg.timeout}s"
            )

        if read_error:
            proc.kill()
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="offline",
                version="", latency_ms=latency, error=read_error
            )

        if not response_line:
            # Check stderr for clues
            stderr_text = ""
            try:
                stderr_text = proc.stderr.read(500)
            except Exception:
                logging.warning("Failed to read stderr from %s health check", cfg.name)
                stderr_text = "<read error>"
            proc.kill()
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="offline",
                version="", latency_ms=latency,
                error=f"No response. stderr: {stderr_text[:100]}"
            )

        # Parse response
        try:
            resp = json.loads(response_line.strip())
        except json.JSONDecodeError:
            proc.kill()
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="degraded",
                version="", latency_ms=latency,
                error=f"Invalid JSON response: {response_line[:80]}"
            )

        proc.kill()

        if "error" in resp:
            return HealthResult(
                name=cfg.name, icon=cfg.icon, status="degraded",
                version="", latency_ms=latency,
                error=str(resp["error"])[:120]
            )

        result = resp.get("result", {})
        server_info = result.get("serverInfo", {})
        version = f"{server_info.get('name', '')} v{server_info.get('version', '?')}"

        # Count tools if available
        if "capabilities" in result:
            tools_section = result.get("capabilities", {}).get("tools", {})
            if tools_section:
                version += " [tools cap]"

        return HealthResult(
            name=cfg.name, icon=cfg.icon, status="online",
            version=version, latency_ms=latency, error=""
        )

    except FileNotFoundError:
        return HealthResult(
            name=cfg.name, icon=cfg.icon, status="offline",
            version="", latency_ms=0,
            error=f"Binary not found: {cfg.binary}"
        )
    except Exception as exc:
        return HealthResult(
            name=cfg.name, icon=cfg.icon, status="offline",
            version="", latency_ms=(time.monotonic() - t0) * 1000,
            error=str(exc)[:120]
        )
    finally:
        # Ensure subprocess is always cleaned up on exception paths
        if 'proc' in locals():
            proc.kill()


# ═══════════════════════════════════════════════════════════════
# Process Manager (for persistent services)
# ═══════════════════════════════════════════════════════════════

class ProcessManager:
    """Manages long-running MCP server processes."""

    def __init__(self) -> None:
        self._procs: dict[str, subprocess.Popen] = {}

    def start(self, name: str, cfg: BeastConfig) -> bool:
        """Start a persistent service. Auto-cleans zombie entries."""
        # Clean up zombie before checking if running
        proc = self._procs.get(name)
        if proc and proc.poll() is None:
            return True  # already running
        # Remove zombie entry if present
        if name in self._procs:
            del self._procs[name]

        if cfg.bridge_script:
            script = ROOT / cfg.bridge_script
            cmd = [cfg.binary, str(script)]
        elif cfg.startup_args:
            cmd = [cfg.binary] + cfg.startup_args
        else:
            return False

        try:
            # DETACHED_PROCESS: don't inherit console, so launcher window
            # can close while background services keep running
            cflags = subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(ROOT),
                env={**os.environ, **cfg.env},
                creationflags=cflags,
            )
            self._procs[name] = proc
            return True
        except Exception as e:
            logging.warning("Failed to start service %s: %s", cfg.name, str(e)[:120])
            return False

    def stop(self, name: str) -> None:
        """Stop a persistent service. Auto-cleans zombie entries."""
        proc = self._procs.pop(name, None)
        if proc is None:
            return
        # Skip if process already dead
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass  # already dead

    def stop_all(self) -> None:
        """Stop all persistent services and clean up zombie entries."""
        self.cleanup_zombies()
        for name in list(self._procs):
            self.stop(name)

    def cleanup_zombies(self) -> int:
        """Remove dead process entries from _procs dict. Returns count removed."""
        removed = 0
        for name, proc in list(self._procs.items()):
            if proc.poll() is not None:
                del self._procs[name]
                removed += 1
        return removed

    @property
    def running(self) -> list[str]:
        self.cleanup_zombies()
        return [n for n, p in self._procs.items() if p.poll() is None]

    def save_pids(self) -> None:
        pids = {n: p.pid for n, p in self._procs.items() if p.poll() is None}
        PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")

    def load_and_kill(self) -> int:
        """Kill previously saved PIDs. Returns count killed."""
        if not PID_FILE.exists():
            return 0
        try:
            pids = json.loads(PID_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        killed = 0
        for _name, pid in pids.items():
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
            except (OSError, ProcessLookupError):
                pass
        PID_FILE.unlink(missing_ok=True)
        return killed


# ═══════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════

STATUS_GLYPHS = {
    "online":   "●",
    "degraded": "◈",
    "offline":  "○",
}

STATUS_COLORS = {
    "online":   "#A6E3A1" if HAS_THEME else "green",
    "degraded": "#FAB387" if HAS_THEME else "yellow",
    "offline":  "#F38BA8" if HAS_THEME else "red",
}

STATUS_LABELS_ZH = {
    "online":   "● 在线",
    "degraded": "◈ 降级",
    "offline":  "○ 离线",
}

BEAST_ICONS = {
    "BAIHU":    "🐅", "QINGLONG": "🐉", "ZHUQUE": "🕊",
    "XUANWU":   "🐢", "QILIN":    "🦄", "TENGSHE": "🐍",
    "YINGLONG": "🪽",
}

def print_ascii_dashboard(results: list[HealthResult], elapsed: float) -> None:
    """Fallback ASCII dashboard when Rich is not available."""
    print()
    print("=" * 70)
    print("  ⚒  核心互联 — 连通性面板")
    print("=" * 70)
    online = sum(1 for r in results if r.status == "online")
    degraded = sum(1 for r in results if r.status == "degraded")
    offline = sum(1 for r in results if r.status == "offline")
    print(f"  ● 在线: {online}  |  ◆ 降级: {degraded}  |  ✗ 离线: {offline}")
    print(f"  健康检查完成，耗时 {elapsed:.1f}s")
    print("-" * 70)
    for r in results:
        glyph = STATUS_GLYPHS.get(r.status, "?")
        label = STATUS_LABELS_ZH.get(r.status, r.status.upper())
        line = f"  {glyph} {r.icon}  {r.name:<16s} [{label:<4s}]"
        if r.version:
            line += f"  {r.version}"
        if r.latency_ms > 0:
            line += f"  ({r.latency_ms:.0f}ms)"
        if r.error:
            line += f"\n       错误: {r.error}"
        print(line)
    print("=" * 70)
    print()


def print_rich_dashboard(results: list[HealthResult], elapsed: float) -> None:
    """Rich terminal dashboard."""
    try:
        _render_rich_dashboard(results, elapsed)
    except Exception:
        print_ascii_dashboard(results, elapsed)


def _beast_color(index: int) -> str:
    """Return the hex color for a beast by index."""
    if HAS_THEME and index < len(BEAST_ORDER):
        return BEAST_PALETTE.get(BEAST_ORDER[index], "#F9E2AF")
    return "#F9E2AF"


def _render_rich_dashboard(results: list[HealthResult], elapsed: float) -> None:
    """Catppuccin Mocha 风格的 Rich 仪表盘。"""
    console = Console()

    # 面板色 — 从主题取，失败回落
    border_c = COLORS["border_active"] if HAS_THEME else "#89B4FA"
    accent_c = COLORS["accent"] if HAS_THEME else "#89B4FA"
    primary_c = COLORS["primary"] if HAS_THEME else "#CDD6F4"
    muted_c = COLORS["muted"] if HAS_THEME else "#7F849C"

    # ── 七兽巡礼标题行 ──
    beast_line_parts = []
    for i, name in enumerate(BEAST_ORDER):
        c = _beast_color(i)
        icon = BEAST_ICONS.get(name, "?")
        beast_line_parts.append(f"[{c}]{icon} {name}[/{c}]")
    beast_line = " ◈ ".join(beast_line_parts)

    # ── 构建表格 ──
    table = Table(
        title=None, show_header=True, header_style=f"bold {primary_c}",
        expand=True, box=ROUNDED, border_style=border_c,
        row_styles=[f"on {COLORS['surface']}" if HAS_THEME else "", ""],
    )
    table.add_column("", width=2, no_wrap=True)
    table.add_column("名称", style=f"bold {primary_c}", width=18)
    table.add_column("定位", style=muted_c, width=40)
    table.add_column("状态", width=12)
    table.add_column("版本 / 信息", width=30)
    table.add_column("延迟", width=10, justify="right")

    online = degraded = offline = 0

    for _idx, r in enumerate(results):
        glyph = STATUS_GLYPHS.get(r.status, "?")
        glyph_c = STATUS_COLORS.get(r.status, muted_c)
        if r.status == "online":
            online += 1
            status_text = "在线"
            status_s = STATUS_COLORS["online"]
        elif r.status == "degraded":
            degraded += 1
            status_text = "降级"
            status_s = STATUS_COLORS["degraded"]
        else:
            offline += 1
            status_text = "离线"
            status_s = STATUS_COLORS["offline"]

        info = r.version if r.version else ("-" if not r.error else "")
        if r.error and not r.version:
            info = f"[{STATUS_COLORS['offline']}]{r.error[:50]}[/]"

        latency = f"{r.latency_ms:.0f}ms" if r.latency_ms > 0 else "-"

        table.add_row(
            f"[{glyph_c}]{glyph}[/]",
            f"{r.icon} {r.name}",
            r.role,
            f"[{status_s}]{status_text}[/]",
            info,
            latency,
        )

    # ── 汇总条 ──
    summary = Text()
    summary.append("  ● ", style=STATUS_COLORS["online"])
    summary.append("● ", style=f"{STATUS_COLORS['online']} bold")
    summary.append(f"在线 {online}  ", style=f"{STATUS_COLORS['online']} bold")
    summary.append("◈ ", style=STATUS_COLORS["degraded"])
    summary.append(f"降级 {degraded}  ", style=STATUS_COLORS["degraded"])
    summary.append("○ ", style=STATUS_COLORS["offline"])
    summary.append(f"离线 {offline}  ", style=STATUS_COLORS["offline"])
    summary.append(f"│  耗时 {elapsed:.1f}s", style=muted_c)

    # ── 网格状态 ──
    if offline == 0 and degraded == 0:
        mesh_status = f"[{STATUS_COLORS['online']}]● 七兽共鸣 — 网格就绪[/]"
    elif offline == 0:
        mesh_status = f"[{STATUS_COLORS['degraded']}]◈ 网格降级 — {degraded} 兽性能受限[/]"
    else:
        mesh_status = f"[{STATUS_COLORS['offline']}]○ 网格不完整 — {offline} 兽不可达[/]"

    # ── 渲染 ──
    console.print()
    console.print(Panel(
        Align.center(
            f"[bold {accent_c}]╔══ █ CRUX · 连通性面板 █ ══╗[/]\n"
            f"[{muted_c}]{beast_line}[/]\n\n"
            f"{mesh_status}"
        ),
        border_style=border_c,
        box=ROUNDED,
        padding=(1, 3),
    ))
    console.print(table)
    console.print(summary)
    console.print()


# ═══════════════════════════════════════════════════════════════
# Main Launcher
# ═══════════════════════════════════════════════════════════════

class MeshLauncher:
    """Orchestrates discovery, health checks, and process management."""

    def __init__(self) -> None:
        self.results: list[HealthResult] = []
        self.trm_summary: str = ""
        self.proc_mgr = ProcessManager()

    def discover_trm(self) -> str:
        """Discover TRM tool catalog and return summary text."""
        try:
            from core.tool_registry_mesh import get_trm
            trm = get_trm()
            trm.discover_all(timeout=5.0)
            self.trm_summary = trm.as_text()
            return self.trm_summary
        except Exception as e:
            self.trm_summary = f"TRM: discovery failed ({e})"
            return self.trm_summary

    def health_check_all(self) -> list[HealthResult]:
        """Run health check on all beasts sequentially."""
        results = []
        # CRUX first (heart), then others
        order = ["crux", "claude"]
        for key in order:
            cfg = BEASTS.get(key)
            if cfg is None:
                continue
            result = _spawn_and_initialize(cfg)
            result.role = cfg.role  # carry role from config
            results.append(result)
            # Brief pause to avoid hammering
            time.sleep(0.1)
        self.results = results
        return results

    def show_dashboard(self, elapsed: float) -> None:
        if HAS_RICH:
            print_rich_dashboard(self.results, elapsed)
        else:
            print_ascii_dashboard(self.results, elapsed)

    def start_persistent(self) -> None:
        """Start CRUX and Claude MCP serve as background processes."""
        print("  正在启动持久服务...")
        for key in ["crux", "claude"]:
            cfg = BEASTS.get(key)
            if cfg is None:
                continue
            ok = self.proc_mgr.start(key, cfg)
            glyph = STATUS_GLYPHS["online"] if ok else STATUS_GLYPHS["offline"]
            print(f"  {glyph} {cfg.icon} {cfg.name}: {'已启动' if ok else '启动失败'}")
        self.proc_mgr.save_pids()
        running = self.proc_mgr.running
        if running:
            print(f"\n  ● 运行中的服务: {', '.join(running)}")
            print(f"  PID 已保存至: {PID_FILE}")
            print("  执行 'python launcher.py --stop' 可一键停止。")
        print()

    def launch_main_window(self) -> None:
        """Open CRUX Studio main window in a new terminal."""
        crux_script = ROOT / "crux_studio.py"
        exe_path = PYTHON

        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "CRUX Studio", exe_path, str(crux_script), "-c"],
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_CONSOLE
                if sys.platform == "win32" else 0,
            )
            print("  ● 主战窗口已拉起 — 进入暗夜工坊")
        except Exception as e:
            logging.warning("Failed to launch CRUX Studio: %s", str(e)[:120])
            print("  ✗ 拉起 CRUX 失败，请手动启动。")

    def stop_all(self) -> None:
        killed = self.proc_mgr.load_and_kill()
        if killed:
            print(f"  已停止 {killed} 个运行中的服务。")
        else:
            print("  没有运行中的服务（未找到 PID 文件）。")


TITLE_ART = r"""
   ╔══════════════════════════════════════════════════╗
   ║     ⚒  CRUX  STUDIO   ·   七 兽 互 联 启 动 器  ║
   ║     白虎为骨 · 青龙为脉 · 朱雀为眼               ║
   ║     玄武为甲 · 麒麟为手 · 螣蛇为忆               ║
   ║     应龙为令 · MCP 网格 · 万象共生               ║
   ╚══════════════════════════════════════════════════╝
"""


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="CRUX MESH Launcher — one-click startup for all AI tools"
    )
    p.add_argument("--start", action="store_true",
                   help="Start persistent services (CRUX + Claude MCP serve)")
    p.add_argument("--stop", action="store_true",
                   help="Stop all running persistent services")
    p.add_argument("--status", action="store_true",
                   help="Quick connectivity check only")
    p.add_argument("--no-check", action="store_true",
                   help="Skip health check (start only)")
    p.add_argument("--launch", action="store_true",
                   help="One-click launch: health-check + start services + main window")
    args = p.parse_args()

    # If no flags → dashboard + interactive menu (for double-click users)
    has_flags = args.start or args.stop or args.status or args.no_check or args.launch
    if not has_flags:
        # 先做健康检查并显示仪表盘
        print(TITLE_ART)
        launcher = MeshLauncher()
        print("\n  正在健康检查...\n")
        t0 = time.monotonic()
        launcher.health_check_all()
        elapsed = time.monotonic() - t0
        launcher.show_dashboard(elapsed)
        launcher.discover_trm()
        if launcher.trm_summary:
            print(f"  {launcher.trm_summary}")

        # 简短菜单
        print()
        print("  [1] 进入聊天（全屏 TUI）")
        print("  [2] 启动后台服务")
        print("  [3] 查看状态")
        print("  [q] 退出")
        print()

        while True:
            try:
                ch = input("  选择 [1/2/3/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ch = "q"
            if ch == "q":
                break
            elif ch == "1":
                print("  正在启动 CRUX TUI...")
                subprocess.run(
                    [PYTHON, str(ROOT / "crux_studio.py"), "-c"],
                    cwd=str(ROOT),
                )
                break
            elif ch == "2":
                launcher.start_persistent()
                break
            elif ch == "3":
                launcher.show_dashboard(elapsed)
            else:
                print("  无效选择")
        return

    print(TITLE_ART)

    launcher = MeshLauncher()

    # --stop: kill saved PIDs and exit
    if args.stop:
        launcher.stop_all()
        return

    # Health check (unless --no-check)
    if not args.no_check:
        print("\n  正在健康检查...\n")
        t0 = time.monotonic()
        launcher.health_check_all()
        elapsed = time.monotonic() - t0
        launcher.show_dashboard(elapsed)

    # --status: check only, no start
    if args.status:
        return

    # --launch: one-click health-check + start + main window
    if args.launch:
        launcher.discover_trm()
        if launcher.trm_summary:
            print(f"  {launcher.trm_summary}")
        launcher.start_persistent()
        print("  正在拉起主战窗口...")
        launcher.launch_main_window()
        print("\n  启动完成。服务已后台运行，主战窗口已打开。")
        return

    # --start: launch persistent services
    if args.start:
        launcher.start_persistent()


if __name__ == "__main__":
    main()
