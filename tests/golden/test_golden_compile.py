"""
ComfyFlow Compiler — Golden 端到端编译测试

语义断言而非 exact match，覆盖常见任务类型。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from comfyflow_compiler.compiler import ComfyFlowCompiler


# ── 测试用例 ──
# (name, intent, expected_task, min_nodes, has_output)

GOLDEN_CASES = [
    ("txt2img_basic", "a cat astronaut in space", 3, True),
    ("txt2img_portrait", "cinematic portrait of a warrior, dramatic lighting", 3, True),
    ("img2img_style", "turn this photo into anime style", 3, True),
    ("flux_realistic", "a photorealistic tiger in the snow, detailed fur", 3, True),
    ("anime_character", "anime girl with blue hair, holding a sword", 3, True),
]


@pytest.fixture(scope="module")
def compiler():
    return ComfyFlowCompiler()


class TestGoldenCompile:
    """端到端编译 — 语义验证"""

    @pytest.mark.parametrize("name,intent,min_nodes,has_output", GOLDEN_CASES)
    def test_compile_semantic(self, compiler, name, intent, min_nodes, has_output):
        """编译应生成语义正确的工作流"""
        result = compiler.compile(intent)

        # 1. 基本成功
        assert result.success, f"[{name}] 编译失败: {result.error}"
        assert result.error is None, f"[{name}] 有错误信息: {result.error}"

        # 2. 有 workflow JSON
        assert result.workflow_json is not None, f"[{name}] 未生成 workflow"

        # 3. 提取 prompt
        wf = result.workflow_json
        prompt = wf.get("prompt", wf)
        assert isinstance(prompt, dict), f"[{name}] prompt 不是 dict"

        # 4. 至少 min_nodes 个节点
        nodes = [v for v in prompt.values() if isinstance(v, dict) and "class_type" in v]
        assert len(nodes) >= min_nodes, (
            f"[{name}] 节点数 {len(nodes)} < 最小 {min_nodes}"
        )

        # 5. 每个节点有 class_type
        for nid, nd in prompt.items():
            if isinstance(nd, dict):
                assert "class_type" in nd, f"[{name}] 节点 {nid} 缺少 class_type"

        # 6. 检查输出节点
        class_types = {nd.get("class_type", "") for nd in nodes}
        has_output_node = any(
            ct in ("SaveImage", "VHS_VideoCombine", "VAEDecode")
            for ct in class_types
        )
        if has_output:
            assert has_output_node, f"[{name}] 缺少输出节点, 类型: {class_types}"

        # 7. quality_report 通过
        assert result.quality_report is not None, f"[{name}] 缺少质量报告"
        assert result.quality_report.passed, (
            f"[{name}] 质量未通过: {result.quality_report.detail}"
        )

        # 8. 有蓝图和硬件信息
        assert result.blueprint_used, f"[{name}] 缺少蓝图信息"
        assert result.hardware_used, f"[{name}] 缺少硬件信息"

        # 9. 用户摘要非空
        assert result.user_summary, f"[{name}] 缺少用户摘要"

    def test_different_intents_different_workflows(self, compiler):
        """不同意图应产生不同 workflow"""
        r1 = compiler.compile("a cat")
        r2 = compiler.compile("a dog running")

        assert r1.success and r2.success

        p1 = str(r1.workflow_json)
        p2 = str(r2.workflow_json)
        assert p1 != p2, "不同意图产生了相同 workflow"

    def test_compile_empty_input(self, compiler):
        """空输入不应崩溃"""
        result = compiler.compile("")
        # 可能成功也可能失败，但不应该抛异常
        assert result is not None

    def test_compile_complex_scene(self, compiler):
        """复杂场景应生成更多节点"""
        simple = compiler.compile("a cat")
        complex_wf = compiler.compile("cinematic scene of a cyberpunk city at night with neon lights, flying cars, rain reflections on wet streets, detailed 4k")

        assert simple.success and complex_wf.success

        sp = simple.workflow_json.get("prompt", simple.workflow_json)
        cp = complex_wf.workflow_json.get("prompt", complex_wf.workflow_json)

        simple_nodes = len([v for v in sp.values() if isinstance(v, dict) and "class_type" in v])
        complex_nodes = len([v for v in cp.values() if isinstance(v, dict) and "class_type" in v])
        assert complex_nodes >= simple_nodes, (
            f"复杂场景节点({complex_nodes})应 >= 简单场景({simple_nodes})"
        )

    def test_video_compile_simple(self, compiler):
        """视频编译应路由到正确的视频蓝图"""
        result = compiler.compile("a cat jumping, make a video")
        if result.success:
            assert "t2v" in result.blueprint_used or "t2v" in str(result.workflow_json), f"Not a t2v blueprint: {result.blueprint_used}"
        else:
            # 环境原因导致失败也可以接受
            assert result.blueprint_used != "missing_blueprint"

    def test_t2v_compile(self, compiler):
        """t2v 意图应路由到 t2v 蓝图并生成有效 workflow"""
        result = compiler.compile("a dog running on the beach, video")
        if result.success:
            assert result.blueprint_used in ("ltx_t2v_basic", "wan_t2v_basic"), f"Unexpected blueprint: {result.blueprint_used}"
            if result.workflow_json:
                prompt = result.workflow_json.get("prompt", result.workflow_json)
                cts = [v.get("class_type","") for v in prompt.values() if isinstance(v, dict)]
                assert any("Sampler" in ct or "Video" in ct for ct in cts), f"No video-related nodes: {cts}"
        else:
            # 如果失败，必须是环境原因（缺模型/显存），而不是 missing_blueprint
            assert result.blueprint_used != "missing_blueprint", f"t2v 不应返回 missing_blueprint: {result.error}"
            # compile_with_fallback 也应相同
            result2 = compiler.compile_with_fallback("a dog running on the beach, video")
            assert result2.blueprint_used != "missing_blueprint"

    def test_i2v_routes_correctly(self, compiler):
        """i2v 意图（含 'turn this' 关键词）应路由到 i2v"""
        result = compiler.compile("turn this picture into a video of a dog running")
        # 可能成功也可能失败（取决于 i2v 蓝图是否就绪），但不应该返回 t2v 的 missing_blueprint 错误
        if not result.success:
            assert result.blueprint_used != "missing_blueprint", "i2v 不应该返回 missing_blueprint"
