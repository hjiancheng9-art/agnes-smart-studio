"""BlueprintCompatibilityMatcher — 兼容性匹配器测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from comfyflow_compiler.capability import (
    CapabilitySnapshot, BlueprintCompatibilityMatcher, CompatibilityScore,
    NodeIndex, ModelIndex, NODE_FALLBACKS,
)


def _make_snapshot(nodes: list[str] = None, models: dict = None,
                   vram_gb: float = 16.0, online: bool = True) -> CapabilitySnapshot:
    snap = CapabilitySnapshot(comfyui_online=online)
    if nodes:
        ni = NodeIndex()
        ni.update({n: {"python_module": "comfy.test", "display_name": n} for n in nodes})
        snap.node_index = ni
        snap.nodes = nodes
    if models:
        mi = ModelIndex()
        mi.update(models)
        snap.model_index = mi
        snap.models = models
    if online:
        snap.system = {"device": {"vram_total_gb": vram_gb}}
    return snap


def _make_blueprint(bid: str = "test_bp", task: str = "txt2img",
                    required_nodes: list[str] = None,
                    required_models: list[str] = None,
                    vram: float = 8.0, name: str = "") -> dict:
    return {
        "id": bid,
        "name": name or bid,
        "capability": {
            "task_type": task,
            "models": [{"name": m, "type": "checkpoints", "required": True} for m in (required_models or [])],
        },
        "requirements": {
            "required_nodes": [{"class_type": n, "reason": "test"} for n in (required_nodes or [])],
        },
        "validation": {"required_vram_gb": vram},
    }


# ── 测试 ──


def test_score_compatible():
    """完全兼容的蓝图"""
    snap = _make_snapshot(nodes=["KSampler", "CLIPTextEncode"], models={"checkpoints": ["sd_xl.safetensors"]})
    matcher = BlueprintCompatibilityMatcher(snap)
    bp = _make_blueprint("test", required_nodes=["KSampler", "CLIPTextEncode"], required_models=["sd_xl.safetensors"])
    score = matcher.score(bp)
    assert score.compatible, f"应兼容但: {score.summary}"
    assert score.overall >= 0.5
    assert len(score.missing_nodes) == 0
    assert len(score.missing_models) == 0
    print(f"  [PASS] test_score_compatible: {score.summary}")


def test_score_missing_node():
    """缺少节点"""
    snap = _make_snapshot(nodes=["KSampler"])
    matcher = BlueprintCompatibilityMatcher(snap)
    bp = _make_blueprint("test", required_nodes=["KSampler", "VAELoader"])
    score = matcher.score(bp)
    assert not score.compatible
    assert "VAELoader" in score.missing_nodes
    assert score.node_score == 0.5
    print(f"  [PASS] test_score_missing_node: {score.summary}")


def test_score_missing_model():
    """缺少模型"""
    snap = _make_snapshot(nodes=["KSampler"], models={"checkpoints": ["sd15.safetensors"]})
    matcher = BlueprintCompatibilityMatcher(snap)
    bp = _make_blueprint("test", required_nodes=["KSampler"], required_models=["sd_xl.safetensors"])
    score = matcher.score(bp)
    assert not score.compatible
    assert "sd_xl.safetensors" in score.missing_models
    print(f"  [PASS] test_score_missing_model: {score.summary}")


def test_score_insufficient_vram():
    """VRAM 不足"""
    snap = _make_snapshot(nodes=["KSampler"], vram_gb=4.0)
    matcher = BlueprintCompatibilityMatcher(snap)
    bp = _make_blueprint("test", required_nodes=["KSampler"], vram=16.0)
    score = matcher.score(bp)
    assert score.vram_score < 1.0
    assert "VRAM" in score.vram_issue or "vram" in score.vram_issue.lower()
    print(f"  [PASS] test_score_insufficient_vram: {score.summary}")


def test_rank_orders_by_compatibility():
    """排序：兼容高的在前"""
    snap = _make_snapshot(nodes=["KSampler"], models={"checkpoints": ["sd_xl.safetensors"]})
    matcher = BlueprintCompatibilityMatcher(snap)

    bp_good = _make_blueprint("good", required_nodes=["KSampler"], required_models=["sd_xl.safetensors"])
    bp_bad = _make_blueprint("bad", required_nodes=["MissingNode"], required_models=["missing_model"])

    ranked = matcher.rank([bp_bad, bp_good])
    assert ranked[0].blueprint_id == "good"
    assert ranked[1].blueprint_id == "bad"
    assert ranked[0].overall > ranked[1].overall
    print(f"  [PASS] test_rank_orders_by_compatibility: good={ranked[0].overall:.2f} > bad={ranked[1].overall:.2f}")


def test_best_returns_best():
    """best() 返回最佳兼容"""
    snap = _make_snapshot(nodes=["KSampler", "CLIPTextEncode"], models={"checkpoints": ["sd_xl.safetensors"]})
    matcher = BlueprintCompatibilityMatcher(snap)

    bp_good = _make_blueprint("good", required_nodes=["KSampler"], required_models=["sd_xl.safetensors"])
    bp_good2 = _make_blueprint("good2", required_nodes=["KSampler", "CLIPTextEncode"], required_models=["sd_xl.safetensors"])
    bp_bad = _make_blueprint("bad", required_nodes=["MissingX"])

    best_score, idx = matcher.best([bp_bad, bp_good, bp_good2])
    assert best_score is not None
    assert best_score.compatible
    print(f"  [PASS] test_best_returns_best: {best_score.blueprint_id}")


def test_find_fallback():
    """不可用时找替代"""
    snap = _make_snapshot(nodes=["KSampler", "VAELoader"], models={"checkpoints": ["sd15.safetensors"]})
    matcher = BlueprintCompatibilityMatcher(snap)

    bad = _make_blueprint("bad", required_nodes=["VAELoader"], required_models=["flux.safetensors"])
    good = _make_blueprint("good", required_nodes=["KSampler", "VAELoader"], required_models=["sd15.safetensors"])

    fallback = matcher.find_fallback(bad, [bad, good])
    assert fallback is not None
    assert fallback.compatible
    assert fallback.blueprint_id == "good"
    print(f"  [PASS] test_find_fallback: bad→{fallback.blueprint_id}")


def test_no_fallback_if_compatible():
    """已兼容时不找替代"""
    snap = _make_snapshot(nodes=["KSampler"], models={"checkpoints": ["sd_xl.safetensors"]})
    matcher = BlueprintCompatibilityMatcher(snap)

    bp = _make_blueprint("good", required_nodes=["KSampler"], required_models=["sd_xl.safetensors"])
    fallback = matcher.find_fallback(bp, [bp])
    assert fallback is not None
    assert fallback.compatible
    assert fallback.blueprint_id == "good"
    print(f"  [PASS] test_no_fallback_if_compatible: {fallback.blueprint_id}")


def test_node_fallback_known():
    """NODE_FALLBACKS 里有对应替代"""
    assert "KSampler" in NODE_FALLBACKS
    assert "SamplerCustomAdvanced" in NODE_FALLBACKS["KSampler"]
    print(f"  [PASS] test_node_fallback_known")


def test_score_offline_snapshot():
    """离线快照时评分不崩溃"""
    snap = _make_snapshot(online=False)
    matcher = BlueprintCompatibilityMatcher(snap)
    bp = _make_blueprint("test", required_nodes=["KSampler"])
    score = matcher.score(bp)
    # 离线时所有检查返回 False，但不崩溃
    assert len(score.missing_nodes) > 0
    print(f"  [PASS] test_score_offline_snapshot")


def test_old_blueprint_format():
    """兼容旧格式 Blueprint dataclass"""
    from comfyflow_compiler.models import Blueprint
    snap = _make_snapshot(nodes=["KSampler"], models={"checkpoints": ["sd_xl.safetensors"]})
    matcher = BlueprintCompatibilityMatcher(snap)

    old_bp = Blueprint(
        name="old_bp", display_name="Old", description="",
        task_type="txt2img", required_nodes=["KSampler"],
        required_models=["sd_xl.safetensors"],
        min_vram_gb=4.0,
    )
    score = matcher.score(old_bp)
    assert score.compatible
    print(f"  [PASS] test_old_blueprint_format: {score.summary}")


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("  BlueprintCompatibilityMatcher Tests")
    print(f"{'='*50}\n")

    tests = [
        test_score_compatible,
        test_score_missing_node,
        test_score_missing_model,
        test_score_insufficient_vram,
        test_rank_orders_by_compatibility,
        test_best_returns_best,
        test_find_fallback,
        test_no_fallback_if_compatible,
        test_node_fallback_known,
        test_score_offline_snapshot,
        test_old_blueprint_format,
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
