"""Capability — 运行时能力探测测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from comfyflow_compiler.capability import (
    CapabilitySnapshot, probe_comfyui,
    ComfyProbe, ComfyProbeError,
    ModelIndex, NodeIndex,
    ComfyOfflineError,
)


class TestModelIndex:
    def test_empty(self):
        idx = ModelIndex()
        assert idx.count() == 0
        assert idx.find("anything") is None

    def test_update(self):
        idx = ModelIndex()
        idx.update({"checkpoints": ["sd_xl_base.safetensors", "sd15.safetensors"],
                     "loras": ["style_lora.safetensors"]})
        assert idx.count() == 3
        assert idx.find("sd_xl") is not None
        assert idx.find("nonexistent") is None

    def test_by_folder(self):
        idx = ModelIndex()
        idx.update({"checkpoints": ["a.safetensors"]})
        entries = idx.list_by_folder("checkpoints")
        assert len(entries) == 1
        assert entries[0].name == "a.safetensors"
        assert entries[0].folder == "checkpoints"

    def test_summary(self):
        idx = ModelIndex()
        idx.update({"checkpoints": ["a"], "loras": ["b", "c"]})
        s = idx.summary()
        assert s["checkpoints"] == 1
        assert s["loras"] == 2


class TestNodeIndex:
    def test_update(self):
        idx = NodeIndex()
        raw = {
            "KSampler": {
                "display_name": "KSampler",
                "input": {"seed": "INT"},
                "output": ["LATENT"],
                "python_module": "comfy.samplers",
            },
            "VAELoader": {
                "display_name": "VAE Loader",
                "python_module": "comfy.vae",
            },
            "MyCustomNode": {
                "display_name": "My Custom",
                "python_module": "custom_nodes.my_pack",
            },
        }
        idx.update(raw)
        assert idx.count() == 3
        assert idx.exists("KSampler")
        assert not idx.exists("NonExistent")
        assert idx.get("KSampler") is not None

    def test_custom_nodes(self):
        idx = NodeIndex()
        idx.update({
            "Builtin": {"python_module": "comfy.samplers"},
            "Custom": {"python_module": "custom_nodes.my_pack"},
        })
        custom = idx.list_custom_nodes()
        assert len(custom) == 1
        assert custom[0].class_type == "Custom"

    def test_search(self):
        idx = NodeIndex()
        idx.update({
            "KSampler": {"display_name": "KSampler", "python_module": "comfy.samplers"},
            "CLIPTextEncode": {"display_name": "CLIP Text Encode", "python_module": "comfy.clip"},
        })
        results = idx.search("clip")
        assert len(results) >= 1
        assert any("CLIP" in r.class_type for r in results)


class TestCapabilitySnapshot:
    def test_offline(self):
        snap = CapabilitySnapshot()
        assert snap.has_node("anything") is False
        assert snap.has_model("anything") is False

    def test_with_data(self):
        idx = NodeIndex()
        idx.update({"KSampler": {"python_module": "comfy.samplers"}})
        midx = ModelIndex()
        midx.update({"checkpoints": ["sd_xl.safetensors"]})

        snap = CapabilitySnapshot()
        snap.node_index = idx
        snap.model_index = midx
        snap.nodes = ["KSampler"]
        snap.models = {"checkpoints": ["sd_xl.safetensors"]}
        snap.comfyui_online = True

        assert snap.has_node("KSampler")
        assert not snap.has_node("VAELoader")
        assert snap.has_model("sd_xl")
        assert not snap.has_model("flux")

    def test_summary_property(self):
        snap = CapabilitySnapshot(comfyui_online=True, comfyui_version="v1.0",
                                   node_count=100, custom_node_count=5,
                                   model_count=50, generated_at="now")
        s = snap.summary
        assert s["comfyui_online"] is True
        assert "100" in s["nodes"]
        assert "50" in s["models"]

    def test_check_blueprint_compatibility(self):
        snap = CapabilitySnapshot()
        snap.node_index = NodeIndex()
        snap.node_index.update({"KSampler": {"python_module": "comfy.samplers"}})
        snap.model_index = ModelIndex()
        snap.model_index.update({"checkpoints": ["sd_xl.safetensors"]})

        blueprint = {
            "requirements": {
                "required_nodes": [
                    {"class_type": "KSampler", "reason": "采样"},
                    {"class_type": "MissingNode", "reason": "缺失"},
                ],
            },
            "capability": {
                "models": [
                    {"name": "sd_xl.safetensors", "type": "checkpoints", "required": True},
                    {"name": "flux.safetensors", "type": "checkpoints", "required": True},
                ],
            },
            "validation": {},
        }
        issues = snap.check_blueprint_compatibility(blueprint)
        assert len(issues) >= 2  # missing_node + missing_model


class TestComfyProbe:
    def test_offline(self):
        probe = ComfyProbe("http://127.0.0.1:1", timeout=1.0)
        assert probe.check_online() is False
        assert probe.get_version() == ""
        assert probe.get_nodes() == {}
        assert probe.get_all_models() == {}


class TestProbeComfyUI:
    def test_offline(self):
        snap = probe_comfyui("http://127.0.0.1:1", timeout=1.0)
        assert snap.comfyui_online is False
        assert snap.node_count == 0
        assert snap.model_count == 0
        assert snap.summary["comfyui_online"] is False
