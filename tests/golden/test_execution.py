"""Execution 执行契约测试"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from comfyflow_compiler.execution import (
    SubmissionContract, SubmissionResult,
    PollingContract, PollResult, ExecutionStatus,
    OutputCollector,
    ExecutionError, SubmissionError, PollingTimeoutError,
    ExecutionOrchestrator, ExecutionResult,
)


class TestSubmission:
    def test_submit_offline(self):
        sc = SubmissionContract("http://127.0.0.1:1", timeout=1)
        result = sc.submit({"prompt": {"1": {"class_type": "K"}}})
        assert not result.success
        assert result.error_type == "offline"
        assert result.trace_id

    def test_submit_invalid_workflow(self):
        sc = SubmissionContract("http://127.0.0.1:1", timeout=1)
        result = sc.submit({"bad": "data"})
        assert not result.success

    def test_submit_result_fields(self):
        sr = SubmissionResult(success=True, prompt_id="pid123", trace_id="abc")
        assert sr.success
        assert sr.prompt_id == "pid123"

    def test_submit_fail_offline(self):
        sr = SubmissionResult(success=False, error_type="offline", error_message="ComfyUI offline")
        assert not sr.success
        assert "offline" in sr.error_type


class TestPolling:
    def test_poll_offline(self):
        pc = PollingContract("http://127.0.0.1:1", poll_interval=0.5, default_timeout=2)
        result = pc.poll("pid123")
        assert result.done
        assert result.status in (ExecutionStatus.TIMEOUT, ExecutionStatus.UNKNOWN)
        assert result.elapsed > 0

    def test_poll_timeout(self):
        pc = PollingContract("http://127.0.0.1:1", poll_interval=0.3, default_timeout=1)
        result = pc.poll("pid123")
        assert result.status == ExecutionStatus.TIMEOUT
        assert "超时" in result.error or "timeout" in result.error.lower()

    def test_poll_result_states(self):
        pr = PollResult(status=ExecutionStatus.PENDING, prompt_id="pid")
        assert not pr.done
        assert not pr.success

        pr2 = PollResult(status=ExecutionStatus.COMPLETED, prompt_id="pid",
                         progress=1.0,
                         outputs={"1": {"images": [{"filename": "test.png"}]}})
        assert pr2.done
        assert pr2.success
        assert pr2.progress == 1.0

        pr3 = PollResult(status=ExecutionStatus.FAILED, prompt_id="pid", error="error")
        assert pr3.done
        assert not pr3.success

        pr4 = PollResult(status=ExecutionStatus.TIMEOUT, prompt_id="pid", error="timeout")
        assert pr4.done
        assert not pr4.success


class TestOutput:
    def test_parse_image(self):
        oc = OutputCollector()
        of = oc._parse_output_item({"filename": "test.png", "folder": "images"})
        assert of is not None
        assert of.filename == "test.png"
        assert of.type == "image"

    def test_parse_video(self):
        oc = OutputCollector()
        of = oc._parse_output_item({"filename": "output.mp4", "subfolder": "video"})
        assert of is not None
        assert of.filename == "output.mp4"
        assert of.type == "video"

    def test_parse_invalid(self):
        oc = OutputCollector()
        of = oc._parse_output_item({})
        assert of is None
        of2 = oc._parse_output_item({"folder": "images"})
        assert of2 is None

    def test_collect_empty(self):
        oc = OutputCollector()
        result = oc.collect("pid123", {})
        assert not result.success
        assert len(result.files) == 0

    def test_collect_with_outputs(self):
        oc = OutputCollector()
        history = {
            "pid123": {
                "outputs": {
                    "9": {"images": [{"filename": "out.png", "folder": "output"}]}
                }
            }
        }
        result = oc.collect("pid123", history)
        assert len(result.files) >= 1
        assert result.images[0].filename == "out.png"

    def test_output_classification(self):
        oc = OutputCollector()
        history = {
            "pid": {
                "outputs": {
                    "5": {"images": [{"filename": "a.png", "folder": "output"}]},
                    "6": {"videos": [{"filename": "b.mp4", "folder": "video"}]},
                }
            }
        }
        result = oc.collect("pid", history)
        assert len(result.images) >= 1
        assert len(result.videos) >= 1


class TestOrchestrator:
    def test_execute_offline(self):
        orch = ExecutionOrchestrator(base_url="http://127.0.0.1:1", default_timeout=1)
        result = orch.execute({"prompt": {"1": {"class_type": "K"}}},
                               task_type="txt2img", blueprint_used="test")
        assert not result.success
        assert result.error_stage == "submission"
        assert result.trace_id
        assert result.task_type == "txt2img"
        assert result.blueprint_used == "test"
        assert result.total_elapsed > 0

    def test_execution_result_summary(self):
        er = ExecutionResult(
            success=True,
            prompt_id="p123",
            trace_id="abc",
            task_type="txt2img",
            blueprint_used="test_bp",
            submission=SubmissionResult(success=True, prompt_id="p123", trace_id="abc"),
            polling=PollResult(status=ExecutionStatus.COMPLETED, prompt_id="p123"),
            total_elapsed=5.2,
        )
        summary = er.summary
        assert "✅" in summary
        assert "txt2img" in summary
        assert "5.2" in summary

    def test_execution_result_failure_summary(self):
        er = ExecutionResult(
            success=False,
            error="ComfyUI offline",
            error_stage="submission",
            trace_id="def",
            total_elapsed=0.5,
        )
        summary = er.summary
        assert "❌" in summary
        assert "submission" in summary


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("  Execution Contract Tests")
    print(f"{'='*50}\n")

    tests = [
        TestSubmission().test_submit_offline,
        TestSubmission().test_submit_invalid_workflow,
        TestSubmission().test_submit_result_fields,
        TestSubmission().test_submit_fail_offline,
        TestPolling().test_poll_offline,
        TestPolling().test_poll_timeout,
        TestPolling().test_poll_result_states,
        TestOutput().test_parse_image,
        TestOutput().test_parse_video,
        TestOutput().test_parse_invalid,
        TestOutput().test_collect_empty,
        TestOutput().test_collect_with_outputs,
        TestOutput().test_output_classification,
        TestOrchestrator().test_execute_offline,
        TestOrchestrator().test_execution_result_summary,
        TestOrchestrator().test_execution_result_failure_summary,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"  {passed}/{len(tests)} passed")
    print(f"{'='*50}")
