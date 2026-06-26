"""Unit tests for core/notebook.py — Jupyter notebook 编辑模块。

notebook.py 的 NotebookCell dataclass 与 Notebook 的单元操作（add/remove/
get/edit/move）是纯列表操作，适合单测；run_cell/run_all 触发子进程，跳过。

⚠ 模块自身 docstring 标注 EXPERIMENTAL（未接通 runtime），但内部逻辑稳定可测。

覆盖：
- Notebook 加载（.ipynb JSON → cells，source 拼接，字段默认值）
- add_cell（append / insert / 重新编号）
- remove_cell（命中 / 越界 / 重新编号）
- get_cell / edit_cell（IndexError 契约）
- move_cell（命中 / 越界 / 重新编号）
- summary / to_markdown（纯计算）
- save 往返（save → 重新 load 一致性）
- NotebookManager（open 缓存 / create 最小结构 / list_notebooks）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.notebook import (
    NOTEBOOK_EXECUTOR_MAP,
    NOTEBOOK_TOOL_DEFS,
    Notebook,
    NotebookCell,
    NotebookManager,
)

# ── fixtures ──────────────────────────────────────────────────────


def _write_nb(path: Path, cells: list[dict], **extra) -> Path:
    """写一个最小合法 .ipynb 文件。"""
    data = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
        "cells": cells,
        **extra,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _cell(cell_type: str = "code", source: str | list[str] = "", **extra) -> dict:
    """构造单个 cell JSON。source 可给 str 或 list（模拟真实 ipynb 的行数组）。"""
    if isinstance(source, str):
        source = source.split("\n")  # 模拟 ipynb 的 source 行数组
    return {"cell_type": cell_type, "source": source, "metadata": {}, **extra}


@pytest.fixture
def nb_path(tmp_path: Path) -> Path:
    """一个含 3 个 cell 的 notebook 文件路径。"""
    return _write_nb(
        tmp_path / "demo.ipynb",
        [
            _cell("markdown", "# Title"),
            _cell("code", "print('hi')"),
            _cell("code", "x = 1\nprint(x)"),
        ],
    )


@pytest.fixture
def empty_nb_path(tmp_path: Path) -> Path:
    """空 notebook（无 cells）。"""
    return _write_nb(tmp_path / "empty.ipynb", [])


# ── NotebookCell dataclass ────────────────────────────────────────


def test_notebook_cell_defaults():
    """dataclass 默认值：outputs=[], execution_count=0, metadata={}。"""
    c = NotebookCell(index=0, cell_type="code", source="x")
    assert c.outputs == []
    assert c.execution_count == 0
    assert c.metadata == {}
    # 默认值应是独立实例（field default_factory 保证）
    c2 = NotebookCell(index=1, cell_type="code", source="y")
    c.outputs.append("x")
    assert c2.outputs == []  # 不共享


# ── Notebook 加载 ─────────────────────────────────────────────────


def test_load_reads_cells_and_joins_source(nb_path):
    """加载后 cells 数量正确，source（行数组）被拼接为单字符串。"""
    nb = Notebook(str(nb_path))
    assert len(nb.cells) == 3
    assert nb.cells[0].cell_type == "markdown"
    assert nb.cells[0].source == "# Title"
    # 多行 source 应被 join
    assert "x = 1" in nb.cells[2].source
    assert "print(x)" in nb.cells[2].source


def test_load_assigns_sequential_indices(nb_path):
    """加载后 index 应从 0 顺序递增。"""
    nb = Notebook(str(nb_path))
    assert [c.index for c in nb.cells] == [0, 1, 2]


def test_load_missing_file_raises(tmp_path):
    """加载不存在的文件应抛 FileNotFoundError（docstring 契约）。"""
    with pytest.raises(FileNotFoundError):
        Notebook(str(tmp_path / "ghost.ipynb"))


def test_load_malformed_json_raises(tmp_path):
    """坏 JSON 应抛 json.JSONDecodeError（docstring 契约）。"""
    p = tmp_path / "bad.ipynb"
    p.write_text("{ not valid json }", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        Notebook(str(p))


def test_load_preserves_nbformat_metadata(tmp_path):
    """加载应保留 nbformat / nbformat_minor / metadata。"""
    p = _write_nb(
        tmp_path / "meta.ipynb",
        [],
        nbformat=4,
        nbformat_minor=5,
        metadata={"kernelspec": {"name": "custom"}},
    )
    nb = Notebook(str(p))
    assert nb._nbformat == 4
    assert nb._nbformat_minor == 5
    assert nb._metadata["kernelspec"]["name"] == "custom"


# ── add_cell ──────────────────────────────────────────────────────


def test_add_cell_append_default(empty_nb_path):
    """不指定 index → 追加到末尾。"""
    nb = Notebook(str(empty_nb_path))
    cell = nb.add_cell(cell_type="code", source="print(1)")
    assert cell.source == "print(1)"
    assert len(nb.cells) == 1
    assert nb.cells[0].index == 0


def test_add_cell_insert_at_index(nb_path):
    """指定 index → 插入到该位置，后续 cell index 重排。"""
    nb = Notebook(str(nb_path))
    nb.add_cell(cell_type="raw", source="inserted", index=1)
    assert nb.cells[1].source == "inserted"
    # 全部 index 应连续
    assert [c.index for c in nb.cells] == [0, 1, 2, 3]


def test_add_cell_reindexes_all(nb_path):
    """插入后所有 cell 的 index 应重新计算（无重复/空洞）。"""
    nb = Notebook(str(nb_path))
    nb.add_cell(source="new", index=0)
    indices = [c.index for c in nb.cells]
    assert indices == list(range(len(nb.cells)))


# ── remove_cell ───────────────────────────────────────────────────


def test_remove_cell_success(nb_path):
    """命中索引返回 True 并删除。"""
    nb = Notebook(str(nb_path))
    assert nb.remove_cell(1) is True
    assert len(nb.cells) == 2
    # 剩余 cell index 重排
    assert [c.index for c in nb.cells] == [0, 1]


def test_remove_cell_out_of_range_returns_false(nb_path):
    """越界索引返回 False（不抛异常，docstring 契约）。"""
    nb = Notebook(str(nb_path))
    assert nb.remove_cell(99) is False
    assert nb.remove_cell(-1) is False
    assert len(nb.cells) == 3  # 未改变


def test_remove_only_cell_leaves_empty(empty_nb_path):
    """删最后一个 cell 后 cells 为空。"""
    nb = Notebook(str(empty_nb_path))
    nb.add_cell(source="x")
    assert nb.remove_cell(0) is True
    assert nb.cells == []


# ── get_cell / edit_cell ──────────────────────────────────────────


def test_get_cell_returns_cell(nb_path):
    """命中索引返回对应 cell。"""
    nb = Notebook(str(nb_path))
    assert nb.get_cell(0).cell_type == "markdown"


def test_get_cell_out_of_range_raises(nb_path):
    """越界索引抛 IndexError（docstring 契约）。"""
    nb = Notebook(str(nb_path))
    with pytest.raises(IndexError):
        nb.get_cell(99)
    with pytest.raises(IndexError):
        nb.get_cell(-1)


def test_edit_cell_updates_source(nb_path):
    """edit_cell 更新 source 并返回该 cell。"""
    nb = Notebook(str(nb_path))
    cell = nb.edit_cell(0, "# New Title")
    assert cell.source == "# New Title"
    assert nb.cells[0].source == "# New Title"


def test_edit_cell_out_of_range_raises(nb_path):
    """edit_cell 越界透传 IndexError。"""
    nb = Notebook(str(nb_path))
    with pytest.raises(IndexError):
        nb.edit_cell(99, "x")


# ── move_cell ─────────────────────────────────────────────────────


def test_move_cell_reorders(nb_path):
    """move_cell 把 from 挪到 to，其余顺延。"""
    nb = Notebook(str(nb_path))
    original_sources = [c.source for c in nb.cells]
    assert nb.move_cell(0, 2) is True
    # 第 0 个（原 markdown）现在应在位置 2
    assert nb.cells[2].source == original_sources[0]
    # index 重排
    assert [c.index for c in nb.cells] == [0, 1, 2]


def test_move_cell_out_of_range_returns_false(nb_path):
    """任一索引越界 → 返回 False（不抛）。"""
    nb = Notebook(str(nb_path))
    assert nb.move_cell(99, 0) is False
    assert nb.move_cell(0, 99) is False
    assert nb.move_cell(-1, 0) is False


def test_move_cell_same_position_noop(nb_path):
    """from==to 应视为合法（返回 True），内容不变。"""
    nb = Notebook(str(nb_path))
    before = [c.source for c in nb.cells]
    assert nb.move_cell(1, 1) is True
    assert [c.source for c in nb.cells] == before


# ── summary / to_markdown ─────────────────────────────────────────


def test_summary_counts(nb_path):
    """summary 应正确统计 cell 数、code/markdown 数、总行数。"""
    nb = Notebook(str(nb_path))
    s = nb.summary()
    assert s["cell_count"] == 3
    assert s["code_cells"] == 2
    assert s["markdown_cells"] == 1
    assert s["total_lines"] >= 3  # 至少 3 行


def test_summary_empty_notebook(empty_nb_path):
    """空 notebook 的 summary 全为 0。"""
    s = Notebook(str(empty_nb_path)).summary()
    assert s == {"cell_count": 0, "code_cells": 0, "markdown_cells": 0, "total_lines": 0}


def test_to_markdown_renders_code_and_markdown(nb_path):
    """to_markdown：markdown 原样、code 包 ```python 围栏。"""
    nb = Notebook(str(nb_path))
    md = nb.to_markdown()
    assert "# Title" in md
    assert "```python" in md
    assert "print('hi')" in md


def test_to_markdown_empty_notebook(empty_nb_path):
    """空 notebook 的 markdown 应为空串或仅空白。"""
    md = Notebook(str(empty_nb_path)).to_markdown()
    assert md.strip() == ""


# ── save 往返 ─────────────────────────────────────────────────────


def test_save_roundtrip_preserves_cells(nb_path, tmp_path):
    """save → 重新 load 应得到相同的 cell 结构。"""
    nb = Notebook(str(nb_path))
    nb.add_cell(source="new cell")
    save_path = str(tmp_path / "saved.ipynb")
    nb.save(save_path)

    nb2 = Notebook(save_path)
    assert len(nb2.cells) == 4
    assert nb2.cells[3].source == "new cell"


def test_save_to_original_path_when_no_arg(nb_path):
    """不传 path → 保存到原路径。"""
    nb = Notebook(str(nb_path))
    nb.edit_cell(0, "# Edited")
    returned = nb.save()
    assert returned == str(nb_path)
    # 重新加载验证已写入
    nb2 = Notebook(str(nb_path))
    assert nb2.cells[0].source == "# Edited"


def test_save_code_cell_includes_outputs_and_count(tmp_path):
    """保存时 code cell 应含 outputs / execution_count 字段。"""
    p = _write_nb(tmp_path / "o.ipynb", [_cell("code", "x=1")])
    nb = Notebook(str(p))
    nb.cells[0].outputs = [{"stdout": "ok"}]
    nb.cells[0].execution_count = 5
    save_path = str(tmp_path / "o2.ipynb")
    nb.save(save_path)

    raw = json.loads(Path(save_path).read_text(encoding="utf-8"))
    code_cell = raw["cells"][0]
    assert code_cell["outputs"] == [{"stdout": "ok"}]
    assert code_cell["execution_count"] == 5


def test_save_non_code_cell_has_empty_outputs(tmp_path):
    """保存时非 code cell 的 outputs 应为空列表。"""
    p = _write_nb(tmp_path / "m.ipynb", [_cell("markdown", "# hi")])
    nb = Notebook(str(p))
    save_path = str(tmp_path / "m2.ipynb")
    nb.save(save_path)
    raw = json.loads(Path(save_path).read_text(encoding="utf-8"))
    assert raw["cells"][0]["outputs"] == []


# ── NotebookManager ───────────────────────────────────────────────


def test_manager_open_caches_by_path(nb_path):
    """同一 path 多次 open 应返回同一实例（缓存）。"""
    mgr = NotebookManager()
    nb1 = mgr.open(str(nb_path))
    nb2 = mgr.open(str(nb_path))
    assert nb1 is nb2


def test_manager_create_writes_minimal_notebook(tmp_path):
    """create 应写入最小合法 .ipynb 并返回可用的 Notebook。"""
    mgr = NotebookManager()
    p = str(tmp_path / "new.ipynb")
    nb = mgr.create(p)
    assert Path(p).exists()
    assert nb.cells == []
    # 写入的文件可被独立加载
    nb2 = Notebook(p)
    assert nb2.cells == []


def test_manager_list_notebooks_finds_ipynb(tmp_path):
    """list_notebooks 应递归发现 .ipynb 文件。"""
    mgr = NotebookManager()
    _write_nb(tmp_path / "a.ipynb", [])
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_nb(sub / "b.ipynb", [])
    (tmp_path / "not_nb.txt").write_text("x", encoding="utf-8")

    found = mgr.list_notebooks(str(tmp_path))
    names = [Path(f).name for f in found]
    assert "a.ipynb" in names
    assert "b.ipynb" in names
    assert "not_nb.txt" not in names


# ── 工具定义与执行器映射 ──────────────────────────────────────────


def test_tool_defs_well_formed():
    """TOOL_DEFS 应是 function 工具定义列表。"""
    assert isinstance(NOTEBOOK_TOOL_DEFS, list)
    assert len(NOTEBOOK_TOOL_DEFS) >= 5
    for td in NOTEBOOK_TOOL_DEFS:
        assert td["type"] == "function"
        assert "name" in td["function"]


def test_executor_map_keys_match_tool_def_names():
    """EXECUTOR_MAP 的 key 应与 TOOL_DEFS 的 function.name 一致。"""
    def_names = {td["function"]["name"] for td in NOTEBOOK_TOOL_DEFS}
    assert set(NOTEBOOK_EXECUTOR_MAP.keys()) == def_names


def test_executor_open_missing_path_returns_error_json():
    """notebook_open 对缺失文件应返回 error JSON（不抛）。"""
    fn = NOTEBOOK_EXECUTOR_MAP["notebook_open"]
    out = fn({"path": "C:/nope/ghost.ipynb"})
    data = json.loads(out)
    assert "error" in data


def test_executor_open_missing_required_param_returns_error():
    """notebook_open 不传 path 应返回 error JSON。"""
    fn = NOTEBOOK_EXECUTOR_MAP["notebook_open"]
    out = fn({})
    assert "error" in json.loads(out)


def test_executor_add_cell_persists_and_returns_cell(tmp_path):
    """notebook_add_cell 应写入文件并返回新 cell 信息。"""
    p = str(_write_nb(tmp_path / "ex.ipynb", []))
    fn = NOTEBOOK_EXECUTOR_MAP["notebook_add_cell"]
    out = fn({"path": p, "cell_type": "code", "source": "print(1)"})
    data = json.loads(out)
    assert "cell" in data
    assert data["cell"]["source"] == "print(1)"
    # 已持久化
    assert len(Notebook(p).cells) == 1
