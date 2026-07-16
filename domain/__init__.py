"""CRUX Domain Layer — pure data types and protocols with zero infrastructure dependencies.

This layer defines WHAT the system does, not HOW. No imports from core/, no I/O.
New runtime modules depend on domain/. Compatibility adapters translate old ↔ new.
"""
