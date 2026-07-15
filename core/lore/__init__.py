"""CRUX lore layer — world-view / narrative modules + intimate-slot implementations.

Layout:
  intimate_slots/  — real implementations of the 7 "intimate slot" subsystems
                     (talisman/inner_armor/backpack/belt/left_ring/right_ring/cloak).
                     The public facade lives in ``core/intimate_slots`` and thin-
                     re-exports from here; runtime wiring is in ``core/beast_wiring``.
  claude_dna.py    — DNA narrative prompt getters. NOTE: currently not injected into
  codebuddy_dna.py   any system prompt; only these files' mtime feeds the prompt cache
                     fingerprint in ``core/chat_prompt``. Injected lore is
                     ``seven_beasts_fusion`` / ``golden_finger`` instead.

See docs/architecture-lore-and-slots.md for the full map.
"""
