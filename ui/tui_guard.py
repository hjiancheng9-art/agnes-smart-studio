"""TUI regression guard — validates critical invariants that agents keep reverting.

Run: python ui/tui_guard.py
Also called by pre-commit quality gates.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TUI_FILE = ROOT / "ui" / "tui_control.py"


def check_no_eager_single_letter() -> list[str]:
    """Eager single-letter bindings block typing. Agents keep adding them back."""
    if not TUI_FILE.exists():
        return ["tui_v2.py not found"]
    source = TUI_FILE.read_text(encoding="utf-8")
    # Find @kb.add("X", eager=True) where X is a single letter
    pattern = r'@kb\.add\("([a-zA-Z])",\s*eager=True\)'
    matches = re.findall(pattern, source)
    if matches:
        return [f"Eager single-letter binding on '{m}' — blocks typing. Use filter=Condition instead." for m in matches]
    return []


def check_no_eager_ctrl_m() -> list[str]:
    """Ctrl+M == Enter in most terminals. Eager binding breaks input."""
    if not TUI_FILE.exists():
        return []
    source = TUI_FILE.read_text(encoding="utf-8")
    if re.search(r'@kb\.add\("c-m",\s*eager=True\)', source):
        return ["Eager Ctrl+M binding — conflicts with Enter key"]
    return []


def check_vim_bindings_use_filter() -> list[str]:
    """Vim hjkl must use filter=_vim_mode, not eager+return."""
    if not TUI_FILE.exists():
        return []
    source = TUI_FILE.read_text(encoding="utf-8")
    issues = []
    for key in ("j", "k", "i", "G"):
        pattern = rf'@kb\.add\("{key}",\s*eager=True\)'
        if re.search(pattern, source):
            issues.append(f"Eager Vim binding on '{key}' — use filter=_vim_mode instead")
    return issues


def check_focus_state_contract() -> list[str]:
    """FocusState.prev() and .next() must return valid indices."""
    from ui.input_router import FocusState

    issues = []
    fs = FocusState()
    fs.total = 5
    # prev() on disabled FocusState should enable and set to last
    idx = fs.prev()
    if idx != 4:
        issues.append(f"FocusState.prev() initial returned {idx}, expected 4")
    # next() should wrap at end
    fs.index = 4
    idx2 = fs.next()
    if idx2 != 4:
        issues.append(f"FocusState.next() at end returned {idx2}, expected 4 (clamped)")
    return issues


def check_message_store_contract() -> list[str]:
    """MessageStore.last_assistant() must handle empty store."""
    from ui.message_store import MessageStore

    issues = []
    store = MessageStore()
    if store.last_assistant() is not None:
        issues.append("last_assistant() on empty store returned non-None")
    store.append("user", "hello")
    if store.last_assistant() is not None:
        issues.append("last_assistant() with no assistant messages returned non-None")
    store.append("assistant", "hi there")
    msg = store.last_assistant()
    if msg is None or msg.text != "hi there":
        issues.append(f"last_assistant() returned wrong message: {msg}")
    return issues


def check_methodology_not_blocks_writes_by_default() -> list[str]:
    """Fresh MethodologyState must not block writes (no stale TDD phase)."""
    from core.methodology import get_methodology_state, methodology_pre_check, reset_methodology_state

    issues = []
    reset_methodology_state()
    state = get_methodology_state()
    if state.tdd_phase != "":
        issues.append(f"Fresh MethodologyState has tdd_phase={state.tdd_phase!r}, expected ''")
    # write to a normal file should be allowed
    allowed, _ = methodology_pre_check("write_file", {"path": "test_normal.py"})
    if not allowed:
        issues.append("Fresh state blocks write_file — likely stale TDD phase")
    return issues


# ═══════════════════════════════════════════════════════════════

CHECKS = [
    ("eager-single-letter", check_no_eager_single_letter),
    ("eager-ctrl-m", check_no_eager_ctrl_m),
    ("vim-filter", check_vim_bindings_use_filter),
    ("focus-state-contract", check_focus_state_contract),
    ("message-store-contract", check_message_store_contract),
    ("methodology-no-stale-tdd", check_methodology_not_blocks_writes_by_default),
]


def main():
    all_ok = True
    for name, check_fn in CHECKS:
        try:
            issues = check_fn()
        except Exception as e:
            print(f"  ❌ {name}: crashed — {e}")
            all_ok = False
            continue
        if issues:
            for issue in issues:
                print(f"  ❌ {name}: {issue}")
            all_ok = False
        else:
            print(f"  ✅ {name}")

    if all_ok:
        print("\n✅ All TUI guards pass")
    else:
        print("\n❌ TUI guards FAILED — fix before committing")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
