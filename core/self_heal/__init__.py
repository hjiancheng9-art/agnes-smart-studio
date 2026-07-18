"""Self-healing & fault recovery (8 modules).

Detect, diagnose, and repair system issues automatically.
"""

__all__ = [
    "failure_learning",  # learn from failures
    "healing",  # healing strategies
    "incident_classifier",  # classify incidents by severity
    "incident_playbook",  # incident response playbooks
    "incident_store",  # persistent incident tracking
    "recovery",  # recovery procedures
    "reflection",  # reflection on past actions
    "reflection_loop",  # continuous reflection cycle
    "remediation_executor",  # execute remediation plans
    "rollback_engine",  # rollback execution engine
    "rollback_manager",  # manage rollback operations
    "rollback_orchestrator",  # orchestrate multi-step rollback
    "self_audit",  # comprehensive self-audit
    "self_evolve",  # self-improvement and learning
    "self_heal",  # self-healing engine
    "self_tool",  # self-inspection tools
]
