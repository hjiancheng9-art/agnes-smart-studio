"""Blueprint Packer — workflow → blueprint JSON"""
from __future__ import annotations
import json, datetime
from pathlib import Path
from typing import Any, Optional

from .types import NormalizedWorkflow
from .normalizer import WorkflowNormalizer
from .schema import BLUEPRINT_SCHEMA_VERSION


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class BlueprintPacker:
    """将归一化的 workflow 打包为蓝图 JSON"""

    def pack(self, workflow: NormalizedWorkflow | dict, blueprint_id: str,
             name: str = "", tags: list[str] | None = None) -> dict:
        """将 workflow 打包为 ProductionBlueprint 字典"""
        if not isinstance(workflow, NormalizedWorkflow):
            workflow = WorkflowNormalizer.normalize(workflow)
        prompt = workflow.prompt or {}
        return self._build_blueprint_json(blueprint_id, name or blueprint_id, prompt, tags or [])

    def pack_from_file(self, workflow_path: str, blueprint_id: str,
                       name: str = "", tags: list[str] | None = None) -> dict:
        with open(workflow_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.pack(data, blueprint_id, name, tags)

    def save(self, blueprint: dict, output_dir: str | Path) -> Path:
        output_path = Path(output_dir) / f"{blueprint['id']}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(blueprint, f, indent=2, ensure_ascii=False)
        return output_path

    def _build_blueprint_json(self, bp_id: str, name: str,
                              prompt: dict, tags: list[str]) -> dict:
        nodes = self._extract_nodes(prompt)
        edges = self._extract_edges(prompt)
        task_type = self._infer_category(prompt)
        return {
            "schema_version": BLUEPRINT_SCHEMA_VERSION,
            "id": bp_id, "name": name, "version": "1.0.0", "status": "beta",
            "source": {"origin": "generated", "workflow_id": bp_id, "mined_at": _now_iso()},
            "capability": {"task_type": task_type, "description": f"{name}", "tags": tags or [task_type],
                           "styles": [], "models": []},
            "requirements": {"min_nodes": len(nodes), "required_nodes": [], "recommended_nodes": [], "custom_nodes": []},
            "input_contract": {"fields": self._build_input_contract(prompt)},
            "output_contract": {"fields": self._build_output_contract(prompt)},
            "graph_template": {
                "nodes": nodes, "edges": edges,
                "entry_points": [n["id"] for n in nodes if n.get("is_input")],
                "exit_points": [n["id"] for n in nodes if n.get("is_output")],
            },
            "slots": self._build_slots(prompt, nodes),
            "quality_modes": {
                "draft": {"steps": 20, "cfg": 3.5, "sampler": "euler", "scheduler": "normal", "resolution": "512x512"},
                "standard": {"steps": 30, "cfg": 7.0, "sampler": "euler", "scheduler": "normal", "resolution": "1024x1024"},
                "quality": {"steps": 50, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras", "resolution": "1024x1024"},
            },
            "validation": {"known_issues": [], "tested_models": []},
            "metadata": {"created_at": _now_iso(), "updated_at": _now_iso(),
                         "total_nodes": len(nodes), "total_edges": len(edges)},
        }

    def _extract_nodes(self, prompt: dict) -> list[dict]:
        nodes = []
        for node_id, node_data in prompt.items():
            if not isinstance(node_data, dict) or "class_type" not in node_data:
                continue
            ct = node_data["class_type"]
            nodes.append({
                "id": node_id, "class_type": ct,
                "title": node_data.get("_meta", {}).get("title", ct),
                "is_output": ct in ("SaveImage", "VHS_VideoCombine"),
            })
        return nodes

    def _extract_edges(self, prompt: dict) -> list[dict]:
        edges = []
        for node_id, node_data in prompt.items():
            if not isinstance(node_data, dict):
                continue
            for input_name, input_val in node_data.get("inputs", {}).items():
                if isinstance(input_val, list) and len(input_val) == 2:
                    edges.append({
                        "from_node": str(input_val[0]), "from_slot": int(input_val[1]),
                        "to_node": node_id, "to_slot": 0,
                    })
        return edges

    def _infer_category(self, prompt: dict) -> str:
        s = str(prompt)
        if "VHS_VideoCombine" in s: return "t2v"
        if "SaveImage" in s: return "txt2img"
        return "general"

    def _build_input_contract(self, prompt: dict) -> list[dict]:
        for nd in prompt.values():
            if isinstance(nd, dict) and "CLIPTextEncode" in nd.get("class_type", ""):
                return [
                    {"name": "positive_prompt", "type": "text", "description": "正向提示词", "required": True},
                    {"name": "negative_prompt", "type": "text", "description": "负向提示词", "required": False},
                ]
        return [{"name": "prompt", "type": "text", "description": "提示词", "required": True}]

    def _build_output_contract(self, prompt: dict) -> list[dict]:
        return [{"name": "output", "type": "image", "description": "生成输出"}]

    def _build_slots(self, prompt: dict, nodes: list[dict]) -> dict:
        slots = {}
        for node in nodes:
            nid, ct = node["id"], node["class_type"]
            nd = prompt.get(nid, {})
            inputs = nd.get("inputs", {}) if isinstance(nd, dict) else {}
            for iname in list(inputs.keys())[:5]:
                slot_name = f"{ct}.{iname}"
                stype = "text" if "text" in iname.lower() else "seed" if "seed" in iname.lower() else "number" if iname in ("steps","cfg") else "string"
                slots[slot_name] = {
                    "node_id": nid, "input_name": iname, "type": stype,
                    "description": f"{ct} → {iname}",
                    "expose_to_ui": stype in ("text", "seed", "number"),
                }
        return slots
