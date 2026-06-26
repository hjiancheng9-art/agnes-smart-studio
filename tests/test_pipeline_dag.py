"""Smoke tests for core/pipeline_dag.py — DAG parallel execution engine.

Tests cover:
- Node and NodeStatus data structures
- DAG construction: node(), then(), merge(), action(), file_owned(), fallback_to()
- DAG execution: run(), entry_nodes, _ready(), retry, fallback, skip
- DAG summary formatting
"""

from core.pipeline_dag import DAG, Node, NodeStatus


class TestNodeStatus:
    def test_enum_values(self):
        assert NodeStatus.PENDING.value == "pending"
        assert NodeStatus.RUNNING.value == "running"
        assert NodeStatus.DONE.value == "done"
        assert NodeStatus.FAILED.value == "failed"
        assert NodeStatus.SKIPPED.value == "skipped"

    def test_enum_count(self):
        assert len(NodeStatus) == 5


class TestNode:
    def test_default_fields(self):
        n = Node(name="test")
        assert n.name == "test"
        assert n.action is None
        assert n.args == ()
        assert n.kwargs == {}
        assert n.deps == []
        assert n.owners == []
        assert n.status == NodeStatus.PENDING
        assert n.result is None
        assert n.error == ""
        assert n.retries == 0
        assert n.max_retries == 2
        assert n.fallback == ""
        assert n.started_at == 0.0
        assert n.finished_at == 0.0

    def test_custom_fields(self):
        def my_action():
            return 42

        n = Node(name="a", action=my_action, args=(1,), kwargs={"x": 2}, deps=["b"], owners=["f1.txt"])
        assert n.action is my_action
        assert n.args == (1,)
        assert n.kwargs == {"x": 2}
        assert n.deps == ["b"]
        assert n.owners == ["f1.txt"]


class TestDAGConstruction:
    def test_empty_dag(self):
        dag = DAG("empty")
        assert dag.name == "empty"
        assert dag.nodes == {}

    def test_single_node(self):
        dag = DAG("solo").node("step1")
        assert "step1" in dag.nodes
        assert dag.nodes["step1"].deps == []

    def test_linear_chain(self):
        dag = DAG("chain")
        dag.node("a").then("b").then("c")
        assert dag.nodes["a"].deps == []
        assert dag.nodes["b"].deps == ["a"]
        assert dag.nodes["c"].deps == ["b"]

    def test_then_is_alias_for_node(self):
        dag = DAG("alias")
        dag.node("x").then("y")
        assert dag.nodes["y"].deps == ["x"]

    def test_merge_branches(self):
        dag = DAG("merge")
        dag.node("a").then("b1").then("c1")
        dag.node("a").then("b2").then("c2")
        dag.merge(["c1", "c2"]).then("final")
        assert "c1" in dag.nodes["final"].deps
        assert "c2" in dag.nodes["final"].deps

    def test_action_assignment(self):
        dag = DAG("act")
        dag.node("step1").action(lambda: "ok")
        assert dag.nodes["step1"].action is not None
        assert dag.nodes["step1"].action() == "ok"

    def test_action_with_args(self):
        dag = DAG("act_args")
        dag.node("step1").action(lambda x, y: x + y, 3, 4)
        assert dag.nodes["step1"].args == (3, 4)

    def test_file_owned(self):
        dag = DAG("files")
        dag.node("writer").file_owned("writer", ["output.txt", "data.csv"])
        assert dag.nodes["writer"].owners == ["output.txt", "data.csv"]

    def test_fallback_to(self):
        dag = DAG("fb")
        dag.node("primary").node("backup").fallback_to("primary", "backup")
        assert dag.nodes["primary"].fallback == "backup"

    def test_entry_nodes(self):
        dag = DAG("entries")
        dag.node("a").then("b").then("c")
        # "d" is added without cursor chain, so it's also an entry
        # But cursor is still "c" from prior chain, so node("d") would add c as dep.
        # Use merge to reset cursor first:
        dag.merge([]).node("d").then("e")
        entries = dag.entry_nodes
        assert "a" in entries
        assert "d" in entries
        assert len(entries) == 2


class TestDAGExecution:
    def test_run_empty_dag(self):
        dag = DAG("empty")
        results = dag.run()
        assert results == {}

    def test_run_no_action_nodes(self):
        dag = DAG("noact")
        dag.node("a").then("b").then("c")
        results = dag.run()
        assert results == {}
        # All nodes should be DONE
        assert dag.nodes["a"].status == NodeStatus.DONE
        assert dag.nodes["b"].status == NodeStatus.DONE
        assert dag.nodes["c"].status == NodeStatus.DONE

    def test_run_with_actions(self):
        dag = DAG("acts")
        dag.node("a").action(lambda: 1)
        dag.node("b").action(lambda: 2)
        results = dag.run()
        assert results.get("a") == 1
        assert results.get("b") == 2

    def test_run_chain_with_results(self):
        dag = DAG("chain")
        dag.node("a").action(lambda: "hello").then("b")
        results = dag.run()
        assert results["a"] == "hello"
        assert dag.nodes["b"].status == NodeStatus.DONE

    def test_run_failure_no_retry(self):
        def fail():
            raise ValueError("boom")

        dag = DAG("fail")
        dag.node("bad").action(fail)
        results = dag.run()
        assert dag.nodes["bad"].status == NodeStatus.FAILED
        assert "boom" in dag.nodes["bad"].error
        assert "bad" not in results

    def test_run_retry_then_fail(self):
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("retry me")

        dag = DAG("retry")
        dag.node("flaky_node").action(flaky)
        results = dag.run()
        assert dag.nodes["flaky_node"].retries == 2  # max_retries default is 2
        assert dag.nodes["flaky_node"].status == NodeStatus.FAILED

    def test_run_retry_then_succeed(self):
        call_count = 0

        def eventually_works():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("not yet")
            return "success"

        dag = DAG("retry_ok")
        dag.node("patient").action(eventually_works)
        results = dag.run()
        assert dag.nodes["patient"].status == NodeStatus.DONE
        assert results["patient"] == "success"
        assert call_count == 2

    def test_run_fallback_on_failure(self):
        """After retries exhausted, primary gets SKIPPED when fallback exists."""
        def fail():
            raise RuntimeError("fail")

        dag = DAG("fb")
        dag.node("primary").action(fail).fallback_to("primary", "backup")
        dag.node("backup").action(lambda: "fallback_ok")
        results = dag.run()
        # primary is SKIPPED (not FAILED) because fallback exists
        assert dag.nodes["primary"].status == NodeStatus.SKIPPED
        assert dag.nodes["backup"].status == NodeStatus.DONE
        assert results["backup"] == "fallback_ok"

    def test_run_parallel_branches(self):
        dag = DAG("par")
        dag.node("a").then("b").action(lambda: "b_done").then("c")
        dag.merge([]).node("a").then("d").action(lambda: "d_done").then("e")
        dag.merge(["c", "e"]).then("final").action(lambda: "final_done")
        results = dag.run()
        assert results.get("b") == "b_done"
        assert results.get("d") == "d_done"
        assert results.get("final") == "final_done"

    def test_run_blocked_by_failed_dep(self):
        def fail():
            raise RuntimeError("fail")

        dag = DAG("block")
        dag.node("a").action(fail).then("b")
        dag.node("b").action(lambda: "should not run")
        results = dag.run()
        assert dag.nodes["a"].status == NodeStatus.FAILED
        assert dag.nodes["b"].status == NodeStatus.PENDING  # never ran


class TestDAGSummary:
    def test_summary_empty(self):
        dag = DAG("empty")
        summary = dag.summary()
        assert "empty" in summary
        assert "0 nodes" in summary

    def test_summary_with_nodes(self):
        dag = DAG("test")
        dag.node("a").then("b")
        dag.run()
        summary = dag.summary()
        assert "2 nodes" in summary
        assert "[+]" in summary  # done nodes

    def test_summary_with_failed(self):
        def fail():
            raise RuntimeError("x")

        dag = DAG("test2")
        dag.node("bad").action(fail)
        dag.run()
        summary = dag.summary()
        assert "[!]" in summary  # failed node
