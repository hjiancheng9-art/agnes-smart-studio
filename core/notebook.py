"""Jupyter notebook (.ipynb) editing module for crux-smart-studio.

Provides classes and tool definitions for opening, editing, executing,
and saving Jupyter notebooks programmatically.

⚠ EXPERIMENTAL — 未接通 runtime：NotebookManager 与 NOTEBOOK_EXECUTOR_MAP 已就位，
但 tools.json 未注册、ChatSession 未 import。接入前接口可能调整。
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

__all__ = [
    "NOTEBOOK_EXECUTOR_MAP",
    "NOTEBOOK_TOOL_DEFS",
    "Notebook",
    "NotebookCell",
    "NotebookManager",
]


@dataclass
class NotebookCell:
    """Represents a single cell in a Jupyter notebook."""

    index: int
    cell_type: str  # "code", "markdown", "raw"
    source: str
    outputs: list = field(default_factory=list)
    execution_count: int = 0
    metadata: dict = field(default_factory=dict)


class Notebook:
    """Represents a Jupyter notebook loaded from a .ipynb file."""

    def __init__(self, path: str) -> None:
        """Load a notebook from a .ipynb file.

        Args:
            path: Path to the .ipynb file.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        self.path = path
        self.cells: list[NotebookCell] = []
        self._nbformat = 4
        self._nbformat_minor = 5
        self._metadata: dict = {}

        if not os.path.isfile(path):
            raise FileNotFoundError(f"Notebook file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self._nbformat = data.get("nbformat", 4)
        self._nbformat_minor = data.get("nbformat_minor", 5)
        self._metadata = data.get("metadata", {})

        for i, cell_data in enumerate(data.get("cells", [])):
            source = "".join(cell_data.get("source", []))
            cell = NotebookCell(
                index=i,
                cell_type=cell_data.get("cell_type", "code"),
                source=source,
                outputs=cell_data.get("outputs", []),
                execution_count=cell_data.get("execution_count", 0),
                metadata=cell_data.get("metadata", {}),
            )
            self.cells.append(cell)

    def add_cell(self, cell_type: str = "code", source: str = "", index: int | None = None) -> NotebookCell:
        """Add a new cell to the notebook.

        Args:
            cell_type: Type of cell ("code", "markdown", "raw").
            source: Cell source content.
            index: Position to insert at. If None, appends at end.

        Returns:
            The newly created NotebookCell.
        """
        cell = NotebookCell(
            index=0,
            cell_type=cell_type,
            source=source,
        )

        if index is None:
            self.cells.append(cell)
        else:
            self.cells.insert(index, cell)

        # Re-index all cells after insertion
        for i, c in enumerate(self.cells):
            c.index = i

        return cell

    def remove_cell(self, index: int) -> bool:
        """Remove a cell at the given index.

        Args:
            index: 0-based cell position to remove.

        Returns:
            True if the cell was removed, False if index is out of range.
        """
        if index < 0 or index >= len(self.cells):
            return False

        self.cells.pop(index)

        # Re-index remaining cells
        for i, c in enumerate(self.cells):
            c.index = i

        return True

    def get_cell(self, index: int) -> NotebookCell:
        """Get a cell at the given index.

        Args:
            index: 0-based cell position.

        Returns:
            The NotebookCell at that position.

        Raises:
            IndexError: If index is out of range.
        """
        if index < 0 or index >= len(self.cells):
            raise IndexError(f"Cell index {index} out of range (0-{len(self.cells) - 1})")
        return self.cells[index]

    def edit_cell(self, index: int, source: str) -> NotebookCell:
        """Edit the source content of a cell.

        Args:
            index: 0-based cell position.
            source: New source content for the cell.

        Returns:
            The updated NotebookCell.

        Raises:
            IndexError: If index is out of range.
        """
        cell = self.get_cell(index)
        cell.source = source
        return cell

    def move_cell(self, from_index: int, to_index: int) -> bool:
        """Move a cell from one position to another.

        Args:
            from_index: Current position of the cell.
            to_index: Desired new position.

        Returns:
            True if the move succeeded, False if indices are out of range.
        """
        if from_index < 0 or from_index >= len(self.cells):
            return False
        if to_index < 0 or to_index >= len(self.cells):
            return False

        cell = self.cells.pop(from_index)
        self.cells.insert(to_index, cell)

        # Re-index all cells after move
        for i, c in enumerate(self.cells):
            c.index = i

        return True

    def run_cell(self, index: int) -> dict:
        """Execute a code cell using subprocess.

        Args:
            index: 0-based cell position. Must be a code cell.

        Returns:
            Dict with "stdout", "stderr", and "exit_code" keys.

        Raises:
            IndexError: If index is out of range.
            ValueError: If cell is not a code cell.
        """
        cell = self.get_cell(index)

        if cell.cell_type != "code":
            raise ValueError(f"Cell {index} is type '{cell.cell_type}', not 'code'")

        result = subprocess.run(
            [sys.executable, "-c", cell.source],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )

        output = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

        # Update cell outputs and execution count
        cell.outputs = [output]
        cell.execution_count += 1

        return output

    def run_all(self) -> list[dict]:
        """Execute all code cells in order.

        Returns:
            List of output dicts for each code cell that was executed.
        """
        results = []
        for cell in self.cells:
            if cell.cell_type == "code":
                results.append(self.run_cell(cell.index))
        return results

    def save(self, path: str | None = None) -> str:
        """Save the notebook to a .ipynb file.

        Args:
            path: Destination path. If None, saves to the original path.

        Returns:
            The path where the notebook was saved.
        """
        save_path = path or self.path

        cells_data = []
        for cell in self.cells:
            cell_dict = {
                "cell_type": cell.cell_type,
                "source": cell.source.split("\n"),
                "metadata": cell.metadata,
            }

            if cell.cell_type == "code":
                cell_dict["outputs"] = cell.outputs
                cell_dict["execution_count"] = cell.execution_count
            else:
                cell_dict["outputs"] = []

            cells_data.append(cell_dict)

        notebook_data = {
            "nbformat": self._nbformat,
            "nbformat_minor": self._nbformat_minor,
            "metadata": self._metadata,
            "cells": cells_data,
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(notebook_data, f, indent=1, ensure_ascii=False)

        return save_path

    def summary(self) -> dict:
        """Return a summary of the notebook.

        Returns:
            Dict with cell_count, code_cells, markdown_cells, total_lines.
        """
        code_cells = sum(1 for c in self.cells if c.cell_type == "code")
        markdown_cells = sum(1 for c in self.cells if c.cell_type == "markdown")
        total_lines = sum(len(c.source.split("\n")) for c in self.cells)

        return {
            "cell_count": len(self.cells),
            "code_cells": code_cells,
            "markdown_cells": markdown_cells,
            "total_lines": total_lines,
        }

    def to_markdown(self) -> str:
        """Convert the notebook to a markdown document.

        Returns:
            Markdown string representation of all cells.
        """
        lines = []
        for cell in self.cells:
            if cell.cell_type == "markdown":
                lines.append(cell.source)
            elif cell.cell_type == "code":
                lines.append(f"```python\n{cell.source}\n```")
                if cell.outputs:
                    for output in cell.outputs:
                        if isinstance(output, dict) and output.get("stdout"):
                            lines.append(f"```\n{output['stdout']}\n```")
            elif cell.cell_type == "raw":
                lines.append(cell.source)
            lines.append("")  # blank line between cells

        return "\n".join(lines)


class NotebookManager:
    """Manages multiple notebook instances."""

    def __init__(self) -> None:
        """Initialize with no notebooks loaded."""
        self._notebooks: dict[str, Notebook] = {}

    def open(self, path: str) -> Notebook:
        """Open an existing notebook file.

        Args:
            path: Path to the .ipynb file.

        Returns:
            The loaded Notebook instance.
        """
        if path in self._notebooks:
            return self._notebooks[path]

        nb = Notebook(path)
        self._notebooks[path] = nb
        return nb

    def create(self, path: str) -> Notebook:
        """Create a new empty notebook and save it.

        Args:
            path: Path for the new .ipynb file.

        Returns:
            The newly created Notebook instance.
        """
        # Create minimal notebook data
        notebook_data = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {
                    "name": "python",
                    "version": sys.version.split()[0],
                },
            },
            "cells": [],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(notebook_data, f, indent=1, ensure_ascii=False)

        nb = Notebook(path)
        self._notebooks[path] = nb
        return nb

    def list_notebooks(self, directory: str = ".") -> list[str]:
        """Find all .ipynb files in a directory.

        Args:
            directory: Directory to search in.

        Returns:
            List of .ipynb file paths found.
        """
        result = []
        for root, _dirs, files in os.walk(directory):
            for fname in files:
                if fname.endswith(".ipynb"):
                    result.append(os.path.join(root, fname))
        return sorted(result)


# --- Tool definitions for AI agent integration ---


def _exec_notebook_open(params: dict) -> str:
    """Execute notebook_open tool."""
    path = params.get("path")
    if not path:
        return json.dumps({"error": "path is required"}, ensure_ascii=False)

    try:
        mgr = NotebookManager()
        nb = mgr.open(path)
        cells_info = [
            {
                "index": c.index,
                "cell_type": c.cell_type,
                "source": c.source[:200] + ("..." if len(c.source) > 200 else ""),
            }
            for c in nb.cells
        ]
        return json.dumps({"cells": cells_info, "summary": nb.summary()}, ensure_ascii=False)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _exec_notebook_edit_cell(params: dict) -> str:
    """Execute notebook_edit_cell tool."""
    path = params.get("path")
    cell_index = params.get("cell_index")
    source = params.get("source")

    if not path or cell_index is None or source is None:
        return json.dumps({"error": "path, cell_index, and source are required"}, ensure_ascii=False)

    try:
        mgr = NotebookManager()
        nb = mgr.open(path)
        cell = nb.edit_cell(int(cell_index), source)
        nb.save()
        return json.dumps(
            {
                "cell": {
                    "index": cell.index,
                    "cell_type": cell.cell_type,
                    "source": cell.source[:200] + ("..." if len(cell.source) > 200 else ""),
                },
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _exec_notebook_add_cell(params: dict) -> str:
    """Execute notebook_add_cell tool."""
    path = params.get("path")
    cell_type = params.get("cell_type", "code")
    source = params.get("source", "")
    index = params.get("index")  # optional, None = append

    if not path:
        return json.dumps({"error": "path is required"}, ensure_ascii=False)

    try:
        mgr = NotebookManager()
        nb = mgr.open(path)
        insert_at = int(index) if index is not None else None
        cell = nb.add_cell(cell_type=cell_type, source=source, index=insert_at)
        nb.save()
        return json.dumps(
            {
                "cell": {
                    "index": cell.index,
                    "cell_type": cell.cell_type,
                    "source": cell.source[:200] + ("..." if len(cell.source) > 200 else ""),
                },
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _exec_notebook_run_cell(params: dict) -> str:
    """Execute notebook_run_cell tool."""
    path = params.get("path")
    cell_index = params.get("cell_index")

    if not path or cell_index is None:
        return json.dumps({"error": "path and cell_index are required"}, ensure_ascii=False)

    try:
        mgr = NotebookManager()
        nb = mgr.open(path)
        output = nb.run_cell(int(cell_index))
        nb.save()
        return json.dumps(output, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _exec_notebook_save(params: dict) -> str:
    """Execute notebook_save tool."""
    path = params.get("path")

    if not path:
        return json.dumps({"error": "path is required"}, ensure_ascii=False)

    try:
        mgr = NotebookManager()
        nb = mgr.open(path)
        saved_path = nb.save()
        return json.dumps({"saved": saved_path, "summary": nb.summary()}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


NOTEBOOK_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "notebook_open",
            "description": "Open a Jupyter notebook file and return its cell list and summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the .ipynb file",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_edit_cell",
            "description": "Edit the source content of a cell in a notebook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the .ipynb file"},
                    "cell_index": {"type": "integer", "description": "0-based index of the cell to edit"},
                    "source": {"type": "string", "description": "New source content for the cell"},
                },
                "required": ["path", "cell_index", "source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_add_cell",
            "description": "Add a new cell to a notebook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the .ipynb file"},
                    "cell_type": {
                        "type": "string",
                        "description": "Type of cell: code, markdown, or raw (default: code)",
                        "enum": ["code", "markdown", "raw"],
                    },
                    "source": {"type": "string", "description": "Cell source content (default: empty)"},
                    "index": {"type": "integer", "description": "Position to insert at. If omitted, appends at end."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_run_cell",
            "description": "Execute a code cell in a notebook and return stdout/stderr/exit_code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the .ipynb file"},
                    "cell_index": {"type": "integer", "description": "0-based index of the code cell to execute"},
                },
                "required": ["path", "cell_index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_save",
            "description": "Save a notebook to its .ipynb file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the .ipynb file"},
                },
                "required": ["path"],
            },
        },
    },
]

NOTEBOOK_EXECUTOR_MAP = {
    "notebook_open": _exec_notebook_open,
    "notebook_edit_cell": _exec_notebook_edit_cell,
    "notebook_add_cell": _exec_notebook_add_cell,
    "notebook_run_cell": _exec_notebook_run_cell,
    "notebook_save": _exec_notebook_save,
}
