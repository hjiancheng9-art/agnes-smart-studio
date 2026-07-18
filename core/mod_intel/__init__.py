# ruff: noqa — intentional re-export package, star imports by design
"""Code intelligence layer — 9 modules.

Re-exports all public APIs from flat core/ intel modules.
All original imports remain valid.
New code can use: from core.mod_intel import CodeAnalyzer
"""

from core.awareness_graph import *
from core.code_intel import *
from core.lsp import *
from core.memory_bridge import *
from core.rag import *
from core.repo_map import *
from core.repo_understanding import *
from core.repo_wiki import *
from core.semantic_memory import *
