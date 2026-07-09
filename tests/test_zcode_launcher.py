"""Tests for launcher.py — BeastConfig, ProcessManager, MeshLauncher, health checks."""

from pathlib import Path

from launcher import (
    BEAST_ICONS,
    BEASTS,
    PID_FILE,
    PYTHON,
    ROOT,
    STATUS_COLORS,
    STATUS_GLYPHS,
    BeastConfig,
    HealthResult,
    MeshLauncher,
    ProcessManager,
    print_ascii_dashboard,
)

# ── BeastConfig ──────────────────────────────────────────────────────────────


def test_beast_config_creation():
    """BeastConfig can be created with name, role, icon, binary."""
    bc = BeastConfig(name="test-beast", role="tester", icon="T", binary="python")
    assert bc.name == "test-beast"
    assert bc.role == "tester"
    assert bc.icon == "T"
    assert bc.binary == "python"


def test_beast_config_defaults():
    """BeastConfig defaults: bridge_script, startup_args, mcp_initialize,
    persistent, timeout, env."""
    bc = BeastConfig(name="d", role="r", icon="i", binary="b")
    assert bc.bridge_script == ""
    assert bc.startup_args == []
    assert bc.mcp_initialize is True
    assert bc.persistent is False
    assert bc.timeout == 15
    assert bc.env == {}


# ── BEASTS dict ──────────────────────────────────────────────────────────────


def test_beasts_contains_crux():
    """BEASTS dict contains 'crux' key."""
    assert "crux" in BEASTS


def test_beasts_contains_claude():
    """BEASTS dict contains 'claude' key."""
    assert "claude" in BEASTS


def test_beasts_crux_persistent():
    """BEASTS['crux'].persistent is True."""
    assert BEASTS["crux"].persistent is True


def test_beasts_claude_persistent():
    """BEASTS['claude'].persistent is True."""
    assert BEASTS["claude"].persistent is True


def test_beasts_crux_name():
    """BEASTS['crux'].name == 'CRUX'."""
    assert BEASTS["crux"].name == "CRUX"


def test_beasts_claude_name():
    """BEASTS['claude'].name == 'Claude Code'."""
    assert BEASTS["claude"].name == "Claude Code"


# ── HealthResult ─────────────────────────────────────────────────────────────


def test_health_result_creation():
    """HealthResult can be created with name, icon, status."""
    hr = HealthResult(name="test", icon="T", status="online")
    assert hr.name == "test"
    assert hr.icon == "T"
    assert hr.status == "online"


def test_health_result_defaults():
    """HealthResult defaults: role, version, latency_ms, error."""
    hr = HealthResult(name="n", icon="i", status="s")
    assert hr.role == ""
    assert hr.version == ""
    assert hr.latency_ms == 0.0
    assert hr.error == ""


# ── MeshLauncher ─────────────────────────────────────────────────────────────


def test_mesh_launcher_empty_results():
    """MeshLauncher() creates instance with empty results."""
    launcher = MeshLauncher()
    assert launcher.results == []


def test_mesh_launcher_proc_mgr():
    """MeshLauncher().proc_mgr is a ProcessManager."""
    launcher = MeshLauncher()
    assert isinstance(launcher.proc_mgr, ProcessManager)


def test_mesh_launcher_discover_trm_returns_string():
    """MeshLauncher().discover_trm() returns a string (may fail gracefully)."""
    launcher = MeshLauncher()
    result = launcher.discover_trm()
    assert isinstance(result, str)


# ── ProcessManager ───────────────────────────────────────────────────────────


def test_process_manager_empty_procs():
    """ProcessManager() creates instance with empty _procs."""
    pm = ProcessManager()
    assert pm._procs == {}


def test_process_manager_running_empty():
    """ProcessManager().running returns empty list initially."""
    pm = ProcessManager()
    assert pm.running == []


def test_process_manager_cleanup_zombies_zero():
    """ProcessManager().cleanup_zombies() returns 0 initially."""
    pm = ProcessManager()
    assert pm.cleanup_zombies() == 0


# ── STATUS_GLYPHS ────────────────────────────────────────────────────────────


def test_status_glyphs_keys():
    """STATUS_GLYPHS has keys: online, degraded, offline."""
    assert "online" in STATUS_GLYPHS
    assert "degraded" in STATUS_GLYPHS
    assert "offline" in STATUS_GLYPHS


# ── STATUS_COLORS ────────────────────────────────────────────────────────────


def test_status_colors_keys():
    """STATUS_COLORS has keys: online, degraded, offline."""
    assert "online" in STATUS_COLORS
    assert "degraded" in STATUS_COLORS
    assert "offline" in STATUS_COLORS


# ── BEAST_ICONS ──────────────────────────────────────────────────────────────


def test_beast_icons_keys():
    """BEAST_ICONS has keys: BAIHU, QINGLONG, ZHUQUE, XUANWU, QILIN,
    TENGSHE, YINGLONG."""
    expected = {"BAIHU", "QINGLONG", "ZHUQUE", "XUANWU", "QILIN", "TENGSHE", "YINGLONG"}
    assert set(BEAST_ICONS.keys()) == expected


# ── Constants ────────────────────────────────────────────────────────────────


def test_python_path():
    """PYTHON path is a string ending with python.exe."""
    assert isinstance(PYTHON, str)
    assert PYTHON.endswith("python.exe")


def test_root_is_path():
    """ROOT is a Path object."""
    assert isinstance(ROOT, Path)


def test_pid_file_ends_with_beasts_pids():
    """PID_FILE is a Path ending with .beasts_pids.json."""
    assert isinstance(PID_FILE, Path)
    assert PID_FILE.name == ".beasts_pids.json"


# ── print_ascii_dashboard ────────────────────────────────────────────────────


def test_print_ascii_dashboard_does_not_raise():
    """print_ascii_dashboard can be called with a list of HealthResult
    without raising."""
    results = [
        HealthResult(name="CRUX", icon="H", status="online"),
        HealthResult(name="Claude Code", icon="B", status="offline"),
    ]
    print_ascii_dashboard(results, elapsed=0.42)


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_beasts_crux_mcp_initialize():
    """BEASTS['crux'].mcp_initialize is True."""
    assert BEASTS["crux"].mcp_initialize is True


def test_beasts_claude_mcp_initialize():
    """BEASTS['claude'].mcp_initialize is True."""
    assert BEASTS["claude"].mcp_initialize is True


def test_beasts_crux_timeout():
    """BEASTS['crux'].timeout == 30."""
    assert BEASTS["crux"].timeout == 30


def test_beasts_claude_timeout():
    """BEASTS['claude'].timeout == 30."""
    assert BEASTS["claude"].timeout == 30
