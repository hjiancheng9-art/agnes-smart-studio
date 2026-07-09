"""
Blueprint 子包 — Golden 回归测试

测试蓝图加载、校验、pack/unpack 的语义正确性。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from comfyflow_compiler.blueprint.schema import BLUEPRINT_JSON_SCHEMA, BLUEPRINT_SCHEMA_VERSION, validate_schema_completeness
from comfyflow_compiler.blueprint.errors import BlueprintValidationError, BlueprintNotFoundError
from comfyflow_compiler.blueprint.validator import BlueprintValidator
from comfyflow_compiler.blueprint.loader import BlueprintLoader
from comfyflow_compiler.blueprint.normalizer import WorkflowNormalizer, NormalizedWorkflow
from comfyflow_compiler.blueprint.packer import BlueprintPacker
from comfyflow_compiler.blueprint.registry import BlueprintRegistry


# ── Fixtures ──


@pytest.fixture
def validator():
    return BlueprintValidator()


@pytest.fixture
def loader():
    return BlueprintLoader()


@pytest.fixture
def packer():
    return BlueprintPacker()


@pytest.fixture
def registry():
    return BlueprintRegistry()


@pytest.fixture
def flux_blueprint(loader) -> dict:
    """加载 flux_txt2img_basic 蓝图"""
    return loader.load("flux_txt2img_basic")


# ── Schema 测试 ──


class TestBlueprintSchema:
    """Schema 本身定义的正确性"""

    def test_schema_version(self):
        assert BLUEPRINT_SCHEMA_VERSION == "1.0.0"

    def test_schema_has_required_fields(self):
        required = BLUEPRINT_JSON_SCHEMA.get("required", [])
        props = BLUEPRINT_JSON_SCHEMA.get("properties", {})
        for f in required:
            assert f in props, f"Required field '{f}' missing from properties"

    def test_schema_completeness(self):
        issues = validate_schema_completeness()
        assert len(issues) == 0, f"Schema issues: {issues}"


# ── 加载测试 ──


class TestBlueprintLoader:
    """蓝图加载器测试"""

    def test_load_existing(self, loader):
        bp = loader.load("flux_txt2img_basic")
        assert bp["id"] == "flux_txt2img_basic"
        assert bp["schema_version"] == "1.0.0"

    def test_load_nonexistent(self, loader):
        with pytest.raises(BlueprintNotFoundError):
            loader.load("nonexistent_blueprint")

    def test_load_all(self, loader):
        all_bp = loader.load_all()
        assert len(all_bp) >= 1
        ids = [b["id"] for b in all_bp if isinstance(b, dict) and "id" in b]
        assert "flux_txt2img_basic" in ids

    def test_list_ids(self, loader):
        ids = loader.list_ids()
        assert "flux_txt2img_basic" in ids

    def test_reload(self, loader):
        loader.load("flux_txt2img_basic")
        assert "flux_txt2img_basic" in loader._cache
        loader.reload()
        assert "flux_txt2img_basic" not in loader._cache


# ── 校验测试 ──


class TestBlueprintValidator:
    """蓝图校验器测试"""

    def test_valid_blueprint(self, validator, flux_blueprint):
        issues = validator.validate(flux_blueprint)
        assert len(issues) == 0, f"Validation issues: {issues}"
        assert validator.is_valid(flux_blueprint)

    def test_missing_required_field(self, validator):
        bad = {"id": "test"}
        issues = validator.validate(bad)
        assert len(issues) > 0
        assert any("schema_version" in i for i in issues)

    def test_slot_references_existing_nodes(self, validator, flux_blueprint):
        slots = flux_blueprint.get("slots", {})
        nodes = flux_blueprint.get("graph_template", {}).get("nodes", [])
        issues = validator.validate_slots(slots, nodes)
        assert len(issues) == 0, f"Slot issues: {issues}"


# ── Normalizer 测试 ──


class TestWorkflowNormalizer:
    """Workflow 归一化器测试"""

    def test_api_format_detection(self):
        data = {"1": {"class_type": "KSampler", "inputs": {"seed": 42}}}
        wf = WorkflowNormalizer.normalize(data)
        assert wf.source_format == "api"
        assert "1" in wf.prompt

    def test_ui_format_detection(self):
        data = {"1": {"class_type": "KSampler", "inputs": {}, "widgets_values": [1, 2, 3]}}
        wf = WorkflowNormalizer.normalize(data)
        assert wf.source_format == "ui"

    def test_history_format(self):
        # 顶层有 outputs 键，判定为 history
        data = {"outputs": {"pid123": {}}, "prompt": {"1": {"class_type": "KSampler", "inputs": {}}}}
        wf = WorkflowNormalizer.normalize(data)
        assert wf.source_format == "history"

    def test_empty_workflow(self):
        wf = WorkflowNormalizer.normalize({})
        assert wf.prompt == {}
        assert wf.source_format == "api"


# ── Packer 测试 ──


class TestBlueprintPacker:
    """蓝图打包器测试"""

    def test_pack_from_workflow(self, packer):
        workflow = {
            "1": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0}},
            "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}},
        }
        bp = packer.pack(workflow, "test_pack_001", name="Test Pack", tags=["test"])
        assert bp["id"] == "test_pack_001"
        assert bp["schema_version"] == "1.0.0"
        assert len(bp["graph_template"]["nodes"]) == 2
        assert len(bp["graph_template"]["edges"]) == 1

    def test_pack_with_empty_workflow(self, packer):
        bp = packer.pack({}, "empty_test")
        assert bp["id"] == "empty_test"
        # 空 workflow 生成空骨架
        assert bp["graph_template"]["nodes"] == []
        assert bp["metadata"]["total_nodes"] == 0

    def test_pack_and_load_roundtrip(self, packer, tmp_path):
        workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat"}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 42}},
        }
        bp = packer.pack(workflow, "roundtrip_test")
        saved_path = packer.save(bp, str(tmp_path))
        assert saved_path.exists()
        with open(saved_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["id"] == "roundtrip_test"


# ── Registry 测试 ──


class TestBlueprintRegistry:
    """蓝图注册表测试"""

    def test_get_existing(self, registry):
        bp = registry.get("flux_txt2img_basic")
        assert bp is not None
        assert bp["id"] == "flux_txt2img_basic"

    def test_get_nonexistent(self, registry):
        bp = registry.get("nonexistent")
        assert bp is None

    def test_list_all(self, registry):
        all_bp = registry.list_all()
        assert len(all_bp) >= 1


# ── 综合语义测试 ──


class TestBlueprintSemantics:
    """蓝图语义正确性测试（非 exact match）"""

    def test_blueprint_has_meaningful_structure(self, flux_blueprint):
        """蓝图应该包含有意义的图结构"""
        gt = flux_blueprint.get("graph_template", {})
        nodes = gt.get("nodes", [])
        edges = gt.get("edges", [])
        assert len(nodes) >= 3, "Blueprint should have at least 3 nodes"
        assert len(edges) >= 1, "Blueprint should have at least 1 edge"

    def test_blueprint_slots_match_nodes(self, flux_blueprint):
        """Slot 引用的节点必须存在于 graph_template 中"""
        slots = flux_blueprint.get("slots", {})
        node_ids = {n["id"] for n in flux_blueprint.get("graph_template", {}).get("nodes", [])}
        for slot_name, slot in slots.items():
            nid = slot.get("node_id")
            assert nid in node_ids, f"Slot '{slot_name}' references missing node '{nid}'"

    def test_blueprint_input_fields_form_valid_contract(self, flux_blueprint):
        """输入契约的字段名和类型应该合理"""
        fields = flux_blueprint.get("input_contract", {}).get("fields", [])
        assert len(fields) > 0
        valid_types = {"text", "image", "mask", "latent", "video", "audio", "number", "boolean", "choice"}
        for f in fields:
            assert f["type"] in valid_types, f"Invalid field type: {f['type']}"

    def test_blueprint_task_type_is_known(self, flux_blueprint):
        """task_type 应该是已知的类型"""
        known_types = {"txt2img", "img2img", "t2v", "i2v", "upscale", "edit", "controlnet", "audio", "mix", "general"}
        task_type = flux_blueprint.get("capability", {}).get("task_type", "")
        assert task_type in known_types, f"Unknown task type: {task_type}"

    def test_quality_modes_have_expected_keys(self, flux_blueprint):
        """quality_modes 应该包含 draft/standard/quality，且每个都有 steps"""
        modes = flux_blueprint.get("quality_modes", {})
        assert "draft" in modes
        assert "standard" in modes
        assert "quality" in modes
        for mode_name, mode in modes.items():
            assert "steps" in mode, f"Mode '{mode_name}' missing steps"


# ── 生产级完整性 ──


class TestProductionBlueprintQuantity:
    """生产级蓝图数量和完整性"""

    def test_minimum_production_blueprints(self, loader):
        """至少要有 10 个生产级蓝图"""
        all_bp = loader.load_all()
        assert len(all_bp) >= 10, f"只有 {len(all_bp)} 个蓝图，需要至少 10 个"

    def test_all_blueprints_pass_validation(self, loader, validator):
        """所有蓝图必须通过 schema 校验"""
        all_bp = loader.load_all()
        for bp in all_bp:
            issues = validator.validate(bp)
            assert len(issues) == 0, f"Blueprint '{bp.get('id','?')}' 校验失败: {issues}"
