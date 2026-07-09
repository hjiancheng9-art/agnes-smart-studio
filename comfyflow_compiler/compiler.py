"""ComfyFlow Compiler — 总入口

将自然语言需求编译为可执行的 ComfyUI Workflow JSON。

使用示例：
    from comfyflow_compiler.compiler import ComfyFlowCompiler

    compiler = ComfyFlowCompiler()
    result = compiler.compile("生成一张电影感赛博朋克猫，霓虹雨夜，9:16")
    if result.success:
        print(result.workflow_json)
        print(result.user_summary)
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from .models import (
    TaskSpec, HardwareProfile, RuntimeBudget, EnvironmentProfile,
    Blueprint, QualityReport, CompileResult,
)
from .intent_parser import parse_intent
from .hardware_profiler import detect_gpu, compute_runtime_budget
from .environment_scanner import scan_comfyui_environment, detect_comfyui_paths
from .blueprint_registry import BlueprintRegistry
from .graph_composer import compose_workflow
from .quality_gate import evaluate_quality
from .workflow_validator import validate_workflow, validate_for_api
from .launcher import ComfyUILauncher, ComfyUIStatus
from .user_facing import build_user_result, UserFacingResult, translate_error
from .workflow_enricher import WorkflowEnricher, WorkflowAnalyzer


class ComfyFlowCompiler:
    """
    ComfyFlow 编译器 — 主控入口。

    把自然语言需求 → 可执行的 ComfyUI workflow JSON。
    """

    def __init__(self, comfyui_path: Optional[str] = None):
        self.registry = BlueprintRegistry()
        self.hardware: Optional[HardwareProfile] = None
        self.budget: Optional[RuntimeBudget] = None
        self.env: Optional[EnvironmentProfile] = None
        self._comfyui_port: Optional[int] = None

        # 自动检测硬件
        self._init_hardware()

        # 自动检测 ComfyUI 环境
        self._init_environment(comfyui_path)

    def _init_hardware(self):
        """初始化硬件检测"""
        self.hardware = detect_gpu()
        self.budget = compute_runtime_budget(self.hardware)

    def _init_environment(self, comfyui_path: Optional[str] = None):
        """初始化环境扫描"""
        if comfyui_path:
            self.env = scan_comfyui_environment(comfyui_path)
        else:
            # 自动查找
            paths = detect_comfyui_paths()
            if paths:
                self.env = scan_comfyui_environment(paths[0])
            else:
                self.env = EnvironmentProfile()
                self.env.warnings.append("未自动检测到 ComfyUI 安装路径")

    def compile(self, user_input: str) -> CompileResult:
        """
        编译单次需求。

        Args:
            user_input: 用户自然语言描述

        Returns:
            CompileResult: 编译结果
        """
        result = CompileResult()

        # 1. 解析意图
        task = parse_intent(user_input)

        # 1.5 Video 意图分流：t2v(纯文本→视频) vs i2v(图片→视频)
        if task.task_type == "video":
            i2v_keywords = ["this picture", "this image", "this photo", "turn this",
                            "this video", "uploaded image", "input image", "make this"]
            is_i2v = any(kw in user_input.lower() for kw in i2v_keywords)

            if is_i2v:
                # i2v — 需要用户提供输入图片
                task.task_type = "i2v"
            else:
                # t2v — 纯文本到视频
                task.task_type = "t2v"

        # 2. 匹配场景配方
        recipes = self.registry.match_recipe(task.task_type, task.style, task.subject)
        recipe = recipes[0] if recipes else None

        # 3. 在硬件约束内选择最佳蓝图
        bp = self.registry.select_best_blueprint(
            task_type=task.task_type,
            recipe=recipe,
            budget_score=self.budget.score if self.budget else 0,
            vram_gb=self.hardware.vram_gb if self.hardware else 0,
            has_sdxl=self.env.has_sdxl if self.env else False,
            has_sd15=self.env.has_sd15 if self.env else False,
            has_flux=self.env.has_flux if self.env else False,
            has_ltx=self.env.has_ltx if self.env else False,
            has_wan=self.env.has_wan if self.env else False,
        )

        if not bp:
            # 尝试降级到最简方案
            bp = self.registry.get_blueprint("txt2img_minimal")
            if not bp:
                result.error = "没有可用的工作流蓝图，请检查 ComfyUI 安装"
                return result

        result.blueprint_used = bp.display_name

        # 4. 组装工作流
        try:
            workflow = compose_workflow(task, bp, self.env, self.budget)
            
            # 4.5 工作流增强
            if self.budget and self.hardware and self.env:
                enricher = WorkflowEnricher(self.budget, self.env)
                enriched = enricher.enrich(
                    workflow, task,
                    quality_mode=task.quality_mode,
                )
                if enriched:
                    workflow = enriched
                    # 增强后再次后处理（修复引用格式 + 模型名）
                    from .graph_composer import _postprocess_for_comfyui
                    workflow = _postprocess_for_comfyui(workflow, self.env)
        except Exception as e:
            result.error = f"工作流组装失败: {e}"
            return result

        # 5. 质量门
        quality = evaluate_quality(workflow, task, bp, self.env, self.budget)
        result.quality_report = quality

        # 6. 校验
        is_valid, errors = validate_workflow(workflow)
        if not is_valid:
            result.error = f"工作流校验失败: {'; '.join(errors[:3])}"
            return result

        # 7. 转换为 API 格式
        api_workflow = validate_for_api(workflow)
        result.workflow_json = api_workflow

        # 8. 生成用户摘要
        result.success = True
        result.hardware_used = self.hardware.gpu_name or "未知"
        result.estimated_vram = f"{self.budget.vram_gb}GB" if self.budget else "未知"
        result.user_summary = self._generate_summary(task, bp, quality)

        return result

    def compile_with_fallback(self, user_input: str) -> CompileResult:
        """
        带自动降级的编译。

        如果首选方案失败 (环境/模型不满足)，自动降级到次优方案。
        如果是缺少蓝图（如 t2v），不降级，直接返回结构化的缺失错误。
        """
        result = self.compile(user_input)
        if result.success:
            return result

        # 尝试降级
        task = parse_intent(user_input)
        recipes = self.registry.match_recipe(task.task_type, task.style, task.subject)
        recipe = recipes[0] if recipes else None

        if recipe:
            fallback_chain = self.registry.get_fallback_chain(
                recipe, self.budget.score if self.budget else 0,
                self.hardware.vram_gb if self.hardware else 0,
                self.env.has_sdxl if self.env else False,
                self.env.has_sd15 if self.env else False,
            )
            for bp in fallback_chain:
                try:
                    workflow = compose_workflow(task, bp, self.env, self.budget)
                    quality = evaluate_quality(workflow, task, bp, self.env, self.budget)
                    is_valid, _ = validate_workflow(workflow)
                    if is_valid:
                        api = validate_for_api(workflow)
                        result.success = True
                        result.workflow_json = api
                        result.blueprint_used = bp.display_name
                        result.quality_report = quality
                        result.fallback_chain_used.append(bp.name)
                        result.user_summary = (
                            f"由于环境限制，已自动降级为 {bp.display_name}。"
                            f"{quality.user_friendly_message}"
                        )
                        return result
                except Exception:
                    continue

        return result

    def _generate_summary(self, task: TaskSpec, bp: Blueprint,
                          quality: QualityReport) -> str:
        """生成面向小白的友好摘要"""
        quality_pct = round(quality.overall_score * 100)
        hw_name = self.hardware.gpu_name or "当前电脑"

        lines = [
            f"🎯 已理解你的需求：{task.subject}",
            f"💻 检测到 {hw_name}（{self.hardware.vram_gb}GB 显存）",
            f"📋 选用方案：{bp.display_name}",
            f"⭐ 工作流质量评分：{quality_pct}分",
        ]

        if quality_pct >= 80:
            lines.append("✅ 可以直接拖入 ComfyUI 运行！")
        elif quality_pct >= 60:
            lines.append("👍 可以运行，建议检查参数是否符合预期")
        else:
            lines.append("ℹ️ 基础可用，如需更高质量请升级硬件或安装更多模型")

        return "\n".join(lines)

    def status(self) -> dict:
        """查看当前系统状态"""
        return {
            "hardware": {
                "gpu": self.hardware.gpu_name if self.hardware else "未检测",
                "vram_gb": self.hardware.vram_gb if self.hardware else 0,
                "budget_tier": self.budget.tier if self.budget else "unknown",
                "budget_score": self.budget.score if self.budget else 0,
            },
            "environment": {
                "comfyui": self.env.comfyui_path if self.env else "未检测",
                "checkpoints": len(self.env.checkpoints) if self.env else 0,
                "custom_nodes": len(self.env.custom_nodes) if self.env else 0,
                "has_sdxl": self.env.has_sdxl if self.env else False,
                "has_sd15": self.env.has_sd15 if self.env else False,
                "has_flux": self.env.has_flux if self.env else False,
                "has_ltx": self.env.has_ltx if self.env else False,
                "has_wan": self.env.has_wan if self.env else False,
            },
            "registry": {
                "blueprints": len(self.registry.blueprints),
                "recipes": len(self.registry.recipes),
            },
        }

    # =========================================================================
    # ComfyUI 启动器接口
    # =========================================================================

    def launch_comfyui(self, port: int = 8188, quiet: bool = True,
                       wait: bool = True, timeout: int = 60,
                       extra_args: Optional[list] = None) -> ComfyUIStatus:
        """一键启动 ComfyUI"""
        comfyui_path = self.env.comfyui_path if (self.env and self.env.comfyui_path) else None
        launcher = ComfyUILauncher(comfyui_path)
        result = launcher.launch(
            port=port, quiet=quiet,
            wait_until_ready=wait, timeout=timeout,
            extra_args=extra_args,
        )
        if result.running and result.port:
            self._comfyui_port = result.port
        return result

    def stop_comfyui(self) -> bool:
        """停止 ComfyUI"""
        launcher = ComfyUILauncher(
            self.env.comfyui_path if (self.env and self.env.comfyui_path) else None
        )
        stopped = launcher.stop()
        if stopped:
            self._comfyui_port = None
        return stopped

    def is_comfyui_running(self, port: int = 8188) -> bool:
        """检查 ComfyUI 是否在运行"""
        return ComfyUILauncher._port_in_use(port)

    def send_to_comfyui(self, workflow_json: dict, port: int = 8188) -> dict:
        """发送工作流到 ComfyUI 执行"""
        launcher = ComfyUILauncher()
        return launcher.send_workflow(workflow_json)

    # =========================================================================
    # 一键编译 + 执行
    # =========================================================================

    def compile_and_run(self, user_input: str, port: int = 8188,
                        wait: bool = True, timeout: int = 300,
                        on_progress: Optional[Callable] = None) -> dict:
        """
        一键完成：编译 → 提交 → 监听 → 返回结果。

        Args:
            user_input: 用户需求
            port: ComfyUI 端口
            wait: 是否等待执行完成
            timeout: 最大等待秒数
            on_progress: 进度回调

        Returns:
            dict: {
                "success": bool,
                "compile": CompileResult,
                "execution": ExecutionProgress,
                "workflow_json": dict,
            }
        """
        from typing import Callable

        # 1. 编译
        result = self.compile_with_fallback(user_input)
        if not result.success or not result.workflow_json:
            return {
                "success": False,
                "compile": result,
                "execution": None,
                "workflow_json": None,
                "error": result.error or "编译失败",
            }

        # 2. 发送到 ComfyUI
        client = ComfyAPIClient(f"http://127.0.0.1:{port}")
        api_workflow = result.workflow_json["prompt"]
        prompt_id = client.queue_prompt(api_workflow)

        if not wait:
            return {
                "success": True,
                "compile": result,
                "prompt_id": prompt_id,
                "workflow_json": result.workflow_json,
            }

        # 3. 等待执行完成
        progress = client.wait_for_completion(
            prompt_id, on_progress=on_progress, timeout=timeout
        )

        return {
            "success": progress.status == "done",
            "compile": result,
            "execution": progress,
            "prompt_id": prompt_id,
            "workflow_json": result.workflow_json,
            "output_images": progress.output_images,
        }
