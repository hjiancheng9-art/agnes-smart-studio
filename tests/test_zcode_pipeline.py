"""RED tests for pipeline modules — DAG, state engine, and tools.

Run: pytest tests/test_zcode_pipeline.py -v

Each test is independent and self-contained.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

import core.pipeline_tools as _pt
from core.pipeline_dag import DAG, Node, NodeStatus
from core.pipeline_tools import pipeline_scope

# ── Fixtures ──────────────────────────────────────────────────────────

# Use absolute paths as fallback — immune to import-time pollution from
# other test modules that may have mutated pt.OUTPUT_ROOT before this file loads.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_ROOT = _PROJECT_ROOT / "output"
_ORIGINAL_MF = _PROJECT_ROOT / "output" / "projects"


@pytest.fixture(autouse=True)
def _restore_pipeline_globals():
    """Safety net: restore OUTPUT_ROOT / MANIFEST_DIR around each test.

    Uses import-time snapshot to guarantee restoration to the real project
    paths, regardless of what prior tests (in any module) have done.
    """
    _pt.OUTPUT_ROOT = _ORIGINAL_ROOT
    _pt.MANIFEST_DIR = _ORIGINAL_MF
    yield
    _pt.OUTPUT_ROOT = _ORIGINAL_ROOT
    _pt.MANIFEST_DIR = _ORIGINAL_MF


class TestDAGCoreTypes:
    """Class existence and type checks."""

    def test_dag_class_exists(self):
        assert DAG is not None

    def test_node_class_exists(self):
        node = Node(name="x")
        assert node.name == "x"
        assert node.status == NodeStatus.PENDING
        assert node.retries == 0
        assert node.max_retries == 2

    def test_nodestatus_has_all_states(self):
        assert NodeStatus.PENDING.value == "pending"
        assert NodeStatus.RUNNING.value == "running"
        assert NodeStatus.DONE.value == "done"
        assert NodeStatus.FAILED.value == "failed"
        assert NodeStatus.SKIPPED.value == "skipped"


class TestDAGCreation:
    """Basic DAG construction."""

    def test_dag_creates_with_name(self):
        dag = DAG("test_pipeline")
        assert dag.name == "test_pipeline"
        assert dag.nodes == {}
        assert dag._cursor is None

    def test_dag_default_name(self):
        dag = DAG()
        assert dag.name == "pipeline"


class TestDAGNode:
    """Node addition and chaining."""

    def test_node_adds_node(self):
        dag = DAG("x")
        dag.node("a")
        assert "a" in dag.nodes
        assert dag.nodes["a"].name == "a"

    def test_node_returns_self_for_chaining(self):
        dag = DAG("x")
        result = dag.node("a")
        assert result is dag

    def test_node_multiple_adds(self):
        dag = DAG("x")
        dag.node("a").node("b").node("c")
        assert list(dag.nodes.keys()) == ["a", "b", "c"]

    def test_node_sets_cursor(self):
        dag = DAG("x")
        dag.node("a")
        assert dag._cursor == "a"

    def test_node_no_implicit_dep_for_first_node(self):
        dag = DAG("x")
        dag.node("a")
        assert dag.nodes["a"].deps == []


class TestDAGThen:
    """then() alias and dependency creation."""

    def test_then_adds_node(self):
        dag = DAG("x")
        dag.node("a").then("b")
        assert "b" in dag.nodes

    def test_then_creates_dependency(self):
        dag = DAG("x")
        dag.node("a").then("b")
        assert dag.nodes["b"].deps == ["a"]

    def test_then_chains_multiple(self):
        dag = DAG("x")
        dag.node("a").then("b").then("c")
        assert dag.nodes["b"].deps == ["a"]
        assert dag.nodes["c"].deps == ["b"]

    def test_then_returns_self(self):
        dag = DAG("x")
        result = dag.node("a").then("b")
        assert result is dag


class TestDAGMerge:
    """Merge point creation."""

    def test_merge_then_creates_merge_point(self):
        dag = DAG("x")
        dag.node("a").node("b")
        dag.merge(["a", "b"]).then("c")
        assert set(dag.nodes["c"].deps) == {"a", "b"}

    def test_merge_followed_by_more_nodes(self):
        dag = DAG("x")
        dag.node("a").node("b").merge(["a", "b"]).then("c").then("d")
        assert set(dag.nodes["c"].deps) == {"a", "b"}
        assert dag.nodes["d"].deps == ["c"]

    def test_merge_clears_cursor(self):
        dag = DAG("x")
        dag.node("a")
        dag.merge(["b"])
        assert dag._cursor is None


class TestDAGAction:
    """Action assignment."""

    def test_action_sets_callable(self):
        dag = DAG("x")

        def my_func():
            return 99

        dag.node("a").action(my_func)
        assert dag.nodes["a"].action is my_func

    def test_action_with_args(self):
        dag = DAG("x")

        def add(a, b):
            return a + b

        dag.node("sum").action(add, 3, 4)
        assert dag.nodes["sum"].action is add
        assert dag.nodes["sum"].args == (3, 4)

    def test_action_returns_self(self):
        dag = DAG("x")
        result = dag.node("a").action(lambda: None)
        assert result is dag

    def test_action_noop_when_no_cursor(self):
        """action() does nothing if cursor is None (after merge)."""
        dag = DAG("x")
        dag.node("a")
        dag.merge([])
        dag.action(lambda: "orphan")
        # No cursor set, so no node should have the action
        assert dag.nodes["a"].action is None


class TestDAGFileOwned:
    """File ownership registration."""

    def test_file_owned_registers_files(self):
        dag = DAG("x")
        dag.node("a").file_owned("a", ["f1.py", "f2.py"])
        assert dag.nodes["a"].owners == ["f1.py", "f2.py"]

    def test_file_owned_creates_node_if_missing(self):
        dag = DAG("x")
        dag.file_owned("new_node", ["f.py"])
        assert "new_node" in dag.nodes

    def test_file_owned_detects_collision(self):
        """Second owner overwrites the file registration (logged warning)."""
        dag = DAG("x")
        dag.file_owned("a", ["shared.py"])
        dag.file_owned("b", ["shared.py"])
        # After collision, the registry should map to the last owner
        assert dag._file_registry["shared.py"] == "b"

    def test_file_owned_returns_self(self):
        dag = DAG("x")
        result = dag.file_owned("a", ["f.py"])
        assert result is dag


class TestDAGFallback:
    """Fallback configuration."""

    def test_fallback_to_sets_fallback(self):
        dag = DAG("x")
        dag.node("a").node("b")
        dag.fallback_to("a", "b")
        assert dag.nodes["a"].fallback == "b"

    def test_fallback_to_nonexistent_source_is_noop(self):
        dag = DAG("x")
        dag.node("b")
        dag.fallback_to("nonexistent", "b")  # should not raise
        assert dag.nodes["b"].fallback == ""

    def test_fallback_returns_self(self):
        dag = DAG("x")
        result = dag.fallback_to("a", "b")
        assert result is dag


class TestDAGEntryNodes:
    """entry_nodes property."""

    def test_entry_nodes_single(self):
        dag = DAG("x")
        dag.node("a").then("b")
        assert dag.entry_nodes == ["a"]

    def test_entry_nodes_multiple_roots_via_reset(self):
        """Use merge([]) to break cursor chain and create independent roots."""
        dag = DAG("x")
        dag.node("a")
        dag.merge([])  # reset cursor so next node has no implicit dep
        dag.node("b")
        dag.merge(["a", "b"]).then("c")
        assert set(dag.entry_nodes) == {"a", "b"}

    def test_entry_nodes_consecutive_node_creates_chain(self):
        """Consecutive .node() calls create implicit dep via cursor."""
        dag = DAG("x")
        dag.node("a")
        dag.node("b")  # b implicitly depends on a
        assert dag.entry_nodes == ["a"]

    def test_entry_nodes_no_nodes(self):
        dag = DAG("x")
        assert dag.entry_nodes == []


class TestDAGRun:
    """DAG execution."""

    def test_run_simple_chain(self):
        dag = DAG("simple")
        dag.node("a").action(lambda: "hello").then("b").action(lambda: "world")
        results = dag.run()
        assert results["a"] == "hello"
        assert results["b"] == "world"

    def test_run_node_with_no_action_is_done(self):
        dag = DAG("no_action")
        dag.node("a")
        results = dag.run()
        assert "a" not in results
        assert dag.nodes["a"].status == NodeStatus.DONE

    def test_run_returns_dict(self):
        dag = DAG("dict_test")
        dag.node("a").action(lambda: 42)
        results = dag.run()
        assert isinstance(results, dict)

    def test_run_respects_dependencies(self):
        """Nodes execute in correct dependency order."""
        order = []

        def capture(name):
            def fn():
                order.append(name)
                return name

            return fn

        dag = DAG("order")
        dag.node("a").action(capture("a")).then("b").action(capture("b")).then("c").action(capture("c"))
        dag.run()
        assert order == ["a", "b", "c"]

    def test_run_parallel_inputs(self):
        results = {}

        def store(key):
            def fn():
                results[key] = key
                return key

            return fn

        dag = DAG("parallel")
        dag.node("a").action(store("a"))
        dag.node("b").action(store("b"))
        dag.merge(["a", "b"]).then("c").action(lambda: "merged")
        dag.run()
        assert results.get("a") == "a"
        assert results.get("b") == "b"
        # Both 'a' and 'b' should be done (order-independent)
        assert dag.nodes["a"].status == NodeStatus.DONE
        assert dag.nodes["b"].status == NodeStatus.DONE
        assert dag.nodes["c"].status == NodeStatus.DONE


class TestDAGRunFailure:
    """DAG failure and retry behavior."""

    def test_failing_node_retries_then_failed(self):
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise ValueError("persistent failure")

        dag = DAG("fail_retry")
        dag.node("a").action(always_fails)
        dag.run()
        # Should retry up to max_retries (2) then stay FAILED
        assert dag.nodes["a"].status == NodeStatus.FAILED
        # Initial + max_retries times = 3 total calls
        assert call_count[0] == 3  # initial + 2 retries

    def test_failing_node_with_fallback(self):
        dag = DAG("fallback_success")

        def fail_fn():
            raise ValueError("fail")

        dag.node("a").action(fail_fn)
        dag.node("b").action(lambda: "fallback_ok")
        dag.fallback_to("a", "b")
        results = dag.run()
        assert dag.nodes["a"].status == NodeStatus.SKIPPED
        assert dag.nodes["b"].status == NodeStatus.DONE
        assert results.get("b") == "fallback_ok"

    def test_fallback_with_then_dep_cleared(self):
        """When 'a' -> 'b' and 'a' falls back to 'b', the dep is cleared."""
        dag = DAG("dep_clear")

        def fail_fn():
            raise ValueError("fail")

        dag.node("a").action(fail_fn).then("b").action(lambda: "saved")
        dag.fallback_to("a", "b")
        results = dag.run()
        # 'b' should still run because fallback clears the dep on 'a'
        assert results.get("b") == "saved"
        assert dag.nodes["b"].status == NodeStatus.DONE

    def test_missing_fallback_is_noop(self):
        """Failing node with missing fallback name still fails."""

        def fail_fn():
            raise ValueError("fail")

        dag = DAG("missing_fb")
        dag.node("a").action(fail_fn)
        dag.fallback_to("a", "nonexistent")
        dag.run()
        assert dag.nodes["a"].status == NodeStatus.FAILED


class TestDAGSummary:
    """Summary string."""

    def test_summary_returns_string(self):
        dag = DAG("s")
        dag.node("a")
        s = dag.summary()
        assert isinstance(s, str)

    def test_summary_contains_dag_name(self):
        dag = DAG("my_dag")
        s = dag.summary()
        assert "my_dag" in s

    def test_summary_contains_node_names(self):
        dag = DAG("s")
        dag.node("alpha").node("beta")
        s = dag.summary()
        assert "alpha" in s
        assert "beta" in s

    def test_summary_shows_status_symbols(self):
        dag = DAG("s")
        dag.node("a").action(lambda: "ok")
        dag.run()
        s = dag.summary()
        # DONE nodes show '+'
        assert "[+]" in s or "+" in s


# ═══════════════════════════════════════════════════════════════════════
# Module 2: core.pipeline_state
# ═══════════════════════════════════════════════════════════════════════

from core.pipeline_state import PIPELINES, PipelineEngine, PipelineState


class TestPipelineState:
    """PipelineState basic operations."""

    def test_create_with_run_id(self):
        ps = PipelineState("run_001")
        assert ps.run_id == "run_001"
        assert ps.data == {}
        assert ps.step_results == {}
        assert ps.assets == []
        assert ps.qa_log == []

    def test_set_and_get_data(self):
        ps = PipelineState("r1")
        ps.set("key1", "value1")
        assert ps.get("key1") == "value1"

    def test_get_default(self):
        ps = PipelineState("r1")
        assert ps.get("nonexistent") is None
        assert ps.get("nonexistent", "fallback") == "fallback"

    def test_set_overwrite(self):
        ps = PipelineState("r1")
        ps.set("x", 1)
        ps.set("x", 2)
        assert ps.get("x") == 2

    def test_data_is_dict(self):
        ps = PipelineState("r1")
        assert isinstance(ps.data, dict)

    def test_record_step_stores_result(self):
        ps = PipelineState("r1")
        ps.record_step("skill_a", "my result text")
        assert ps.step_results["skill_a"] == "my result text"

    def test_record_step_truncates_at_500(self):
        ps = PipelineState("r1")
        long_text = "x" * 1000
        ps.record_step("skill_a", long_text)
        assert len(ps.step_results["skill_a"]) == 500

    def test_record_step_sets_current_step(self):
        ps = PipelineState("r1")
        ps.record_step("skill_b", "ok")
        assert ps.current_step == "skill_b"

    def test_add_asset_records_info(self):
        ps = PipelineState("r1")
        ps.add_asset("/path/to/img.png", "visual", "main character")
        assert len(ps.assets) == 1
        asset = ps.assets[0]
        assert asset["path"] == "/path/to/img.png"
        assert asset["step"] == "visual"
        assert asset["desc"] == "main character"
        assert asset["run_id"] == "r1"
        assert "ts" in asset

    def test_add_asset_multiple(self):
        ps = PipelineState("r1")
        ps.add_asset("a.png", "s1")
        ps.add_asset("b.png", "s2")
        assert len(ps.assets) == 2

    def test_log_qa_records_entry(self):
        ps = PipelineState("r1")
        ps.log_qa("inspect", True, "all good")
        assert len(ps.qa_log) == 1
        entry = ps.qa_log[0]
        assert entry["step"] == "inspect"
        assert entry["passed"] is True
        assert entry["note"] == "all good"
        assert "ts" in entry

    def test_log_qa_failure(self):
        ps = PipelineState("r1")
        ps.log_qa("inspect", False, "quality low")
        assert ps.qa_log[0]["passed"] is False

    def test_context_for_next_empty(self):
        ps = PipelineState("r1")
        ctx = ps.context_for_next()
        assert ctx == ""

    def test_context_for_next_with_step_result(self):
        ps = PipelineState("r1")
        ps.record_step("writing", "first draft completed")
        ctx = ps.context_for_next()
        assert "[Previous step: writing]" in ctx
        assert "first draft completed" in ctx

    def test_context_for_next_shows_assets(self):
        ps = PipelineState("r1")
        ps.record_step("s1", "done")
        ps.add_asset("out.png", "s1")
        ctx = ps.context_for_next()
        assert "Assets" in ctx
        assert "out.png" in ctx

    def test_context_for_next_shows_last_three_assets(self):
        ps = PipelineState("r1")
        ps.record_step("s1", "done")
        for i in range(5):
            ps.add_asset(f"f{i}.png", "s1")
        ctx = ps.context_for_next()
        # Should show only the last 3
        assert "f4.png" in ctx
        assert "f3.png" in ctx
        assert "f2.png" in ctx
        assert "f0.png" not in ctx

    def test_context_for_next_with_constraints(self):
        ps = PipelineState("r1")
        ps.record_step("s1", "done")
        ps.set("constraints", "no violence")
        ctx = ps.context_for_next()
        assert "no violence" in ctx

    def test_context_for_next_truncates_step_at_300(self):
        ps = PipelineState("r1")
        long_text = "abc" * 200
        ps.record_step("s1", long_text)
        ctx = ps.context_for_next()
        # The step result in context is sliced to [:300]
        part = ctx.split("\n")[1] if "\n" in ctx else ctx
        assert len(part) <= 300

    def test_start_time_set_on_creation(self):
        ps = PipelineState("r1")
        assert isinstance(ps.start_time, float)
        assert ps.start_time > 0


class TestPIPELINES:
    """PIPELINES presets dictionary."""

    def test_has_expected_keys(self):
        expected = {
            "video-production",
            "comfyui-studio",
            "combat-action",
            "creative-image",
            "world-building",
            "script-to-audio",
            "novel-publishing",
            "comic-storyboard",
            "self-evolve",
            "api-development",
        }
        assert expected.issubset(PIPELINES.keys())

    def test_each_has_name_skills_output_type(self):
        for pid, pipe in PIPELINES.items():
            assert "name" in pipe, f"{pid} missing name"
            assert "skills" in pipe, f"{pid} missing skills"
            assert isinstance(pipe["skills"], list), f"{pid} skills not list"
            assert "output_type" in pipe, f"{pid} missing output_type"

    def test_video_production_preset(self):
        pipe = PIPELINES["video-production"]
        assert pipe["output_type"] == "video"
        assert "prompt-director" in pipe["skills"]

    def test_comfyui_studio_preset(self):
        pipe = PIPELINES["comfyui-studio"]
        assert pipe["output_type"] == "image/video"
        assert "comfyui-bridge" in pipe["skills"]

    def test_qa_gates_are_valid_skills(self):
        for pid, pipe in PIPELINES.items():
            for gate in pipe.get("qa_gates", []):
                assert gate in pipe["skills"], f"{pid}: QA gate '{gate}' not in skills list"


class TestPipelineEngine:
    """PipelineEngine unit tests."""

    def test_list_pipelines_returns_list_of_dicts(self):
        engine = PipelineEngine()
        result = engine.list_pipelines()
        assert isinstance(result, list)
        assert len(result) > 0
        entry = result[0]
        assert "id" in entry
        assert "name" in entry
        assert "skills" in entry
        assert "output" in entry

    def test_list_pipelines_matches_pipelines_keys(self):
        engine = PipelineEngine()
        result = engine.list_pipelines()
        ids = {e["id"] for e in result}
        assert ids == set(PIPELINES.keys())

    def test_run_invalid_pipeline_raises_valueerror(self):
        engine = PipelineEngine()
        import pytest

        with pytest.raises(ValueError, match="Unknown pipeline"):
            engine.run("nonexistent-pipeline-xyz", "input")

    def test_prev_step_returns_previous(self):
        engine = PipelineEngine()
        skills = ["a", "b", "c"]
        assert engine._prev_step(skills, "b") == "a"
        assert engine._prev_step(skills, "c") == "b"

    def test_prev_step_first_returns_none(self):
        engine = PipelineEngine()
        assert engine._prev_step(["a", "b"], "a") is None

    def test_prev_step_unknown_returns_none(self):
        engine = PipelineEngine()
        assert engine._prev_step(["a", "b"], "z") is None

    def test_check_quality_empty_output_fails(self):
        engine = PipelineEngine()
        engine.state = PipelineState("qa_test")
        result = engine._check_quality("step1", "")
        assert result is False

    def test_check_quality_fail_prefix_fails(self):
        engine = PipelineEngine()
        engine.state = PipelineState("qa_test")
        result = engine._check_quality("step1", "[FAIL] something wrong")
        assert result is False

    def test_check_quality_chinese_error_fails(self):
        engine = PipelineEngine()
        engine.state = PipelineState("qa_test")
        result = engine._check_quality("step1", "[错误] 发生了错误")
        assert result is False

    def test_check_quality_valid_output_passes(self):
        engine = PipelineEngine()
        engine.state = PipelineState("qa_test")
        result = engine._check_quality("step1", "valid output content")
        assert result is True

    def test_check_quality_logs_on_failure(self):
        engine = PipelineEngine()
        engine.state = PipelineState("qa_test")
        engine._check_quality("step1", "")
        assert len(engine.state.qa_log) >= 1
        assert engine.state.qa_log[-1]["passed"] is False


# ═══════════════════════════════════════════════════════════════════════
# Module 3: core.pipeline_tools
# ═══════════════════════════════════════════════════════════════════════

from core.pipeline_tools import (
    EXECUTOR_MAP,
    MANIFEST_DIR,
    OUTPUT_ROOT,
    PIPELINE_TOOLS,
    execute_check_file,
    execute_decompose_to_storyboard,
    execute_dependency_graph,
    execute_list_files,
    execute_mark_asset_ok,
    execute_regenerate_asset,
    execute_save_manifest,
)


class TestPipelineToolDefinitions:
    """PIPELINE_TOOLS structure."""

    def test_pipeline_tools_is_list(self):
        assert isinstance(PIPELINE_TOOLS, list)
        assert len(PIPELINE_TOOLS) > 0

    def test_each_tool_has_function_type(self):
        for tool in PIPELINE_TOOLS:
            assert tool["type"] == "function"

    def test_each_tool_has_function_name(self):
        for tool in PIPELINE_TOOLS:
            assert "name" in tool["function"]
            assert isinstance(tool["function"]["name"], str)
            assert len(tool["function"]["name"]) > 0

    def test_each_tool_has_description(self):
        for tool in PIPELINE_TOOLS:
            assert "description" in tool["function"]
            assert isinstance(tool["function"]["description"], str)

    def test_each_tool_has_parameters(self):
        for tool in PIPELINE_TOOLS:
            params = tool["function"]["parameters"]
            assert params["type"] == "object"
            assert "properties" in params

    def test_each_parameter_has_type_and_description(self):
        for tool in PIPELINE_TOOLS:
            params = tool["function"]["parameters"]["properties"]
            for pname, pdef in params.items():
                assert "type" in pdef, f"{tool['function']['name']}:{pname} missing type"
                assert "description" in pdef, f"{tool['function']['name']}:{pname} missing description"

    def test_required_fields_present(self):
        for tool in PIPELINE_TOOLS:
            func = tool["function"]
            params = func["parameters"]
            required = params.get("required", [])
            for r in required:
                assert r in params["properties"], f"{func['name']}: required '{r}' missing from properties"


class TestEXECUTORMAP:
    """EXECUTOR_MAP coverage."""

    def test_executor_map_has_matching_keys(self):
        tool_names = {t["function"]["name"] for t in PIPELINE_TOOLS}
        executor_names = set(EXECUTOR_MAP.keys())
        assert tool_names == executor_names, (
            f"Mismatch: tools={tool_names - executor_names}, extras={executor_names - tool_names}"
        )

    def test_executor_map_values_are_callable(self):
        for name, fn in EXECUTOR_MAP.items():
            assert callable(fn), f"{name} executor not callable"

    def test_executor_map_routes_to_correct_function(self):
        """Spot-check that executor lambda routes to the underlying function."""
        import inspect

        fn = EXECUTOR_MAP["check_file_exists"]
        source = inspect.getsource(fn)
        assert "execute_check_file" in source


class TestExecuteCheckFile:
    """execute_check_file — file existence check."""

    def test_returns_json(self):
        result = execute_check_file("/nonexistent/path/xyz")
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_nonexistent_file_returns_exists_false(self):
        result = execute_check_file("/nonexistent/path/xyz")
        data = json.loads(result)
        assert data["exists"] is False

    def test_existing_file_returns_exists_true(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            tmp_path = f.name
        try:
            result = execute_check_file(tmp_path)
            data = json.loads(result)
            assert data["exists"] is True
            assert data["is_file"] is True
        finally:
            os.unlink(tmp_path)

    def test_return_has_path(self):
        result = execute_check_file("/some/path")
        data = json.loads(result)
        assert "path" in data
        assert "is_file" in data

    def test_existing_file_has_size_and_extension(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello")
            tmp_path = f.name
        try:
            result = execute_check_file(tmp_path)
            data = json.loads(result)
            assert data["size_bytes"] == 5
            assert data["extension"] == ".txt"
        finally:
            os.unlink(tmp_path)


class TestExecuteSaveManifest:
    """execute_save_manifest — manifest creation."""

    def _run_with_temp(self, fn):
        """Run fn with temporary OUTPUT_ROOT and MANIFEST_DIR via pipeline_scope."""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with pipeline_scope(td_path):
                return fn(td_path)

    def test_creates_manifest_json(self):
        def _test(td):
            result = execute_save_manifest("test_proj", {"phase": "init"})
            data = json.loads(result)
            assert data["success"] is True
            assert "test_proj" in data["project_name"]
            manifest_path = Path(data["manifest_path"])
            assert manifest_path.exists()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest["phase"] == "init"

        self._run_with_temp(_test)

    def test_returns_project_name_and_paths(self):
        def _test(td):
            result = execute_save_manifest("my_project", {})
            data = json.loads(result)
            assert data["project_name"] == "my_project"
            assert "manifest_path" in data
            assert "output_dir" in data

        self._run_with_temp(_test)

    def test_adds_timestamp(self):
        def _test(td):
            result = execute_save_manifest("ts_test", {"data": 1})
            data = json.loads(result)
            manifest_path = Path(data["manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert "saved_at" in manifest

        self._run_with_temp(_test)

    def test_sanitizes_project_name(self):
        def _test(td):
            result = execute_save_manifest("my project/path", {})
            data = json.loads(result)
            assert data["success"] is True

        self._run_with_temp(_test)


class TestExecuteListFiles:
    """execute_list_files — project file listing."""

    def _run_with_temp(self, fn):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with pipeline_scope(td_path):
                return fn(td_path)

    def test_nonexistent_project_returns_exists_false(self):
        def _test(td):
            result = execute_list_files("nonexistent_project")
            data = json.loads(result)
            assert data["exists"] is False
            assert data["files"] == []

        self._run_with_temp(_test)

    def test_existing_project_lists_files(self):
        def _test(td):
            # Create a project with a file
            project_dir = td / "projects" / "my_proj"
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "test.txt").write_text("hello", encoding="utf-8")

            result = execute_list_files("my_proj")
            data = json.loads(result)
            assert data["exists"] is True
            assert data["total_files"] == 1
            assert data["files"][0]["path"] == "test.txt"

        self._run_with_temp(_test)

    def test_returns_json_with_project_name(self):
        def _test(td):
            result = execute_list_files("some_project")
            data = json.loads(result)
            assert data["project_name"] == "some_project"

        self._run_with_temp(_test)


class TestExecuteDecomposeToStoryboard:
    """execute_decompose_to_storyboard — script persistence."""

    def _run_with_temp(self, fn):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with pipeline_scope(td_path):
                return fn(td_path)

    def test_saves_script_to_manifest(self):
        def _test(td):
            result = execute_decompose_to_storyboard("film_x", "the script text")
            data = json.loads(result)
            assert data["success"] is True
            assert data["project_name"] == "film_x"
            assert data["script_length"] == len("the script text")

            # Verify manifest was written
            mf_path = td / "projects" / "film_x" / "manifest.json"
            assert mf_path.exists()
            manifest = json.loads(mf_path.read_text(encoding="utf-8"))
            assert manifest["script"] == "the script text"
            assert manifest["phase"] == "decompose"
            assert manifest["stage"] == "script_locked"

        self._run_with_temp(_test)

    def test_returns_hint(self):
        def _test(td):
            result = execute_decompose_to_storyboard("p1", "text")
            data = json.loads(result)
            assert "hint" in data

        self._run_with_temp(_test)


class TestExecuteDependencyGraph:
    """execute_dependency_graph — dependency graph inspection."""

    def _run_with_temp(self, fn):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with pipeline_scope(td_path):
                return fn(td_path)

    def test_nonexistent_project_returns_error(self):
        def _test(td):
            result = execute_dependency_graph("no_such_project")
            data = json.loads(result)
            assert data["success"] is False
            assert "error" in data
            assert "项目不存在" in data["error"] or "no_such_project" in data["error"]

        self._run_with_temp(_test)

    def test_existing_project_returns_nodes(self):
        def _test(td):
            # Create manifest with assets
            mf_dir = td / "projects" / "my_film"
            mf_dir.mkdir(parents=True, exist_ok=True)
            mf = {
                "project_name": "my_film",
                "assets": {
                    "char-01": {
                        "type": "character",
                        "status": "done",
                        "path": "/chars/hero.png",
                        "depends_on": [],
                        "depended_by": ["kf-03"],
                    },
                    "kf-03": {
                        "type": "keyframe",
                        "status": "pending",
                        "path": "",
                        "depends_on": ["char-01"],
                        "depended_by": [],
                    },
                },
            }
            (mf_dir / "manifest.json").write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")

            result = execute_dependency_graph("my_film")
            data = json.loads(result)
            assert data["success"] is True
            assert data["total_nodes"] == 2
            node_ids = {n["id"] for n in data["nodes"]}
            assert node_ids == {"char-01", "kf-03"}

        self._run_with_temp(_test)


class TestExecuteMarkAssetOk:
    """execute_mark_asset_ok — marking assets as done."""

    def _run_with_temp(self, fn):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with pipeline_scope(td_path):
                return fn(td_path)

    def test_nonexistent_project_returns_error(self):
        def _test(td):
            result = execute_mark_asset_ok("ghost_project", "asset-01")
            data = json.loads(result)
            assert data["success"] is False
            assert "不存在" in data["error"] or "ghost_project" in data["error"]

        self._run_with_temp(_test)

    def test_nonexistent_asset_in_existing_project(self):
        def _test(td):
            mf_dir = td / "projects" / "p1"
            mf_dir.mkdir(parents=True, exist_ok=True)
            (mf_dir / "manifest.json").write_text(
                json.dumps({"project_name": "p1", "assets": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            result = execute_mark_asset_ok("p1", "no-such-asset")
            data = json.loads(result)
            assert data["success"] is False
            assert "未找到" in data["error"]

        self._run_with_temp(_test)

    def test_marks_asset_done(self):
        def _test(td):
            mf_dir = td / "projects" / "p1"
            mf_dir.mkdir(parents=True, exist_ok=True)
            mf = {
                "project_name": "p1",
                "assets": {
                    "char-01": {
                        "type": "character",
                        "status": "pending",
                        "depends_on": [],
                        "depended_by": [],
                    }
                },
            }
            (mf_dir / "manifest.json").write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
            result = execute_mark_asset_ok("p1", "char-01")
            data = json.loads(result)
            assert data["success"] is True
            assert data["status"] == "done"

            # Verify file was updated
            manifest = json.loads((mf_dir / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["assets"]["char-01"]["status"] == "done"

        self._run_with_temp(_test)


class TestExecuteRegenerateAsset:
    """execute_regenerate_asset — asset regeneration."""

    def _run_with_temp(self, fn):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            with pipeline_scope(td_path):
                return fn(td_path)

    def test_nonexistent_project_returns_error(self):
        def _test(td):
            result = execute_regenerate_asset("missing", "a-01")
            data = json.loads(result)
            assert data["success"] is False
            assert "不存在" in data["error"] or "missing" in data["error"]

        self._run_with_temp(_test)

    def test_nonexistent_asset_returns_error(self):
        def _test(td):
            mf_dir = td / "projects" / "p1"
            mf_dir.mkdir(parents=True, exist_ok=True)
            (mf_dir / "manifest.json").write_text(
                json.dumps({"project_name": "p1", "assets": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            result = execute_regenerate_asset("p1", "bad-id")
            data = json.loads(result)
            assert data["success"] is False
            assert "未找到" in data["error"]

        self._run_with_temp(_test)

    def test_marks_asset_needs_redo(self):
        def _test(td):
            mf_dir = td / "projects" / "p1"
            mf_dir.mkdir(parents=True, exist_ok=True)
            mf = {
                "project_name": "p1",
                "assets": {
                    "kf-03": {
                        "type": "keyframe",
                        "status": "done",
                        "depends_on": [],
                        "depended_by": [],
                    }
                },
            }
            (mf_dir / "manifest.json").write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
            result = execute_regenerate_asset("p1", "kf-03")
            data = json.loads(result)
            assert data["success"] is True
            assert data["new_status"] == "needs_redo"

            manifest = json.loads((mf_dir / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["assets"]["kf-03"]["status"] == "needs_redo"

        self._run_with_temp(_test)

    def test_with_new_params(self):
        def _test(td):
            mf_dir = td / "projects" / "p1"
            mf_dir.mkdir(parents=True, exist_ok=True)
            mf = {
                "project_name": "p1",
                "assets": {
                    "char-01": {
                        "type": "character",
                        "status": "done",
                        "depends_on": [],
                        "depended_by": [],
                    }
                },
            }
            (mf_dir / "manifest.json").write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
            result = execute_regenerate_asset("p1", "char-01", '{"prompt": "warmer tone"}')
            data = json.loads(result)
            assert data["success"] is True

            manifest = json.loads((mf_dir / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["assets"]["char-01"]["params_update"] == {"prompt": "warmer tone"}

        self._run_with_temp(_test)


class TestPipelineToolsConstants:
    """OUTPUT_ROOT and MANIFEST_DIR type checks."""

    def test_output_root_is_path(self):
        assert isinstance(OUTPUT_ROOT, Path)

    def test_manifest_dir_is_path(self):
        assert isinstance(MANIFEST_DIR, Path)

    def test_manifest_dir_is_under_output_root(self):
        assert str(MANIFEST_DIR).startswith(str(OUTPUT_ROOT))
