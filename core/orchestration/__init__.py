"""Orchestration & execution layer (20 modules).

Plans, schedules, and executes tasks — from simple tool calls to multi-phase workflows.
"""

__all__ = [
    # Core orchestration
    "runtime_orchestrator",  # RuntimeOrchestrator — main execution engine
    "runtime_types",  # ExecutionPlan, ExecutionMode, TaskComplexity
    "runtime_result",  # runtime result types
    "runtime_guard",  # sandbox and safety guard during execution
    "runtime_inspect",  # runtime introspection and debugging
    "orchestra",  # orchestration presets and launchers
    "orchestration",  # low-level orchestration primitives
    # Task management
    "task_manager",  # task lifecycle management
    "task_complexity",  # task complexity estimation
    "task_governor",  # task budget and rate limiting
    "task_spec_builder",  # build task specs from user intent
    # Execution
    "execution_policy",  # choose_policy() — task classification
    "executor",  # executor core
    "executor_models",  # executor data models
    "plan_executor",  # multi-step plan execution
    "plan_mode",  # plan mode workflow
    "deliberate_workflow",  # deliberate execution workflow
    # Pipeline
    "pipeline_dag",  # DAG-based pipeline execution
    "pipeline_tools",  # pipeline tools (create_project, etc.)
    "pipeline_state",  # pipeline state persistence
]
