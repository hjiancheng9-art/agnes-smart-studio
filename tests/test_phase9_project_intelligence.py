"""Test P9: Project Intelligence Layer / Repo Understanding OS."""

import pytest

from core.repo_understanding import (
    Edge,
    ProjectContextPack,
    ProjectOS,
    RepoGraph,
    RepoIndex,
    RepoIndexSnapshot,
)


@pytest.fixture(scope="module")
def repo_index():
    """Build index once for the module (CRUX project itself)."""
    idx = RepoIndex(root=".")
    snap = idx.build()
    return idx, snap


class TestRepoIndex:
    def test_build(self, repo_index):
        _idx, snap = repo_index
        assert snap.total_files > 0
        assert snap.total_lines > 0
        assert snap.build_time_ms > 0

    def test_finds_python_files(self, repo_index):
        _idx, snap = repo_index
        py_files = [f for f in snap.files.values() if f.extension == ".py"]
        assert len(py_files) > 10

    def test_parses_imports(self, repo_index):
        _idx, snap = repo_index
        # Check that at least some files have imports parsed
        with_imports = [f for f in snap.files.values() if f.imports]
        assert len(with_imports) > 5

    def test_parses_classes(self, repo_index):
        _idx, snap = repo_index
        with_classes = [f for f in snap.files.values() if f.classes]
        assert len(with_classes) > 3

    def test_parses_functions(self, repo_index):
        _idx, snap = repo_index
        with_funcs = [f for f in snap.files.values() if f.functions]
        assert len(with_funcs) > 5

    def test_find_symbol(self, repo_index):
        idx, _snap = repo_index
        symbols = idx.find_symbol("RepoIndex")
        assert len(symbols) >= 1
        assert any(s.kind == "class" for s in symbols)

    def test_find_symbol_case_insensitive(self, repo_index):
        idx, _snap = repo_index
        symbols = idx.find_symbol("repoindex")
        assert len(symbols) >= 1

    def test_find_files_matching(self, repo_index):
        idx, _snap = repo_index
        files = idx.find_files_matching("chat", max_results=5)
        assert len(files) >= 1

    def test_find_files_by_class(self, repo_index):
        idx, _snap = repo_index
        files = idx.find_files_matching("RepoIndex", max_results=5)
        assert len(files) >= 1

    def test_project_summary(self, repo_index):
        idx, snap = repo_index
        summary = idx.project_summary()
        assert "Project" in summary
        assert "Files" in summary
        assert str(snap.total_files) in summary

    def test_context_for_llm(self, repo_index):
        idx, _snap = repo_index
        ctx = idx.context_for_llm()
        assert len(ctx) > 100

    def test_to_dict(self, repo_index):
        _idx, snap = repo_index
        d = snap.to_dict()
        assert d["total_files"] > 0
        assert "symbol_count" in d

    def test_excludes_directories(self):
        idx = RepoIndex(root=".", excludes={"__pycache__"})
        snap = idx.build()
        pycache_files = [f for f in snap.files if "__pycache__" in f]
        assert len(pycache_files) == 0

    def test_incremental_no_changes(self, repo_index):
        idx, _snap = repo_index
        result = idx.incremental()
        # May be None if no changes
        assert result is None or isinstance(result, RepoIndexSnapshot)

    def test_empty_directory(self, tmp_path):
        idx = RepoIndex(root=str(tmp_path))
        snap = idx.build()
        assert snap.total_files == 0


class TestRepoGraph:
    def test_build_from_index(self, repo_index):
        _idx, snap = repo_index
        graph = RepoGraph.from_index(snap)
        assert len(graph.nodes) > 0

    def test_dependencies_of(self, repo_index):
        _idx, snap = repo_index
        graph = RepoGraph.from_index(snap)
        # Check a known file
        deps = graph.dependencies_of("core/repo_understanding.py")
        assert isinstance(deps, set)

    def test_dependents_of(self, repo_index):
        _idx, snap = repo_index
        graph = RepoGraph.from_index(snap)
        # Common dependency
        deps = graph.dependents_of("core/repo_understanding.py")
        assert isinstance(deps, set)

    def test_summary(self, repo_index):
        _idx, snap = repo_index
        graph = RepoGraph.from_index(snap)
        summary = graph.summary("core/repo_understanding.py")
        assert "Dependencies" in summary

    def test_edge_types(self):
        e1 = Edge(source="a.py", target="b.py", kind="import")
        e2 = Edge(source="a.py", target="b.py", kind="call")
        assert e1.kind == "import"
        assert e2.kind == "call"


class TestProjectOS:
    def test_index(self):
        os = ProjectOS(root=".")
        snap = os.index()
        assert snap.total_files > 0
        assert os.is_indexed

    def test_context_pack(self):
        os = ProjectOS(root=".")
        os.index()
        pack = os.context_pack(active_file="core/repo_understanding.py")
        assert isinstance(pack, ProjectContextPack)
        assert pack.file_count > 0
        assert len(pack.assemble()) > 100

    def test_context_pack_active_file(self, repo_index):
        os = ProjectOS(root=".")
        os.index()
        pack = os.context_pack(active_file="core/repo_understanding.py")
        # Should include the active file summary
        assembled = pack.assemble()
        assert "Active:" in assembled or "repo_understanding" in assembled

    def test_project_name(self):
        os = ProjectOS(root=".")
        os.index()
        pack = os.context_pack()
        assert len(pack.project_name) > 0

    def test_search(self):
        os = ProjectOS(root=".")
        os.index()
        results = os.search("chat")
        assert len(results) >= 1

    def test_find_symbol(self):
        os = ProjectOS(root=".")
        os.index()
        symbols = os.find_symbol("RepoIndex")
        assert len(symbols) >= 1

    def test_change_impact(self):
        os = ProjectOS(root=".")
        os.index()
        impact = os.analyze_change("core/repo_understanding.py")
        assert "Change Impact" in impact

    def test_quick_refresh(self):
        os = ProjectOS(root=".")
        os.index()
        changed = os.quick_refresh()
        # May or may not have changes
        assert isinstance(changed, bool)

    def test_not_indexed(self):
        os = ProjectOS(root="/nonexistent")
        assert not os.is_indexed


class TestIntegration:
    def test_validation_layer_integration(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        assert hasattr(vl, "project_os")
        assert hasattr(vl, "ensure_project_index")

    def test_get_project_context(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        pack = vl.get_project_context()
        assert pack.file_count > 0

    def test_search_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        results = vl.search_project("chat")
        assert len(results) >= 1

    def test_find_symbol_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        symbols = vl.find_symbol("ValidationLayer")
        assert len(symbols) >= 1

    def test_change_impact_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        impact = vl.analyze_change_impact("core/repo_understanding.py")
        assert "Change Impact" in impact

    def test_chat_p9_flag(self):
        import py_compile

        py_compile.compile("core/chat.py", doraise=True)
