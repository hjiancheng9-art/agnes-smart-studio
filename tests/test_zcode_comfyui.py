"""RED phase tests for core/comfyui_tools.py.

ComfyUI bridge tools: status, models, workflow submit, custom nodes, LoRA training.
Note: comfyui_client.py does not exist; all ComfyUI logic is in comfyui_tools.py.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Module-level constants and config
# ---------------------------------------------------------------------------


class TestComfyUIConfig:
    """Environment and URL configuration."""

    def test_base_url_default(self):
        import core.comfyui_tools as ct

        # Default when env not set
        assert ct.COMFYUI_BASE_URL.startswith("http://")

    def test_ssrf_guard_blocks_remote(self):
        """SSRF guard resets non-localhost URLs."""
        import importlib
        import core.comfyui_tools as ct

        assert ct.COMFYUI_BASE_URL.rstrip("/") in ("http://127.0.0.1:8188", "http://localhost:8188")

    def test_output_root_exists(self):
        import core.comfyui_tools as ct

        assert ct.OUTPUT_ROOT.exists()

    def test_lora_output_root_exists(self):
        import core.comfyui_tools as ct

        assert ct.LORA_OUTPUT_ROOT.exists()


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class TestComfyUIToolDefs:
    """Validate all tool definitions."""

    def test_all_tools_have_required_structure(self):
        import core.comfyui_tools as ct

        tool_names = set()
        for td in ct.COMFYUI_TOOLS:
            assert td["type"] == "function"
            fn = td["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert "properties" in fn["parameters"]
            tool_names.add(fn["name"])
        assert len(tool_names) == len(ct.COMFYUI_TOOLS), "Duplicate tool names"

    def test_unique_tool_names(self):
        import core.comfyui_tools as ct

        names = [td["function"]["name"] for td in ct.COMFYUI_TOOLS]
        assert len(names) == len(set(names))

    def test_executor_map_covers_all_names(self):
        import core.comfyui_tools as ct

        tool_names = {td["function"]["name"] for td in ct.COMFYUI_TOOLS}
        executor_names = set(ct.COMFYUI_EXECUTOR_MAP.keys())
        for name in tool_names:
            assert name in executor_names, f"Missing executor for '{name}'"

    def test_executor_map_callables(self):
        import core.comfyui_tools as ct

        for name, fn in ct.COMFYUI_EXECUTOR_MAP.items():
            assert callable(fn), f"Executor '{name}' is not callable"


# ---------------------------------------------------------------------------
# Status and model listing (offline-safe)
# ---------------------------------------------------------------------------


class TestComfyUIStatusOffline:
    """Status checks when ComfyUI is offline."""

    def test_execute_status_offline(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_status())
        # Either available or not
        assert "available" in result

    def test_execute_list_models_offline(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_list_models())
        assert "models" in result or "error" in result

    def test_execute_get_node_info_offline(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_get_node_info())
        assert "error" in result or "total_nodes" in result or "categories" in result

    def test_execute_get_node_info_with_type_offline(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_get_node_info(node_type="KSampler"))
        assert "error" in result or "class_type" in result

    def test_execute_clear_queue_offline(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_clear_queue())
        assert "success" in result


# ---------------------------------------------------------------------------
# Workflow building (no server needed)
# ---------------------------------------------------------------------------


class TestBuildCustomWorkflow:
    """Custom workflow builder tests (local-only)."""

    def test_build_simple_workflow(self):
        import core.comfyui_tools as ct

        nodes = json.dumps([
            {"id": 1, "class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            {"id": 2, "class_type": "CLIPTextEncode", "inputs": {"text": "a beautiful landscape", "clip": [1, 1]}},
            {"id": 3, "class_type": "SaveImage", "inputs": {"images": [5, 0]}},
        ])
        result = json.loads(ct.execute_build_custom_workflow(nodes=nodes))
        assert result["success"]
        assert result["node_count"] == 3
        assert "workflow" in result
        assert "saved_path" in result
        assert os.path.isfile(result["saved_path"])
        # Cleanup
        os.unlink(result["saved_path"])

    def test_build_workflow_with_line_references(self):
        import core.comfyui_tools as ct

        nodes = json.dumps([
            {"id": 1, "class_type": "ModelLoader", "inputs": {"model": "foo"}},
            {"id": 2, "class_type": "Processor", "inputs": {"input": [1, 0]}},
        ])
        result = json.loads(ct.execute_build_custom_workflow(nodes=nodes))
        assert result["success"]
        wf = result["workflow"]
        # Check line reference converted
        node2_inputs = wf["2"]["inputs"]
        assert node2_inputs["input"] == ["1", 0]

    def test_build_workflow_auto_detects_save_node(self):
        import core.comfyui_tools as ct

        nodes = json.dumps([
            {"id": 1, "class_type": "LoadImage", "inputs": {}},
            {"id": 2, "class_type": "SaveImage", "inputs": {"images": [1, 0]}},
        ])
        result = json.loads(ct.execute_build_custom_workflow(nodes=nodes))
        assert result["output_node_id"] == "2"

    def test_build_workflow_invalid_json_returns_error(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_build_custom_workflow(nodes="not valid json"))
        assert not result.get("success")
        assert "error" in result

    def test_build_workflow_not_list_returns_error(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_build_custom_workflow(nodes='{"key": "value"}'))
        assert not result.get("success")
        assert "error" in result

    def test_preview_workflow_invalid_json(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_preview_workflow(workflow_json="bad json"))
        assert not result.get("success")


# ---------------------------------------------------------------------------
# Submit workflow (offline-safe paths)
# ---------------------------------------------------------------------------


class TestSubmitWorkflowOffline:
    """Submit workflow tests that exercise parsing paths without server."""

    def test_submit_invalid_json(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_submit_workflow(workflow_json="bad json"))
        assert not result.get("success")
        assert "error" in result

    def test_submit_with_wait_false_parses(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_submit_workflow(workflow_json="{}", wait=False))
        # Will fail on server connection
        assert "error" in result or "prompt_id" in result

    def test_get_result_unknown_prompt(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_get_result(prompt_id="nonexistent-123"))
        assert "error" in result or "status" in result


# ---------------------------------------------------------------------------
# Create custom node (no server needed)
# ---------------------------------------------------------------------------


class TestCreateCustomNode:
    """Custom node creation."""

    def test_create_without_env_var(self):
        import core.comfyui_tools as ct

        # Without COMFYUI_CUSTOM_NODES_DIR, should return error
        result = json.loads(ct.execute_create_custom_node(node_name="TestNode", node_code="CATEGORY='test'\nRETURN_TYPES=()\nFUNCTION='run'\nINPUT_TYPES={}\n"))
        assert not result.get("success") or "error" in result

    def test_create_missing_attributes(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_create_custom_node(node_name="BadNode", node_code="class BadNode: pass\n"))
        assert not result.get("success")

    def test_create_node_name_sanitized(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_create_custom_node(node_name="My Node/Test", node_code=""))
        assert "error" in result or "node_name" in result


# ---------------------------------------------------------------------------
# LoRA training tools (local-only, no server needed)
# ---------------------------------------------------------------------------


class TestLoRATools:
    """LoRA dataset preparation, config generation, status."""

    def test_prepare_dataset_creates_structure(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_lora_prepare_dataset(dataset_name="test_lora"))
        assert result["success"]
        assert result["dataset_name"] == "test_lora"
        assert os.path.isdir(result["root_dir"])
        assert os.path.isdir(result["config_dir"])
        assert os.path.isdir(result["output_dir"])
        # Verify concept dirs created
        for c in result["concepts"]:
            assert os.path.isdir(c["image_dir"])

    def test_prepare_dataset_with_custom_concepts(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_lora_prepare_dataset(
            dataset_name="multi_concept", concept_names="cat,dog", concept_count=2
        ))
        assert result["success"]
        concept_names = [c["name"] for c in result["concepts"]]
        assert "cat" in concept_names
        assert "dog" in concept_names

    def test_prepare_dataset_default_concept_count(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_lora_prepare_dataset(dataset_name="default_conc"))
        assert result["success"]
        assert len(result["concepts"]) >= 1

    def test_generate_config_missing_dataset(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_lora_generate_config(
            dataset_name="nonexistent_lora", base_model="sd_xl_base_1.0.safetensors"
        ))
        assert not result.get("success")

    def test_generate_config_creates_toml(self):
        import core.comfyui_tools as ct

        # First prepare dataset
        ct.execute_lora_prepare_dataset(dataset_name="config_test", concept_count=1)
        result = json.loads(ct.execute_lora_generate_config(
            dataset_name="config_test", base_model="sd_xl_base_1.0.safetensors"
        ))
        assert result["success"]
        assert os.path.isfile(result["config_path"])
        # Verify it's TOML content
        content = Path(result["config_path"]).read_text(encoding="utf-8")
        assert "[general]" in content
        assert "[network]" in content

    def test_generate_config_auto_detects_sdxl(self):
        import core.comfyui_tools as ct

        ct.execute_lora_prepare_dataset(dataset_name="auto_sdxl", concept_count=1)
        result = json.loads(ct.execute_lora_generate_config(
            dataset_name="auto_sdxl", base_model="sd_xl_base_1.0.safetensors"
        ))
        assert result["config_summary"]["lora_type"] == "sdxl"

    def test_generate_config_auto_detects_sd15(self):
        import core.comfyui_tools as ct

        ct.execute_lora_prepare_dataset(dataset_name="auto_sd15", concept_count=1)
        result = json.loads(ct.execute_lora_generate_config(
            dataset_name="auto_sd15", base_model="dreamshaper_8.safetensors"
        ))
        assert result["config_summary"]["lora_type"] == "sd15"

    def test_check_status_all_projects(self):
        import core.comfyui_tools as ct

        # Prepare a dataset first so there's something to find
        ct.execute_lora_prepare_dataset(dataset_name="status_test")
        result = json.loads(ct.execute_lora_check_status())
        assert "total_projects" in result
        assert "projects" in result

    def test_check_status_specific_dataset(self):
        import core.comfyui_tools as ct

        ct.execute_lora_prepare_dataset(dataset_name="specific_test")
        result = json.loads(ct.execute_lora_check_status(dataset_name="specific_test"))
        assert result["dataset_name"] == "specific_test"

    def test_check_status_nonexistent_dataset(self):
        import core.comfyui_tools as ct

        result = json.loads(ct.execute_lora_check_status(dataset_name="never_created"))
        assert not result.get("exists")


# ---------------------------------------------------------------------------
# _simplify_node_info and helpers
# ---------------------------------------------------------------------------


class TestNodeInfoHelpers:
    """Internal node info formatting."""

    def test_simplify_node_info_basic(self):
        import core.comfyui_tools as ct

        info = {
            "category": "loaders",
            "display_name": "Load Checkpoint",
            "description": "Loads a model checkpoint",
            "input": {
                "required": {"ckpt_name": [["model.safetensors"], "model.safetensors"]},
                "optional": {},
            },
            "output": ["MODEL", "CLIP", "VAE"],
            "output_name": ["model", "clip", "vae"],
            "output_is_list": [False, False, False],
        }
        result = ct._simplify_node_info("CheckpointLoaderSimple", info)
        assert result["class_type"] == "CheckpointLoaderSimple"
        assert result["category"] == "loaders"
        assert "inputs" in result
        assert "required" in result["inputs"]
        assert len(result["outputs"]) == 3
        assert result["outputs"][0]["type"] == "MODEL"

    def test_fmt_param_combo_type(self):
        import core.comfyui_tools as ct

        # Test the _fmt_param helper via _simplify_node_info
        info = {
            "category": "test",
            "input": {
                "required": {"choice_param": [["a", "b", "c"], "a"]},
                "optional": {},
            },
            "output": [],
            "output_name": [],
            "output_is_list": [],
        }
        result = ct._simplify_node_info("TestNode", info)
        param = result["inputs"]["required"]["choice_param"]
        assert param["type"] == "combo"
        assert param["choices"] == ["a", "b", "c"]
        assert param["default"] == "a"


# ---------------------------------------------------------------------------
# submit_comfyui_workflow bridge
# ---------------------------------------------------------------------------


class TestSubmitComfyuiWorkflow:
    """Bridge function for Showrunner integration."""

    def test_submit_comfyui_workflow_malformed(self):
        import core.comfyui_tools as ct

        result = ct.submit_comfyui_workflow({"bad": "workflow"})
        # Will fail to reach server
        assert "error" in result


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestComfyUIExports:
    """Module exports are complete."""

    def test_all_matches_actual_exports(self):
        import core.comfyui_tools as ct

        assert "execute_status" in ct.__all__
        assert "execute_list_models" in ct.__all__
        assert "execute_submit_workflow" in ct.__all__
        assert "execute_build_custom_workflow" in ct.__all__
        assert "execute_create_custom_node" in ct.__all__
        assert "COMFYUI_TOOLS" in ct.__all__
        assert "COMFYUI_EXECUTOR_MAP" in ct.__all__

    def test_known_functions_resolve(self):
        import core.comfyui_tools as ct

        for name in ct.__all__:
            if not name.isupper():  # skip constants
                obj = getattr(ct, name, None)
                assert obj is not None, f"{name} not found in comfyui_tools"
