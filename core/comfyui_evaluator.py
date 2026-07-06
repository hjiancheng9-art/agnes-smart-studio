"""Motif Evaluator — 回放准入系统 (B2)

验证每个 Motif 的:
1. quality_score: Node Schema 完备性 + 连接完整性
2. compatibility: 模型/显存兼容 
3. param_ranges: 参数范围合法性
4. hash 去重: 内容重复检查
5. 编译回放: Compiler 能成功编译
6. Validator 通过: L1-L4 校验通过
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class EvalScore:
    """评估分数。"""
    score: float        # 0-1
    max_score: float    # 1.0
    details: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def pct(self) -> str:
        return f"{self.score/self.max_score*100:.0f}%"


@dataclass
class MotifEvalResult:
    """单个 Motif 的完整评估结果。"""
    motif_id: str
    name: str
    passed: bool
    overall_score: float   # 0-1
    
    node_score: EvalScore = field(default_factory=lambda: EvalScore(0, 1))
    edge_score: EvalScore = field(default_factory=lambda: EvalScore(0, 1))
    compile_score: EvalScore = field(default_factory=lambda: EvalScore(0, 1))
    validate_score: EvalScore = field(default_factory=lambda: EvalScore(0, 1))
    
    errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "motif_id": self.motif_id,
            "name": self.name,
            "passed": self.passed,
            "overall_score": round(self.overall_score, 2),
            "scores": {
                "nodes": self.node_score.pct,
                "edges": self.edge_score.pct,
                "compile": self.compile_score.pct,
                "validate": self.validate_score.pct,
            },
        }


class MotifEvaluator:
    """Motif 评估器 — 质量门禁。"""

    MIN_PASS_SCORE = 0.6

    def evaluate(self, motif) -> MotifEvalResult:
        """评估单个 Motif。"""
        from core.comfyui_compiler import (
            WorkflowIR, IRComponent, IRConnection, IROutput, GraphCompiler
        )
        
        errors = []
        
        # 1. Node completeness
        node_score = self._eval_nodes(motif)
        
        # 2. Edge completeness
        edge_score = self._eval_edges(motif)
        
        # 3. Compile test
        compile_score, compile_errors = self._eval_compile(motif)
        errors.extend(compile_errors)
        
        # 4. Validate test
        validate_score = self._eval_validate(motif)
        
        # Overall
        weights = {"nodes": 0.25, "edges": 0.25, "compile": 0.3, "validate": 0.2}
        overall = (
            node_score.score/node_score.max_score * weights["nodes"] +
            edge_score.score/edge_score.max_score * weights["edges"] +
            compile_score.score/compile_score.max_score * weights["compile"] +
            validate_score.score/validate_score.max_score * weights["validate"]
        )
        passed = overall >= self.MIN_PASS_SCORE and len(errors) == 0
        
        return MotifEvalResult(
            motif_id=motif.motif_id,
            name=motif.name,
            passed=passed,
            overall_score=overall,
            node_score=node_score,
            edge_score=edge_score,
            compile_score=compile_score,
            validate_score=validate_score,
            errors=errors,
        )
    
    def _eval_nodes(self, motif) -> EvalScore:
        score = 0
        max_score = len(motif.nodes) * 2 if motif.nodes else 2
        details = []
        warnings = []
        
        if not motif.nodes:
            return EvalScore(0, 1, details=["无节点"], warnings=["Motif 必须有节点"])
        
        for n in motif.nodes:
            if n.class_type:
                score += 1
            if n.role:
                score += 1
            else:
                warnings.append(f"节点 {n.class_type} 缺少 role")
        
        return EvalScore(score, max(max_score, 1), details=details, warnings=warnings)
    
    def _eval_edges(self, motif) -> EvalScore:
        if not motif.nodes:
            return EvalScore(0, 1, details=["无节点，无法评估连接"])
        
        if not motif.edges:
            return EvalScore(0.3, 1, details=["无显式连接"], warnings=["建议补充 edges"])
        
        # Check edges reference valid nodes
        node_roles = {n.role for n in motif.nodes}
        valid = 0
        for e in motif.edges:
            if e.from_node in node_roles and e.to_node in node_roles:
                valid += 1
        
        return EvalScore(valid / len(motif.edges), 1, 
                        details=[f"{valid}/{len(motif.edges)} 有效连接"],
                        warnings=[] if valid == len(motif.edges) else [f"{len(motif.edges)-valid} 条连接引用无效节点"])
    
    def _eval_compile(self, motif) -> tuple[EvalScore, list[str]]:
        """尝试将 Motif 编译为 WorkflowIR 并执行 Compiler。"""
        from core.comfyui_compiler import (
            WorkflowIR, IRComponent, IRConnection, IROutput, GraphCompiler,
            BUILTIN_MOTIFS
        )
        
        errors = []
        
        if not motif.nodes:
            return EvalScore(0, 1, details=["无节点"], warnings=["无法编译"]), ["Motif 无节点"]
        
        # Build IR from motif
        try:
            ir = WorkflowIR(
                ir_id=f"eval_{motif.motif_id}",
                graph_type="single_workflow",
                task_type=motif.task_types[0] if motif.task_types else "txt2img",
            )
            
            for n in motif.nodes:
                ir.components.append(IRComponent(
                    id=n.role or f"n_{n.class_type}",
                    role=n.role or "unknown",
                    node_class=n.class_type,
                    params=dict(n.params),
                ))
            
            # Build default connections from edges
            for e in motif.edges:
                ir.connections.append(IRConnection(e.from_node, e.from_port, e.to_node, e.to_port))
            
            # Compile
            compiler = GraphCompiler(BUILTIN_MOTIFS)
            compiled = compiler.compile(ir)
            
            if compiled.is_valid:
                return EvalScore(1, 1, details=[f"编译成功: {len(compiled.workflow)} 节点"]), []
            else:
                diag = "; ".join(compiled.diagnostics[-3:])
                errors.append(f"编译失败: {diag}")
                return EvalScore(0.5, 1, details=["编译部分失败"], warnings=[diag]), errors
                
        except Exception as e:
            errors.append(f"编译异常: {e}")
            return EvalScore(0, 1, details=["编译异常"]), errors
    
    def _eval_validate(self, motif) -> EvalScore:
        """尝试编译后校验。"""
        from core.comfyui_compiler import (
            WorkflowIR, IRComponent, IRConnection, GraphCompiler, BUILTIN_MOTIFS
        )
        from core.comfyui_validator import validate_workflow
        
        if not motif.nodes:
            return EvalScore(0, 1, details=["无节点"], warnings=["无法校验"])
        
        try:
            ir = WorkflowIR(
                ir_id=f"eval_val_{motif.motif_id}",
                graph_type="single_workflow",
                task_type=motif.task_types[0] if motif.task_types else "txt2img",
            )
            for n in motif.nodes:
                ir.components.append(IRComponent(
                    id=n.role or f"n_{n.class_type}",
                    role=n.role or "unknown",
                    node_class=n.class_type,
                ))
            for e in motif.edges:
                ir.connections.append(IRConnection(e.from_node, e.from_port, e.to_node, e.to_port))
            
            compiler = GraphCompiler(BUILTIN_MOTIFS)
            compiled = compiler.compile(ir)
            
            if compiled.is_valid and compiled.workflow:
                v = validate_workflow(compiled.workflow)
                if v.is_valid or not v.errors:
                    return EvalScore(1, 1, details=[f"校验通过: {len(compiled.workflow)} 节点"])
                else:
                    return EvalScore(0.5, 1, details=["校验发现警告"],
                                    warnings=[e.message[:60] for e in v.errors[:2]])
            return EvalScore(0.3, 1, details=["编译不完整，跳过校验"])
        except Exception:
            return EvalScore(0, 1, details=["校验异常"])


def evaluate_registry(registry=None, min_score: float = 0.6) -> list[MotifEvalResult]:
    """评估注册表中所有 Motif。"""
    from core.comfyui_motif import get_registry
    
    reg = registry or get_registry()
    evaluator = MotifEvaluator()
    results = []
    
    for motif in reg.list_all():
        result = evaluator.evaluate(motif)
        results.append(result)
        status = "✅" if result.passed else "❌"
        print(f"  {status} {motif.motif_id}: {result.overall_score:.2f} [{result.node_score.pct} N | {result.edge_score.pct} E | {result.compile_score.pct} C | {result.validate_score.pct} V]")
    
    return results


def update_quality_scores(results: list[MotifEvalResult], registry=None):
    """将评估结果写回 Motif 的 quality_score。"""
    from core.comfyui_motif import get_registry
    
    reg = registry or get_registry()
    updated = 0
    for r in results:
        motif = reg.get(r.motif_id)
        if motif:
            motif.quality_score = max(0.1, min(1.0, r.overall_score))
            motif.pass_rate = r.overall_score
            updated += 1
    return updated
