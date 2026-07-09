"""Blueprint JSON Schema — 生产级蓝图格式定义

从真实 ComfyUI workflow 抽象而来的蓝图 JSON Schema。
"""

from __future__ import annotations

BLUEPRINT_SCHEMA_VERSION = "1.0.0"

BLUEPRINT_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://comfyflow.local/schemas/blueprint-1.0.0.json",
    "title": "ComfyFlow Production Blueprint",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "id",
        "name",
        "version",
        "status",
        "source",
        "capability",
        "requirements",
        "input_contract",
        "output_contract",
        "graph_template",
        "slots",
        "quality_modes",
        "validation",
        "metadata",
    ],
    "properties": {
        "schema_version": {
            "type": "string",
            "description": "Blueprint schema version. Used for migration and compatibility.",
        },
        "id": {
            "type": "string",
            "description": "Unique identifier for the blueprint (e.g. 'flux_txt2img_v1').",
        },
        "name": {
            "type": "string",
            "description": "Human-readable display name (e.g. 'Flux Text-to-Image').",
        },
        "version": {
            "type": "string",
            "description": "Semantic version of this blueprint (e.g. '1.2.0').",
        },
        "status": {
            "type": "string",
            "enum": ["stable", "beta", "deprecated"],
            "description": "Maturity level of the blueprint.",
        },
        "source": {
            "type": "object",
            "required": ["origin", "workflow_id", "mined_at"],
            "properties": {
                "origin": {
                    "type": "string",
                    "enum": ["mined", "handcrafted", "community", "generated"],
                    "description": "How this blueprint was created.",
                },
                "workflow_id": {
                    "type": "string",
                    "description": "Original ComfyUI workflow ID / filename.",
                },
                "mined_at": {
                    "type": "string",
                    "description": "ISO 8601 timestamp of mining/creation.",
                },
                "author": {
                    "type": "string",
                    "description": "Creator or maintainer.",
                },
            },
        },
        "capability": {
            "type": "object",
            "required": ["task_type", "description", "tags"],
            "properties": {
                "task_type": {
                    "type": "string",
                    "description": "Primary task (txt2img, img2img, i2v, t2v, upscale, edit, controlnet, audio, mix).",
                },
                "description": {
                    "type": "string",
                    "description": "What this blueprint does in one sentence.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords for matching (e.g. ['flux', 'realistic', 'portrait']).",
                },
                "styles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Supported visual styles (e.g. ['cinematic', 'anime', 'photorealistic']).",
                },
                "models": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "type"],
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "required": {"type": "boolean"},
                            "source": {"type": "string"},
                        },
                    },
                    "description": "Models required/used by this blueprint.",
                },
                "performance_hint": {
                    "type": "object",
                    "properties": {
                        "gpu_vram_gb": {"type": "number"},
                        "avg_gen_time_s": {"type": "number"},
                        "batch_size": {"type": "integer"},
                    },
                },
            },
        },
        "requirements": {
            "type": "object",
            "required": ["min_nodes", "required_nodes", "recommended_nodes"],
            "properties": {
                "min_nodes": {
                    "type": "integer",
                    "description": "Minimum number of ComfyUI nodes needed.",
                },
                "required_nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["class_type", "reason"],
                        "properties": {
                            "class_type": {"type": "string"},
                            "reason": {"type": "string"},
                            "fallback": {"type": "string"},
                        },
                    },
                    "description": "Nodes that must exist for this blueprint to work.",
                },
                "recommended_nodes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional but beneficial extra nodes.",
                },
                "custom_nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "install_hint"],
                        "properties": {
                            "name": {"type": "string"},
                            "install_hint": {"type": "string"},
                        },
                    },
                    "description": "Third-party custom node requirements.",
                },
            },
        },
        "input_contract": {
            "type": "object",
            "required": ["fields"],
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "type", "description"],
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["text", "image", "mask", "latent", "video", "audio", "number", "boolean", "choice"],
                            },
                            "description": {"type": "string"},
                            "required": {"type": "boolean"},
                            "default": {},
                            "choices": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "example": {"type": "string"},
                        },
                    },
                },
                "prompt_template": {
                    "type": "string",
                    "description": "Jinja2-like template: 'A {{style}} photo of {{subject}}'",
                },
            },
        },
        "output_contract": {
            "type": "object",
            "required": ["fields"],
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "type", "description"],
                        "properties": {
                            "name": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["image", "video", "audio", "latent", "mask", "json"],
                            },
                            "description": {"type": "string"},
                            "preview": {"type": "boolean"},
                        },
                    },
                },
            },
        },
        "graph_template": {
            "type": "object",
            "required": ["nodes", "edges"],
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "class_type"],
                        "properties": {
                            "id": {"type": "string"},
                            "class_type": {"type": "string"},
                            "title": {"type": "string"},
                            "is_output": {"type": "boolean"},
                            "is_input": {"type": "boolean"},
                        },
                    },
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["from_node", "from_slot", "to_node", "to_slot"],
                        "properties": {
                            "from_node": {"type": "string"},
                            "from_slot": {"type": "integer"},
                            "to_node": {"type": "string"},
                            "to_slot": {"type": "integer"},
                            "type": {"type": "string"},
                        },
                    },
                },
                "entry_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Node IDs that accept external input.",
                },
                "exit_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Node IDs that produce final output.",
                },
            },
        },
        "slots": {
            "type": "object",
            "patternProperties": {
                "^.*$": {
                    "type": "object",
                    "required": ["node_id", "input_name", "type", "description"],
                    "properties": {
                        "node_id": {"type": "string"},
                        "input_name": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": ["text", "image", "number", "boolean", "choice", "latent", "seed", "model", "vae", "clip", "lora"],
                        },
                        "description": {"type": "string"},
                        "default": {},
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                        "choices": {"type": "array", "items": {"type": "string"}},
                        "required": {"type": "boolean"},
                        "expose_to_ui": {"type": "boolean"},
                        "ui_label": {"type": "string"},
                        "ui_group": {"type": "string"},
                    },
                },
            },
            "additionalProperties": False,
        },
        "quality_modes": {
            "type": "object",
            "properties": {
                "draft": {
                    "type": "object",
                    "properties": {
                        "steps": {"type": "integer"},
                        "cfg": {"type": "number"},
                        "sampler": {"type": "string"},
                        "scheduler": {"type": "string"},
                        "resolution": {"type": "string"},
                    },
                },
                "standard": {
                    "type": "object",
                    "properties": {
                        "steps": {"type": "integer"},
                        "cfg": {"type": "number"},
                        "sampler": {"type": "string"},
                        "scheduler": {"type": "string"},
                        "resolution": {"type": "string"},
                    },
                },
                "quality": {
                    "type": "object",
                    "properties": {
                        "steps": {"type": "integer"},
                        "cfg": {"type": "number"},
                        "sampler": {"type": "string"},
                        "scheduler": {"type": "string"},
                        "resolution": {"type": "string"},
                    },
                },
            },
        },
        "validation": {
            "type": "object",
            "properties": {
                "required_vram_gb": {"type": "number"},
                "tested_models": {"type": "array", "items": {"type": "string"}},
                "known_issues": {"type": "array", "items": {"type": "string"}},
                "golden_texts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "expected_note_content": {"type": "string"},
                        },
                    },
                },
            },
        },
        "metadata": {
            "type": "object",
            "properties": {
                "created_at": {"type": "string"},
                "updated_at": {"type": "string"},
                "changelog": {"type": "array", "items": {"type": "string"}},
                "total_nodes": {"type": "integer"},
                "total_edges": {"type": "integer"},
            },
        },
    },
}


def validate_schema_completeness() -> list[str]:
    """Check that the schema itself is well-formed."""
    issues: list[str] = []
    required_fields = BLUEPRINT_JSON_SCHEMA.get("required", [])
    props = BLUEPRINT_JSON_SCHEMA.get("properties", {})
    for f in required_fields:
        if f not in props:
            issues.append(f"Required field '{f}' has no properties definition")
    return issues
