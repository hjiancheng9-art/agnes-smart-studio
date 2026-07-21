"""CRUX DNA Gene Registry — 7 genes mapped to actual working modules.

Each DNA "gene" represents a core capability that defines CRUX's identity.
Unlike the deprecated "golden fingers" (which were aspirational docstrings),
these genes all have verified runtime implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DnaGene:
    """A single DNA gene — a verified core capability."""

    id: int
    name: str
    description: str
    module: str  # Primary implementation module
    key_symbols: list[str] = field(default_factory=list)
    phase: str = ""  # Orchestration phase where active


# ═══════════════════════════════════════════════════════════════
# 7 DNA Genes
# ═══════════════════════════════════════════════════════════════

GENES: list[DnaGene] = [
    DnaGene(
        id=1,
        name="自进化",
        description="Goal-driven self-evolution with reflection loop and evaluation",
        module="core.executor",
        key_symbols=["GoalManager", "SelfReflection", "SemanticVerifier"],
        phase="VERIFY",
    ),
    DnaGene(
        id=2,
        name="工具网格",
        description="Tool Registry Mesh — unified discovery, routing, and caching across providers",
        module="core.tool_registry_mesh",
        key_symbols=["ToolRegistryMesh", "ToolTier", "TOOL_CATEGORIES"],
        phase="EXECUTE",
    ),
    DnaGene(
        id=3,
        name="边界校验",
        description="Defense layer — circuit breaking, capability registry, file snapshots, operation dedup",
        module="core.defense",
        key_symbols=["get_circuit", "CircuitBreaker", "methodology_pre_check"],
        phase="EXECUTE",
    ),
    DnaGene(
        id=4,
        name="自扩展",
        description="Skill marketplace — search, install, auto-discover, and hot-load skills",
        module="core.skills",
        key_symbols=["SkillManager", "get_manager", "load_skill"],
        phase="GATE",
    ),
    DnaGene(
        id=5,
        name="多智能体",
        description="Multi-agent orchestration — swarm dispatch, plan-execute, and mode routing",
        module="core.multi_agent",
        key_symbols=["agent_swarm", "multi_agent", "compute_agent_mode"],
        phase="EXECUTE",
    ),
    DnaGene(
        id=6,
        name="语义记忆",
        description="Memory bridge — persistent knowledge extraction and context injection across sessions",
        module="core.memory_bridge",
        key_symbols=["MemoryBridge", "inject_context", "extract_key_facts"],
        phase="CLOSE",
    ),
    DnaGene(
        id=7,
        name="容灾自愈",
        description="Four-layer resilience — provider failover → retry → self-heal audit → circuit break",
        module="core.beast_wiring",
        key_symbols=["baihu_recovery", "SelfHealer", "reset_background_manager"],
        phase="EXECUTE",
    ),
]


def get_gene(gene_id: int) -> DnaGene | None:
    """Look up a DNA gene by ID."""
    for g in GENES:
        if g.id == gene_id:
            return g
    return None


def get_genes_by_phase(phase: str) -> list[DnaGene]:
    """Get all genes active in a given orchestration phase."""
    return [g for g in GENES if g.phase == phase]


def verify_all_genes() -> dict[str, bool]:
    """Verify all 7 genes are importable. Returns {gene_name: ok}."""
    results = {}
    for g in GENES:
        try:
            __import__(g.module)
            results[g.name] = True
        except ImportError:
            results[g.name] = False
    return results
