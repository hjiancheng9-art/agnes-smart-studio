"""Self-healing layer — 18 modules.

Re-exports all public APIs from flat core/ self-heal modules.
All original imports remain valid.
New code can use: from core.mod_self_heal import SelfHealer
"""

from core.self_audit import *
from core.self_heal import *
from core.self_evolve import *
from core.self_tool import *
from core.incident_classifier import *
from core.incident_playbook import *
from core.incident_store import *
from core.remediation_executor import *
from core.reflection import *
from core.reflection_loop import *
from core.failure_learning import *
from core.rollback_manager import *
from core.rollback_engine import *
from core.rollback_orchestrator import *
from core.recovery import *
from core.crash_guard import *
from core.fake_fix_detector import *
from core.fixability_estimator import *
