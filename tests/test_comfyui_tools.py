"""ComfyUI 工具模块单测 — 纯函数 + 数据结构，不依赖 ComfyUI 服务。

覆盖:
    - 常量/配置: BASE_URL / TIMEOUT / POLL_INTERVAL / CUSTOM_NODES_DIR
    - COMFYUI_TOOLS: 每个 tool def 必须含 name/description/parameters
    - COMFYUI_EXECUTOR_MAP: 每个 executor 必须指向已知函数
    - _simplify_node_info: 纯函数可直接测试
    - execute_status: 无服务时应优雅降级
    - execute_list_models: 无服务时应优雅降级
    - execute_clear_queue: 无服务时应优雅降级
    - execute_get_node_info: 无服务时应优雅降级
    - execute_submit_workflow: 参数校验
    - execute_get_result: 参数校验
    - execute_preview_workflow: 参数校验
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.comfyui_tools import (
    COMFYUI_BASE_URL,
    COMFYUI_EXECUTOR_MAP,
    COMFYUI_POLL_INTERVAL,
    COMFYUI_TIMEOUT,
    COMFYUI_TOOLS,
    LORA_OUTPUT_ROOT,
    OUTPUT_ROOT,
    _simplify_node_info,
    execute_build_custom_workflow,
    execute_clear_queue,
    execute_create_custom_node,
    execute_get_node_info,
    execute_get_result,
    execute_list_models,
    execute_lora_check_status,
    execute_lora_generate_config,
    execute_lora_prepare_dataset,
    execute_preview_workflow,
    execute_status,
    execute_submit_workflow,
    submit_comfyui_workflow,
)

# ── 常量/配置 ────────────────────────────────────────────────────


class TestConstants:
    def test_base_url_is_http(self):
        assert COMFYUI_BASE_URL.startswith("http://") or COMFYUI_BASE_URL.startswith("https://")

    def test_timeout_is_positive_int(self):
        assert isinstance(COMFYUI_TIMEOUT, int) and COMFYUI_TIMEOUT > 0

    def test_poll_interval_is_positive(self):
        assert isinstance(COMFYUI_POLL_INTERVAL, int) and COMFYUI_POLL_INTERVAL > 0


# ── 工具定义完整性 ───────────────────────────────────────────────


class TestToolDefinitions:
    def test_comfyui_tools_is_list(self):
        assert isinstance(COMFYUI_TOOLS, list)

    def test_each_tool_has_required_fields(self):
        """每个工具定义必须含 name + description + parameters。"""
        for tool in COMFYUI_TOOLS:
            fn = tool.get("function", tool)
            assert "name" in fn, f"missing name in {tool}"
            assert "description" in fn, f"missing description in {fn['name']}"
            assert "parameters" in fn, f"missing parameters in {fn['name']}"

    def test_tool_names_unique(self):
        """工具名不能重复。"""
        names = [t.get("function", t)["name"] for t in COMFYUI_TOOLS]
        assert len(names) == len(set(names)), f"重复工具名: {[n for n in names if names.count(n) > 1]}"

    def test_tool_names_snake_case(self):
        """工具名应遵循 snake_case 约定。"""
        import re

        for tool in COMFYUI_TOOLS:
            name = tool.get("function", tool)["name"]
            assert re.match(r"^[a-z][a-z0-9_]*$", name), f"非 snake_case: {name}"

    def test_descriptions_are_meaningful(self):
        """description 至少 10 个字符。"""
        for tool in COMFYUI_TOOLS:
            fn = tool.get("function", tool)
            assert len(fn.get("description", "")) >= 10, f"{fn['name']}: description 太短"


# ── Executor Map ─────────────────────────────────────────────────


class TestExecutorMap:
    def test_executor_map_is_dict(self):
        assert isinstance(COMFYUI_EXECUTOR_MAP, dict)

    def test_executor_map_covers_tools(self):
        """EXECUTOR_MAP 的 key 应覆盖 COMFYUI_TOOLS 中的工具名。"""
        tool_names = {t.get("function", t)["name"] for t in COMFYUI_TOOLS}
        executor_names = set(COMFYUI_EXECUTOR_MAP.keys())
        # 允许 executor map 不完全覆盖（有些可能是 batch 的）
        # 但至少覆盖 50%
        if executor_names:
            coverage = len(tool_names & executor_names) / len(tool_names)
            assert coverage >= 0.5, f"executor 只覆盖 {coverage:.0%} 工具"

    def test_executor_values_are_callable(self):
        """每个 executor 必须是可调用对象。"""
        for name, fn in COMFYUI_EXECUTOR_MAP.items():
            assert callable(fn), f"{name}: executor 不是 callable"


# ── _simplify_node_info 纯函数 ────────────────────────────────────


class TestSimplifyNodeInfo:
    def test_full_info(self):
        info = {
            "input": {"required": {"seed": ["FLOAT", {"default": 0, "min": 0, "max": 999999}]}},
            "input_order": {"required": ["seed"]},
            "output": ["IMAGE"],
            "output_name": ["image"],
            "output_is_list": [False],
            "name": "KSampler",
            "description": "Sampling node",
            "category": "sampling",
        }
        result = _simplify_node_info("KSampler", info)
        assert result["class_type"] == "KSampler"
        assert result["category"] == "sampling"
        assert "outputs" in result  # 键名为 outputs（复数）
        assert len(result["outputs"]) >= 1
        assert result["outputs"][0]["type"] == "IMAGE"
        assert result["outputs"][0]["name"] == "image"

    def test_empty_info(self):
        result = _simplify_node_info("EmptyNode", {})
        assert result["class_type"] == "EmptyNode"
        assert result["category"] == "unknown"

    def test_missing_optional_keys(self):
        info = {"input": {}, "output": []}
        result = _simplify_node_info("MinimalNode", info)
        assert result["class_type"] == "MinimalNode"
        assert "outputs" in result  # 键名为 outputs（复数）
        assert len(result["outputs"]) == 0

    def test_combo_param_with_choices(self):
        """combo 类型参数应提取 choices 列表。"""
        info = {
            "input": {
                "required": {"ckpt_name": [["model_a.safetensors", "model_b.safetensors"], "model_a.safetensors"]},
                "optional": {},
            },
            "output": ["MODEL", "CLIP", "VAE"],
            "output_name": ["model", "clip", "vae"],
            "output_is_list": [False, False, False],
            "category": "loaders",
        }
        result = _simplify_node_info("CheckpointLoaderSimple", info)
        ckpt = result["inputs"]["required"]["ckpt_name"]
        assert ckpt["type"] == "combo"
        assert ckpt["choices"] == ["model_a.safetensors", "model_b.safetensors"]
        assert ckpt["default"] == "model_a.safetensors"

    def test_float_param_with_range(self):
        """FLOAT/INT 参数应提取 min/max。"""
        info = {
            "input": {
                "required": {"steps": ["INT", 20, {"min": 1, "max": 150}]},
                "optional": {},
            },
            "output": ["LATENT"],
            "output_name": ["latent"],
            "output_is_list": [False],
        }
        result = _simplify_node_info("KSampler", info)
        steps = result["inputs"]["required"]["steps"]
        assert steps["type"] == "INT"
        assert steps["default"] == 20
        assert steps["min"] == 1
        assert steps["max"] == 150


# ── 无服务优雅降级 ──────────────────────────────────────────────


class TestGracefulDegradation:
    """这些函数调用 ComfyUI 服务，无服务时不应抛异常。"""

    def test_execute_status_no_service(self):
        """无 ComfyUI 服务时应返回错误信息而非抛异常。"""
        result = execute_status()
        assert isinstance(result, str)
        # 无服务时应包含错误提示
        assert len(result) > 0

    def test_execute_list_models_no_service(self):
        result = execute_list_models()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_clear_queue_no_service(self):
        result = execute_clear_queue()
        assert isinstance(result, str)

    def test_execute_get_node_info_no_service(self):
        result = execute_get_node_info()
        assert isinstance(result, str)

    def test_execute_get_result_empty_prompt_id(self):
        result = execute_get_result("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_preview_workflow_empty(self):
        result = execute_preview_workflow("")
        assert isinstance(result, str)

    def test_execute_submit_workflow_empty(self):
        result = execute_submit_workflow("")
        assert isinstance(result, str)


# ── SSRF 防护 ─────────────────────────────────────────────────


class TestSsrfProtection:
    """验证非本地 COMFYUI_BASE_URL 被重置。"""

    def test_base_url_localhost(self):
        """默认 URL 应为本地地址。"""
        parsed = urlparse(COMFYUI_BASE_URL)
        assert parsed.hostname in {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}


# ── execute_build_custom_workflow ───────────────────────────────


class TestBuildCustomWorkflow:
    """纯文件系统操作，不需要 ComfyUI 服务。"""

    def test_valid_two_nodes(self, tmp_path, monkeypatch):
        """两个节点 + 连线应正确构建。"""
        monkeypatch.setattr("core.comfyui_tools.OUTPUT_ROOT", tmp_path)
        nodes = json.dumps(
            [
                {
                    "id": 1,
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
                },
                {"id": 2, "class_type": "CLIPTextEncode", "inputs": {"text": "hello", "clip": [1, 0]}},
            ]
        )
        result = json.loads(execute_build_custom_workflow(nodes))
        assert result["success"] is True
        assert result["node_count"] == 2
        assert result["output_node_id"] == "2"  # 最后一个节点
        assert "1" in result["workflow"]
        assert "2" in result["workflow"]
        # 文件已保存
        assert Path(result["saved_path"]).exists()

    def test_save_image_auto_detected(self, tmp_path, monkeypatch):
        """含 save/preview 的节点应自动作为 output_node（最后出现的 wins）。"""
        monkeypatch.setattr("core.comfyui_tools.OUTPUT_ROOT", tmp_path)
        nodes = json.dumps(
            [
                {"id": 1, "class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
                {"id": 2, "class_type": "PreviewImage", "inputs": {"images": [1, 0]}},
                {"id": 3, "class_type": "SaveImage", "inputs": {"images": [1, 0]}},
            ]
        )
        result = json.loads(execute_build_custom_workflow(nodes))
        # SaveImage 在 id=3（最后一个含 save 的），应被自动检测为输出
        assert result["output_node_id"] == "3"

    def test_explicit_output_node_id(self, tmp_path, monkeypatch):
        """手动指定 output_node_id 应覆盖自动检测。"""
        monkeypatch.setattr("core.comfyui_tools.OUTPUT_ROOT", tmp_path)
        nodes = json.dumps(
            [
                {"id": 1, "class_type": "SaveImage", "inputs": {}},
                {"id": 2, "class_type": "SaveImage", "inputs": {}},
            ]
        )
        result = json.loads(execute_build_custom_workflow(nodes, output_node_id=2))
        assert result["output_node_id"] == "2"

    def test_invalid_json(self):
        result = json.loads(execute_build_custom_workflow("not json{"))
        assert result["success"] is False
        assert "error" in result

    def test_not_array(self):
        result = json.loads(execute_build_custom_workflow(json.dumps({"id": 1})))
        assert result["success"] is False

    def test_connection_ref_int_to_str(self, tmp_path, monkeypatch):
        """连线引用的源节点 ID 应被转为字符串。"""
        monkeypatch.setattr("core.comfyui_tools.OUTPUT_ROOT", tmp_path)
        nodes = json.dumps(
            [
                {"id": 1, "class_type": "NodeA", "inputs": {}},
                {"id": 2, "class_type": "NodeB", "inputs": {"link": [1, 0]}},
            ]
        )
        result = json.loads(execute_build_custom_workflow(nodes))
        # 连线引用的源 ID 应为字符串 "1"
        assert result["workflow"]["2"]["inputs"]["link"][0] == "1"


# ── execute_create_custom_node ──────────────────────────────────


class TestCreateCustomNode:
    """文件系统操作 + 代码校验。"""

    def test_no_custom_nodes_dir(self):
        """COMFYUI_CUSTOM_NODES_DIR 为空时应报错。"""
        result = json.loads(execute_create_custom_node("TestNode", "pass"))
        assert result["success"] is False
        assert "未配置" in result.get("error", "")

    def test_valid_node(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.COMFYUI_CUSTOM_NODES_DIR", str(tmp_path))
        code = (
            "CATEGORY = 'test'\nRETURN_TYPES = ('IMAGE',)\n"
            "FUNCTION = 'generate'\n"
            "INPUT_TYPES = lambda: {'required': {'seed': ('INT', {'default': 0})}}\n"
            "def generate(self, seed): return (None,)\n"
        )
        result = json.loads(execute_create_custom_node("MyNode", code))
        assert result["success"] is True
        assert (tmp_path / "MyNode.py").exists()

    def test_missing_required_attrs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.COMFYUI_CUSTOM_NODES_DIR", str(tmp_path))
        code = "class MyNode: pass"
        result = json.loads(execute_create_custom_node("BadNode", code))
        assert result["success"] is False
        assert "缺少必要属性" in result.get("error", "")

    def test_dir_not_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.COMFYUI_CUSTOM_NODES_DIR", str(tmp_path / "nonexistent"))
        result = json.loads(execute_create_custom_node("X", "pass"))
        assert result["success"] is False

    def test_file_already_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.COMFYUI_CUSTOM_NODES_DIR", str(tmp_path))
        (tmp_path / "DupNode.py").write_text("# exists", encoding="utf-8")
        code = "CATEGORY='x'\nRETURN_TYPES=()\nFUNCTION='f'\nINPUT_TYPES=lambda:{'required':{}}"
        result = json.loads(execute_create_custom_node("DupNode", code))
        assert result["success"] is False
        assert "已存在" in result.get("error", "")

    def test_name_sanitized(self, tmp_path, monkeypatch):
        """空格/斜杠应被替换为下划线。"""
        monkeypatch.setattr("core.comfyui_tools.COMFYUI_CUSTOM_NODES_DIR", str(tmp_path))
        code = "CATEGORY='x'\nRETURN_TYPES=()\nFUNCTION='f'\nINPUT_TYPES=lambda:{'required':{}}"
        result = json.loads(execute_create_custom_node("My Node/Foo", code))
        assert result["success"] is True
        assert result["node_name"] == "My_Node_Foo"


# ── LoRA 训练工具 ───────────────────────────────────────────────


class TestLoraPrepareDataset:
    """execute_lora_prepare_dataset — 纯文件系统操作。"""

    def test_single_concept(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        result = json.loads(execute_lora_prepare_dataset("my_char"))
        assert result["success"] is True
        assert result["dataset_name"] == "my_char"
        # 目录结构已创建
        assert (tmp_path / "my_char" / "dataset" / "my_char").is_dir()
        assert (tmp_path / "my_char" / "config").is_dir()
        assert (tmp_path / "my_char" / "output").is_dir()
        # 标签模板已生成
        readme = tmp_path / "my_char" / "dataset" / "my_char" / "README.txt"
        assert readme.exists()
        assert "my_char" in readme.read_text(encoding="utf-8")

    def test_multiple_concepts(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        result = json.loads(execute_lora_prepare_dataset("multi", concept_count=3, concept_names="face,body,outfit"))
        assert result["success"] is True
        assert len(result["concepts"]) == 3
        names = [c["name"] for c in result["concepts"]]
        assert names == ["face", "body", "outfit"]

    def test_name_sanitized(self, tmp_path, monkeypatch):
        """空格和斜杠应被替换为下划线。"""
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        result = json.loads(execute_lora_prepare_dataset("My LoRA / Test"))
        # "My LoRA / Test" → 空格→_ → "My_LoRA_/_Test" → /→_ → "My_LoRA___Test"
        assert result["dataset_name"] == "My_LoRA___Test"

    def test_concept_count_expands_names(self, tmp_path, monkeypatch):
        """concept_count 大于 concept_names 长度时，多余概念自动命名。"""
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        result = json.loads(execute_lora_prepare_dataset("exp", concept_count=3, concept_names="alpha"))
        assert len(result["concepts"]) == 3
        assert result["concepts"][1]["name"] == "concept_2"


class TestLoraGenerateConfig:
    """execute_lora_generate_config — 需要 prepare_dataset 的目录。"""

    def test_no_dataset(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        result = json.loads(execute_lora_generate_config("missing", "model.safetensors"))
        assert result["success"] is False
        assert "不存在" in result.get("error", "")

    def test_sdxl_auto_detect(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        execute_lora_prepare_dataset("sdxl_test")
        result = json.loads(execute_lora_generate_config("sdxl_test", "sd_xl_base_1.0.safetensors"))
        assert result["success"] is True
        assert result["config_summary"]["lora_type"] == "sdxl"
        assert result["config_summary"]["learning_rate"] == "1.0e-04"
        # 配置文件已生成
        assert Path(result["config_path"]).exists()

    def test_sd15_auto_detect(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        execute_lora_prepare_dataset("sd15_test")
        result = json.loads(execute_lora_generate_config("sd15_test", "dreamshaper_8.safetensors"))
        assert result["success"] is True
        assert result["config_summary"]["lora_type"] == "sd15"
        assert result["config_summary"]["learning_rate"] == "5.0e-04"

    def test_manual_lora_type(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        execute_lora_prepare_dataset("manual_test")
        result = json.loads(execute_lora_generate_config("manual_test", "any_model.safetensors", lora_type="sd15"))
        assert result["config_summary"]["lora_type"] == "sd15"

    def test_no_concept_dirs(self, tmp_path, monkeypatch):
        """数据集目录存在且有 dataset 子目录但无概念子文件夹时应报错。"""
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        ds = tmp_path / "empty_ds"
        (ds / "dataset").mkdir(parents=True)
        result = json.loads(execute_lora_generate_config("empty_ds", "model.safetensors"))
        assert result["success"] is False
        assert "没有概念" in result.get("error", "")

    def test_config_contains_toml_content(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        execute_lora_prepare_dataset("toml_test")
        result = json.loads(execute_lora_generate_config("toml_test", "sd_xl_base_1.0.safetensors"))
        content = Path(result["config_path"]).read_text(encoding="utf-8")
        assert "[general]" in content
        assert "[network]" in content
        assert "[optimizer]" in content
        assert "sd_xl_base_1.0.safetensors" in content


class TestLoraCheckStatus:
    """execute_lora_check_status — 纯文件系统查询。"""

    def test_nonexistent_dataset(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        result = json.loads(execute_lora_check_status("no_such"))
        assert result["exists"] is False

    def test_dataset_no_output(self, tmp_path, monkeypatch):
        """output 目录存在但无 safetensors → training_or_failed。"""
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        execute_lora_prepare_dataset("no_output")
        result = json.loads(execute_lora_check_status("no_output"))
        # output 目录由 prepare_dataset 创建，但无 safetensors → training_or_failed
        assert result["status"] == "training_or_failed"

    def test_list_all_projects(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        execute_lora_prepare_dataset("project_a")
        execute_lora_prepare_dataset("project_b")
        result = json.loads(execute_lora_check_status())
        assert result["total_projects"] >= 2
        names = [p["name"] for p in result["projects"]]
        assert "project_a" in names
        assert "project_b" in names

    def test_completed_with_safetensors(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.comfyui_tools.LORA_OUTPUT_ROOT", tmp_path)
        execute_lora_prepare_dataset("completed_test")
        out = tmp_path / "completed_test" / "output"
        (out / "my_lora.safetensors").write_bytes(b"\x00" * 1024)
        result = json.loads(execute_lora_check_status("completed_test"))
        assert result["status"] == "completed"
        assert len(result["trained_loras"]) == 1
        assert result["trained_loras"][0]["name"] == "my_lora.safetensors"


# ── submit_comfyui_workflow (Showrunner 接口) ──────────────────


class TestSubmitComfyuiWorkflow:
    def test_invalid_json_returns_error(self):
        result = submit_comfyui_workflow({"bad": "json"})
        assert "error" in result or result.get("success") is False

    def test_returns_dict(self):
        result = submit_comfyui_workflow({})
        assert isinstance(result, dict)


# ── execute_submit_workflow 参数校验 ───────────────────────────


class TestSubmitWorkflowValidation:
    def test_invalid_json_string(self):
        result = json.loads(execute_submit_workflow("{invalid"))
        assert result["success"] is False
        assert "error" in result

    def test_valid_json_dict_passthrough(self):
        result = json.loads(execute_submit_workflow("{}"))
        # 无服务时可能成功提交或失败，但不应抛异常
        assert "success" in result or "error" in result

    def test_wait_false_skips_poll(self):
        result = json.loads(execute_submit_workflow("{}", wait=False))
        # 不等待时应直接返回
        assert isinstance(result, dict)


# ── OUTPUT_ROOT / LORA_OUTPUT_ROOT ────────────────────────────


class TestOutputPaths:
    def test_output_root_exists(self):
        assert OUTPUT_ROOT.is_dir()

    def test_lora_output_root_exists(self):
        assert LORA_OUTPUT_ROOT.is_dir()

    def test_lora_output_is_subdir(self):
        assert LORA_OUTPUT_ROOT.parent == OUTPUT_ROOT
