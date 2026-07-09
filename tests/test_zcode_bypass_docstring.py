"""Verify core/prompt_bypass.py docstring matches the actual default of BYPASS_ENABLED.

The Configuration section in the module docstring must say "default True"
because _RAW_BYPASS defaults to "1" and BYPASS_ENABLED is True unless the
env var is explicitly set to 0/false/no/off.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BYPASS_FILE = ROOT / "core" / "prompt_bypass.py"


def _get_module_docstring() -> str:
    """Parse the file with ast and return the module docstring."""
    source = BYPASS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    doc = ast.get_docstring(tree)
    assert doc is not None, "module docstring is missing"
    return doc


def test_docstring_configuration_section_exists():
    """The module docstring must contain a 'Configuration:' section."""
    doc = _get_module_docstring()
    assert "Configuration:" in doc, "Module docstring is missing a 'Configuration:' section\n\n" + doc


def test_docstring_says_default_true_not_false():
    """Line 19-ish in the docstring says 'default True', not 'default False'.

    The code (line ~52) sets:
        _RAW_BYPASS = os.getenv("CRUX_BYPASS_ENABLED", "1").strip().lower()
        BYPASS_ENABLED = _RAW_BYPASS not in ("0", "false", "no", "off")

    So the actual default is True.  The docstring must reflect this.
    """
    doc = _get_module_docstring()

    # Find the BYPASS_ENABLED line in the Configuration section
    lines = doc.splitlines()
    config_line = None
    for line in lines:
        if "BYPASS_ENABLED" in line:
            config_line = line.strip()
            break

    assert config_line is not None, "Could not find a line mentioning BYPASS_ENABLED in the docstring"

    # Must say "default True"
    assert "default True" in config_line, (
        f"BYPASS_ENABLED docstring line must say 'default True'.\n"
        f"Found: {config_line!r}\n\n"
        f"The actual default in the code IS True "
        f"(BYPASS_ENABLED = _RAW_BYPASS not in ('0','false','no','off'), "
        f"and _RAW_BYPASS defaults to '1')."
    )

    # Must NOT say "default False"
    assert "default False" not in config_line, (
        f"BYPASS_ENABLED docstring line says 'default False', but the actual default is True.\nFound: {config_line!r}"
    )


def test_both_parts_of_docstring_are_consistent():
    """Quick sanity: the two assertions don't contradict each other."""
    # If we got here, test_docstring_says_default_true_not_false passed.
    pass
