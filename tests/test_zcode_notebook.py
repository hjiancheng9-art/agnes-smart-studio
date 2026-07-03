"""RED phase tests for core/notebook.py.

NotebookManager open/edit/add/run/save lifecycle, Notebook class, tool executors.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Notebook class tests
# ---------------------------------------------------------------------------


class TestNotebook:
    """Notebook load, cell operations, save, export."""

    @pytest.fixture
    def minimal_nb_path(self):
        """Create a minimal .ipynb file."""
        nb = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": [
                {"cell_type": "code", "source": ["print('hello')\n"], "outputs": [], "execution_count": 0, "metadata": {}},
                {"cell_type": "markdown", "source": ["# Title\n"], "metadata": {}},
            ],
        }
        with tempfile.NamedTemporaryFile(suffix=".ipynb", mode="w", delete=False) as f:
            json.dump(nb, f)
            f.flush()
            path = f.name
        yield path
        os.unlink(path)

    def test_load_notebook(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        assert len(nb.cells) == 2
        assert nb.cells[0].cell_type == "code"
        assert nb.cells[0].source == "print('hello')\n"
        assert nb.cells[1].cell_type == "markdown"
        assert nb._nbformat == 4

    def test_file_not_found_raises(self):
        from core.notebook import Notebook

        with pytest.raises(FileNotFoundError):
            Notebook("/nonexistent/notebook.ipynb")

    def test_get_cell(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        cell = nb.get_cell(0)
        assert cell.cell_type == "code"
        assert cell.index == 0

    def test_get_cell_out_of_range_raises(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        with pytest.raises(IndexError):
            nb.get_cell(99)
        with pytest.raises(IndexError):
            nb.get_cell(-1)

    def test_edit_cell(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        cell = nb.edit_cell(0, "print('updated')\n")
        assert cell.source == "print('updated')\n"
        assert nb.get_cell(0).source == "print('updated')\n"

    def test_edit_cell_out_of_range_raises(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        with pytest.raises(IndexError):
            nb.edit_cell(99, "x")

    def test_add_cell_append(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        initial = len(nb.cells)
        cell = nb.add_cell(cell_type="code", source="x = 1\n")
        assert len(nb.cells) == initial + 1
        assert cell.index == initial  # appended at end
        assert nb.cells[-1].source == "x = 1\n"

    def test_add_cell_insert_at_index(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        nb.add_cell(cell_type="markdown", source="# inserted\n", index=0)
        assert len(nb.cells) == 3
        assert nb.cells[0].cell_type == "markdown"
        assert nb.cells[0].index == 0
        assert nb.cells[1].index == 1  # re-indexed

    def test_remove_cell(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        assert nb.remove_cell(0) is True
        assert len(nb.cells) == 1
        assert nb.cells[0].index == 0

    def test_remove_cell_out_of_range(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        assert nb.remove_cell(99) is False
        assert nb.remove_cell(-1) is False

    def test_move_cell(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        # Move cell 0 to position 1
        assert nb.move_cell(0, 1) is True
        # Cell that was at index 0 is now at index 1
        # After move, indexes are recalculated
        assert nb.cells[0].index == 0
        assert nb.cells[1].index == 1

    def test_move_cell_out_of_range(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        assert nb.move_cell(99, 0) is False
        assert nb.move_cell(0, 99) is False

    def test_save_preserves_content(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        nb.edit_cell(0, "print('saved')\n")
        saved = nb.save()
        # Reload and verify (save joins source lines, trailing \n may be normalized)
        nb2 = Notebook(saved)
        assert "print('saved')" in nb2.get_cell(0).source

    def test_save_to_different_path(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        with tempfile.NamedTemporaryFile(suffix=".ipynb", mode="w", delete=False) as f:
            new_path = f.name
        try:
            saved = nb.save(path=new_path)
            assert saved == new_path
            assert os.path.isfile(new_path)
        finally:
            os.unlink(new_path)

    def test_summary(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        s = nb.summary()
        assert s["cell_count"] == 2
        assert s["code_cells"] == 1
        assert s["markdown_cells"] == 1
        assert s["total_lines"] >= 1

    def test_to_markdown(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        md = nb.to_markdown()
        assert "```python" in md
        assert "print('hello')" in md
        assert "# Title" in md

    def test_run_cell_code(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        # Edit to a known-good snippet
        nb.edit_cell(0, "print('ran ok')\n")
        output = nb.run_cell(0)
        assert "stdout" in output
        assert output["exit_code"] == 0
        assert nb.cells[0].execution_count == 1

    def test_run_cell_non_code_raises(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        with pytest.raises(ValueError):
            nb.run_cell(1)  # markdown cell

    def test_run_all_executes_code_cells(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        # Add another code cell
        nb.add_cell(cell_type="code", source="x = 42\n")
        nb.add_cell(cell_type="markdown", source="# ignored\n")
        outputs = nb.run_all()
        # Only code cells executed
        assert len(outputs) == 2

    def test_run_cell_error_exit_code(self, minimal_nb_path):
        from core.notebook import Notebook

        nb = Notebook(minimal_nb_path)
        nb.edit_cell(0, "import sys; sys.exit(1)\n")
        output = nb.run_cell(0)
        assert output["exit_code"] == 1


# ---------------------------------------------------------------------------
# NotebookManager tests
# ---------------------------------------------------------------------------


class TestNotebookManager:
    """Manager create, open, list."""

    def test_create_notebook(self):
        from core.notebook import NotebookManager

        mgr = NotebookManager()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test_create.ipynb")
            nb = mgr.create(path)
            assert os.path.isfile(path)
            assert len(nb.cells) == 0
            assert nb._nbformat == 4

    def test_open_notebook(self):
        from core.notebook import NotebookManager

        # Create a real .ipynb file
        nb_data = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [{"cell_type": "code", "source": ["x = 1\n"], "outputs": [], "execution_count": 0, "metadata": {}}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.ipynb")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(nb_data, f)
            mgr = NotebookManager()
            nb = mgr.open(path)
            assert len(nb.cells) == 1

    def test_open_caches_notebook(self):
        from core.notebook import NotebookManager

        nb_data = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [{"cell_type": "code", "source": ["x = 1\n"], "outputs": [], "execution_count": 0, "metadata": {}}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.ipynb")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(nb_data, f)
            mgr = NotebookManager()
            nb1 = mgr.open(path)
            nb2 = mgr.open(path)
            assert nb1 is nb2  # cached

    def test_list_notebooks(self):
        from core.notebook import NotebookManager

        mgr = NotebookManager()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.ipynb").write_text("{}")
            (Path(tmp) / "b.ipynb").write_text("{}")
            (Path(tmp) / "c.txt").write_text("")
            files = mgr.list_notebooks(tmp)
            assert len(files) == 2
            assert all(f.endswith(".ipynb") for f in files)


# ---------------------------------------------------------------------------
# Tool executor tests
# ---------------------------------------------------------------------------


class TestNotebookToolExecutors:
    """notebook_open/edit_cell/add_cell/run_cell/save executors."""

    @pytest.fixture
    def notebook_path(self):
        nb_data = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {"cell_type": "code", "source": ["print(1)\n"], "outputs": [], "execution_count": 0, "metadata": {}},
                {"cell_type": "markdown", "source": ["# md\n"], "metadata": {}},
            ],
        }
        with tempfile.NamedTemporaryFile(suffix=".ipynb", mode="w", delete=False) as f:
            json.dump(nb_data, f)
            f.flush()
            path = f.name
        yield path
        os.unlink(path)

    def test_notebook_open_executor(self, notebook_path):
        from core.notebook import _exec_notebook_open

        result = json.loads(_exec_notebook_open({"path": notebook_path}))
        assert "cells" in result
        assert "summary" in result
        assert len(result["cells"]) == 2

    def test_notebook_open_missing_path(self):
        from core.notebook import _exec_notebook_open

        result = json.loads(_exec_notebook_open({}))
        assert "error" in result

    def test_notebook_open_nonexistent_file(self):
        from core.notebook import _exec_notebook_open

        result = json.loads(_exec_notebook_open({"path": "/nonexistent/nb.ipynb"}))
        assert "error" in result

    def test_notebook_edit_cell(self, notebook_path):
        from core.notebook import _exec_notebook_edit_cell

        result = json.loads(_exec_notebook_edit_cell({"path": notebook_path, "cell_index": 0, "source": "print(42)\n"}))
        assert "cell" in result
        assert result["cell"]["index"] == 0

    def test_notebook_edit_cell_missing_args(self):
        from core.notebook import _exec_notebook_edit_cell

        result = json.loads(_exec_notebook_edit_cell({"path": "x"}))
        assert "error" in result

    def test_notebook_add_cell_append(self, notebook_path):
        from core.notebook import _exec_notebook_add_cell

        result = json.loads(_exec_notebook_add_cell({"path": notebook_path, "cell_type": "code", "source": "y = 2\n"}))
        assert "cell" in result
        assert result["cell"]["cell_type"] == "code"

    def test_notebook_add_cell_missing_path(self):
        from core.notebook import _exec_notebook_add_cell

        result = json.loads(_exec_notebook_add_cell({}))
        assert "error" in result

    def test_notebook_run_cell(self, notebook_path):
        from core.notebook import _exec_notebook_run_cell

        result = json.loads(_exec_notebook_run_cell({"path": notebook_path, "cell_index": 0}))
        assert "stdout" in result
        assert result["exit_code"] == 0

    def test_notebook_run_cell_missing_args(self):
        from core.notebook import _exec_notebook_run_cell

        result = json.loads(_exec_notebook_run_cell({}))
        assert "error" in result

    def test_notebook_save(self, notebook_path):
        from core.notebook import _exec_notebook_save

        result = json.loads(_exec_notebook_save({"path": notebook_path}))
        assert "saved" in result
        assert "summary" in result

    def test_notebook_save_missing_path(self):
        from core.notebook import _exec_notebook_save

        result = json.loads(_exec_notebook_save({}))
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool definition structure tests
# ---------------------------------------------------------------------------


class TestNotebookToolDefs:
    """Validate tool definitions and executor map consistency."""

    def test_all_tools_have_required_structure(self):
        from core.notebook import NOTEBOOK_TOOL_DEFS

        tool_names = set()
        for td in NOTEBOOK_TOOL_DEFS:
            assert td["type"] == "function"
            fn = td["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert "properties" in fn["parameters"]
            assert "required" in fn["parameters"]
            tool_names.add(fn["name"])
        assert len(tool_names) == len(NOTEBOOK_TOOL_DEFS)

    def test_executor_map_covers_all_tools(self):
        from core.notebook import NOTEBOOK_TOOL_DEFS, NOTEBOOK_EXECUTOR_MAP

        tool_names = {td["function"]["name"] for td in NOTEBOOK_TOOL_DEFS}
        assert tool_names == set(NOTEBOOK_EXECUTOR_MAP.keys())

    def test_executor_map_callables(self):
        from core.notebook import NOTEBOOK_EXECUTOR_MAP

        for name, fn in NOTEBOOK_EXECUTOR_MAP.items():
            assert callable(fn), f"{name} executor is not callable"


# ---------------------------------------------------------------------------
# NotebookCell dataclass
# ---------------------------------------------------------------------------


class TestNotebookCell:
    """NotebookCell dataclass invariants."""

    def test_default_values(self):
        from core.notebook import NotebookCell

        cell = NotebookCell(index=0, cell_type="code", source="")
        assert cell.outputs == []
        assert cell.execution_count == 0
        assert cell.metadata == {}

    def test_field_assignment(self):
        from core.notebook import NotebookCell

        cell = NotebookCell(index=5, cell_type="markdown", source="# hi\n", execution_count=3)
        assert cell.index == 5
        assert cell.cell_type == "markdown"
        assert cell.source == "# hi\n"
        assert cell.execution_count == 3
