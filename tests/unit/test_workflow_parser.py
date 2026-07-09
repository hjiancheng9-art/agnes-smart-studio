"""
ComfyFlow Compiler — Workflow 格式解析器单元测试

覆盖：三种格式检测、互转、校验
优先级：高（格式错误全链崩）
目标覆盖率：90%+
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import json
from comfyflow_compiler.workflow_parser import (
    detect_format, WorkflowFormat, convert_to_api, convert_to_save_v1,
    to_api_prompt, to_save_v1, validate_workflow,
)


class TestDetectFormat:
    """自动格式检测"""

    def test_detect_api_prompt(self, sample_sdxl_workflow):
        fmt = detect_format(sample_sdxl_workflow)
        assert fmt == WorkflowFormat.API_PROMPT

    def test_detect_save_v1(self, sample_save_v1):
        fmt = detect_format(sample_save_v1)
        assert fmt == WorkflowFormat.SAVE_V1

    def test_detect_unknown(self):
        assert detect_format([]) == WorkflowFormat.UNKNOWN
        assert detect_format("") == WorkflowFormat.UNKNOWN
        assert detect_format({}) == WorkflowFormat.UNKNOWN

    def test_detect_mixed_format(self):
        """带 version 但没有 state/nodes 的不能算 Save V1"""
        data = {"version": 1, "nodes": []}
        # 缺少 state
        fmt = detect_format(data)
        assert fmt != WorkflowFormat.SAVE_V1


class TestConvertApiPrompt:
    """API Prompt → Save V1 转换"""

    def test_basic_conversion(self, sample_sdxl_workflow):
        save = convert_to_save_v1(sample_sdxl_workflow)
        assert save is not None
        assert save["version"] == 1
        assert len(save["nodes"]) >= 7, f"应有 >=7 节点: {len(save['nodes'])}"

    def test_links_preserved(self):
        """连接关系应被保留"""
        workflow = {
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat", "clip": ["4", 1]}},
        }
        save = convert_to_save_v1(workflow)
        assert save is not None
        assert len(save["links"]) >= 1, "应保留连接"
        
        # 检查 link 的 origin/target
        link = save["links"][0]
        assert link["origin_id"] == 4
        assert link["target_id"] == 6

    def test_widgets_preserved(self):
        """非连接参数应放入 widgets_values"""
        workflow = {
            "5": {"class_type": "KSampler", "inputs": {
                "seed": 0, "steps": 20, "cfg": 7.0,
                "model": ["1", 0], "positive": ["2", "conditioning"],
            }}
        }
        save = convert_to_save_v1(workflow)
        node = save["nodes"][0]
        assert node["type"] == "KSampler"
        # steps 应出现在 widgets_values 中
        assert 20 in node.get("widgets_values", [])
        assert 7.0 in node.get("widgets_values", [])


class TestConvertSaveV1:
    """Save V1 → API Prompt 转换"""

    def test_conversion(self, sample_save_v1):
        api = convert_to_api(sample_save_v1)
        assert api is not None
        # 应保留节点 ID
        assert "4" in api
        assert "6" in api
        assert api["4"]["class_type"] == "CheckpointLoaderSimple"

    def test_widgets_to_inputs(self):
        """widgets_values 应映射到 inputs"""
        save = {
            "version": 1, "state": {}, "nodes": [
                {"id": 4, "type": "CheckpointLoaderSimple", "pos": [0,0], "size": [300,200],
                 "flags": {}, "order": 0, "mode": 0,
                 "inputs": [], "outputs": [],
                 "properties": {},
                 "widgets_values": ["sd_xl.safetensors"]},
                {"id": 6, "type": "CLIPTextEncode", "pos": [0,0], "size": [300,200],
                 "flags": {}, "order": 1, "mode": 0,
                 "inputs": [{"name": "clip", "type": "CLIP", "link": 1, "slot_index": 0}],
                 "outputs": [],
                 "properties": {},
                 "widgets_values": ["a cat"]},
            ],
            "links": [{"id": 1, "origin_id": 4, "origin_slot": 1, "target_id": 6, "target_slot": 0, "type": "CLIP"}],
            "groups": [], "reroutes": [], "extra": {}, "models": [],
        }
        api = convert_to_api(save)
        assert api["4"]["inputs"]["ckpt_name"] == "sd_xl.safetensors"


class TestValidateWorkflow:
    """Workflow 校验"""

    def test_valid_workflow(self, sample_sdxl_workflow):
        valid, errors = validate_workflow(sample_sdxl_workflow)
        assert valid, f"应通过校验: {errors}"
        assert len(errors) == 0

    def test_invalid_empty(self):
        valid, errors = validate_workflow({})
        assert not valid

    def test_invalid_no_class_type(self):
        valid, errors = validate_workflow({"1": {"inputs": {}}})
        assert not valid

    def test_invalid_missing_ref(self):
        """引用不存在的节点"""
        wf = {
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat", "clip": ["999", 1]}},
        }
        valid, errors = validate_workflow(wf)
        assert not valid
        assert any("999" in e for e in errors)

    def test_no_output_node(self):
        """缺少输出节点"""
        wf = {"4": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat", "clip": None}}}
        valid, errors = validate_workflow(wf)
        assert not valid
        assert any("输出" in e or "SaveImage" in e for e in errors)

    def test_vhs_video_is_valid_output(self):
        """VHS_VideoCombine 应被视为输出节点"""
        wf = {"10": {"class_type": "VHS_VideoCombine", "inputs": {"images": None}}}
        valid, errors = validate_workflow(wf)
        # 只要不报"缺少输出"就行
        output_errors = [e for e in errors if "输出" in e or "SaveImage" in e]
        assert len(output_errors) == 0, f"VHS 应被识别为输出: {errors}"
