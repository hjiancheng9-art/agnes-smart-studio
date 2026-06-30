#!/usr/bin/env python3
"""Nine Beasts One-Click Launcher --- start and interconnect all AI tools.

Usage:
    python launcher.py              # health check + TRM catalog + dashboard
    python launcher.py --start      # start persistent services
    python launcher.py --stop       # stop all running services
    python launcher.py --status     # quick connectivity check
    python launcher.py --tools      # TRM tool catalog only

Architecture:
    CRUX (heart) -- MCP mesh -- 8 beasts (organs)
    Each beast exposes tools via MCP stdio bridges.
    Launcher discovers, health-checks, and optionally keeps services alive.
    TRM (Tool Registry Mesh) indexes all tools across all beasts.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from core.mcp_servers._mcp_utils import run_subprocess

ROOT = Path(__file__).parent
PID_FILE = ROOT / ".beasts_pids.json"

# ── Rich import (optional, falls back to plain text) ──────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.layout import Layout
    from rich.align import Align
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


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
COPILOT_BIN = os.path.expanduser(r"~\AppData\Roaming\npm\copilot.cmd")
QODER_BIN = os.path.expanduser(r"~\.qoder\bin\qodercli\qodercli.exe")
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
    "codex": BeastConfig(
        name="Codex",
        role="视觉编码 · 网页浏览",
        icon="\U0001f441",
        binary=CODEX_BIN,
        startup_args=["--help"],
        mcp_initialize=False,
        timeout=20,
    ),
    "kimi": BeastConfig(
        name="Kimi",
        role="超长上下文 · 中文内容处理",
        icon="\U0001f4dc",
        binary=PYTHON,
        bridge_script="core/mcp_servers/kimi_bridge.py",
        timeout=20,
    ),
    "copilot": BeastConfig(
        name="Copilot",
        role="IDE 神经末梢 · 行内补全",
        icon="\U0001f916",
        binary=PYTHON,
        bridge_script="core/mcp_servers/copilot_bridge.py",
        timeout=20,
    ),
    "qoder": BeastConfig(
        name="Qoder",
        role="终端原住民 · Shell 操作",
        icon="\U0001f5a5",
        binary=QODER_BIN,
        startup_args=["--version"],
        mcp_initialize=False,
        timeout=15,
    ),
    "qoder-bridge": BeastConfig(
        name="Qoder 桥接",
        role="Qoder MCP 桥接器",
        icon="\U0001f517",
        binary=PYTHON,
        bridge_script="core/mcp_servers/qoder_bridge.py",
        timeout=20,
    ),
    "codebuddy": BeastConfig(
        name="CodeBuddy",
        role="生态延伸 · 备选编码视角",
        icon="\U0001f4a1",
        binary=PYTHON,
        bridge_script="core/mcp_servers/codebuddy_bridge.py",
        timeout=20,
    ),
    "zcode": BeastConfig(
        name="ZCode (GLM)",
        role="智谱清言 · GLM-5.2 旗舰模型",
        icon="\U0001f40c",
        binary=PYTHON,
        bridge_script="core/mcp_servers/zcode_bridge.py",
        timeout=30,
    ),
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
                version += f" [tools cap]"

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
        for name, pid in pids.items():
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
    "online":   "✅",   # checkmark
    "degraded": "⚠️",  # warning
    "offline":  "❌",   # X
}


STATUS_LABELS_ZH = {
    "online":   "在线",
    "degraded": "降级",
    "offline":  "离线",
}

def print_ascii_dashboard(results: list[HealthResult], elapsed: float) -> None:
    """Fallback ASCII dashboard when Rich is not available."""
    print()
    print("=" * 70)
    print("  九兽互联 — 连通性面板")
    print("=" * 70)
    online = sum(1 for r in results if r.status == "online")
    degraded = sum(1 for r in results if r.status == "degraded")
    offline = sum(1 for r in results if r.status == "offline")
    print(f"  在线: {online}  |  降级: {degraded}  |  离线: {offline}")
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


def _render_rich_dashboard(results: list[HealthResult], elapsed: float) -> None:
    """Actual Rich rendering — wrapped for graceful fallback."""
    console = Console()

    # Build table
    table = Table(title=None, show_header=True, header_style="bold", expand=True)
    table.add_column("", width=2, no_wrap=True)
    table.add_column("名称", style="bold", width=18)
    table.add_column("定位", width=40)
    table.add_column("状态", width=12)
    table.add_column("版本 / 信息", width=30)
    table.add_column("延迟", width=10, justify="right")

    online = degraded = offline = 0

    for r in results:
        glyph = STATUS_GLYPHS.get(r.status, "?")
        if r.status == "online":
            online += 1
            status_style = "green"
            status_text = "在线"
        elif r.status == "degraded":
            degraded += 1
            status_style = "yellow"
            status_text = "降级"
        else:
            offline += 1
            status_style = "red"
            status_text = "离线"

        info = r.version if r.version else ("-" if not r.error else "")
        if r.error and not r.version:
            info = f"[dim red]{r.error[:50]}[/]"

        latency = f"{r.latency_ms:.0f}ms" if r.latency_ms > 0 else "-"

        table.add_row(
            glyph,
            f"{r.icon} {r.name}",
            r.role,
            f"[{status_style}]{status_text}[/]",
            info,
            latency,
        )

    # Build summary panel
    summary = Text()
    summary.append(f"  在线: ", style="green bold")
    summary.append(f"{online}  ", style="green")
    summary.append(f"降级: ", style="yellow bold")
    summary.append(f"{degraded}  ", style="yellow")
    summary.append(f"离线: ", style="red bold")
    summary.append(f"{offline}  ", style="red")
    summary.append(f"|  耗时 {elapsed:.1f}s", style="dim")

    # Total mesh status
    if offline == 0 and degraded == 0:
        mesh_status = "[bold green]全部在线 — 网格就绪[/]"
    elif offline == 0:
        mesh_status = f"[bold yellow]网格降级 — {degraded} 兽性能受限[/]"
    else:
        mesh_status = f"[bold red]网格不完整 — {offline} 兽不可达[/]"

    console.print()
    console.print(Panel(
        Align.center("[bold]九兽互联 — 连通性面板[/]\n" + mesh_status),
        border_style="bright_blue",
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
            count = trm.discover_all(timeout=5.0)
            self.trm_summary = trm.as_text()
            return self.trm_summary
        except Exception as e:
            self.trm_summary = f"TRM: discovery failed ({e})"
            return self.trm_summary

    def health_check_all(self) -> list[HealthResult]:
        """Run health check on all beasts sequentially."""
        results = []
        # CRUX first (heart), then others
        order = ["crux", "claude", "codex", "kimi", "copilot",
                  "qoder", "qoder-bridge", "codebuddy", "zcode"]
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
            print(f"\n  运行中的服务: {', '.join(running)}")
            print(f"  PID 已保存至: {PID_FILE}")
            print(f"  执行 'python launcher.py --stop' 可一键停止。")
        print()

    def launch_main_window(self) -> None:
        """Open Kimi interactive main window in a new terminal."""
        exe_path = KIMI_BIN

        if not os.path.isfile(exe_path):
            found = shutil.which("kimi")
            if found:
                exe_path = found
            else:
                print("  ⚠️ 未找到 Kimi CLI")
                print(f"  期望路径: {KIMI_BIN}")
                print("  请安装 Kimi Code 客户端")
                return

        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", exe_path],
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_CONSOLE
                if sys.platform == "win32" else 0,
            )
            print(f"  ✅ 主战窗口已拉起 (Kimi)")
        except Exception as e:
            logging.warning("Failed to launch Kimi Code: %s", str(e)[:120])
            print("  ⚠️ 拉起 Kimi 失败，请手动启动。")

    def stop_all(self) -> None:
        killed = self.proc_mgr.load_and_kill()
        if killed:
            print(f"  已停止 {killed} 个运行中的服务。")
        else:
            print("  没有运行中的服务（未找到 PID 文件）。")


TITLE_ART = r"""
   ╔══════════════════════════════════════════════╗
   ║           九 兽 互 联 启 动 器              ║
   ║     CRUX · Claude · Codex · Kimi            ║
   ║     Copilot · Qoder · CodeBuddy · ZCode     ║
   ║         全 MCP 网格互联 · 一键拉起           ║
   ╚══════════════════════════════════════════════╝
"""


def _interactive_menu() -> None:
    """Interactive menu mode — the default when double-clicked."""
    launcher = MeshLauncher()

    while True:
        print()
        print("  [1] 健康检查 (验证全部连通性)")
        print("  [2] 完整启动 (检查 + 拉起持久服务)")
        print("  [3] 一键停止 (关闭所有持久服务)")
        print("  [4] 快速启动 (跳过检查，直接拉起)")
        print("  [5] 启动并退出 (拉起服务后关闭面板)")
        print("  [0] 退出")
        print()
        try:
            choice = input("  请选择 [0-5]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出...")
            break

        if choice == "1":
            print("\n  正在健康检查...\n")
            t0 = time.monotonic()
            launcher.health_check_all()
            elapsed = time.monotonic() - t0
            launcher.show_dashboard(elapsed)
            # Also show TRM
            try:
                trm_text = launcher.discover_trm()
                print(f"  {trm_text}")
            except Exception as e:
                logging.debug("TRM discovery in menu failed: %s", str(e)[:120])

        elif choice == "2":
            print("\n  正在健康检查...\n")
            t0 = time.monotonic()
            launcher.health_check_all()
            elapsed = time.monotonic() - t0
            launcher.show_dashboard(elapsed)
            try:
                trm_text = launcher.discover_trm()
                print(f"  {trm_text}")
            except Exception as e:
                logging.debug("TRM discovery failed: %s", str(e)[:120])
            launcher.start_persistent()

        elif choice == "3":
            launcher.stop_all()

        elif choice == "4":
            launcher.start_persistent()

        elif choice == "5":
            print("\n  正在健康检查...\n")
            t0 = time.monotonic()
            launcher.health_check_all()
            elapsed = time.monotonic() - t0
            launcher.show_dashboard(elapsed)
            try:
                trm_text = launcher.discover_trm()
                print(f"  {trm_text}")
            except Exception as e:
                logging.debug("TRM discovery failed: %s", str(e)[:120])
            launcher.start_persistent()
            print("  正在拉起主战窗口 (Codex)...")
            launcher.launch_main_window()
            print("  服务已后台运行，主战窗口已打开。")
            break

        elif choice == "0":
            print("  再见。")
            break
        else:
            print("  无效选择，请输入 0-4。")


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="Nine Beasts MESH Launcher — one-click startup for all AI tools"
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

    # If no flags → interactive menu mode (for double-click users)
    has_flags = args.start or args.stop or args.status or args.no_check or args.launch
    if not has_flags:
        print(TITLE_ART)
        _interactive_menu()
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
